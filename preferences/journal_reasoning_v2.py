"""Retrieve precedent by signed outcomes and the participant's stated reasons."""

import math
import re
from dataclasses import dataclass

from . import journal_reasoning as v1
from .journal_forecast import Forecast, JournalMeasure, JournalRequest, PastDecision, _choice, wording_forecast
from .journal_wording import content_features, outcome_difference, outcome_features


MODEL = "reasoning-examples-v2"
# These words can qualify a more specific phrase. Alone they do not establish
# that two decisions have the same mechanism, beneficiary or policy effect.
_WEAK = v1.GENERIC_ACTIONS | set("""
tax levy surcharge fee rate revenue funding fund public money cost financial
increase increasing increased additional decrease decreasing reduce reduced
charge charging pay payment amount percent dollar million provide providing
service resident area authority government office election voter voting use
using issue general make making create implementation implementing
year beginning include including first again over tax base
""".split())
_FISCAL_STAGES = {"new levy", "allocate revenue"}
_RATE_QUALIFIERS = _WEAK | {"higher", "lower", "cut", "cutting", "imposing", "imposed", "impose",
                            "raise", "raising", "mixed", "rates", "transfer"}
_SENTENCES = re.compile(r"(?<=[.!?])\s+|\n+")
_DIRECT = re.compile(
    r"^\s*(?:(?:and|because)\s+)?(?:i|we)\s+(?:(?:generally|strongly|personally|usually)\s+)?"
    r"(?:(do not|don't|never)\s+)?"
    r"(support|favor|prefer|want|value|oppose|reject|dislike)\s+(.+)", re.I,
)
_ONLY_FOR = re.compile(
    r"^\s*(?:i|we)\s+(?P<initial>only\s+)?(?:support|favor|prefer)\s+(?P<subject>.+?)\s+"
    r"(?P<inside>only\s+)?(?:for|if)\s+(?P<condition>.+)$", re.I,
)


@dataclass
class CaseMatch:
    item: PastDecision
    score: float
    matched_terms: tuple[str, ...]
    citation: str | None
    citation_supports_yes: bool | None = None


def _specific(term: str) -> bool:
    # Compound fiscal anchors carry more meaning than their separate words.
    if term.endswith((" tax base", "tax rate change", "tax mixed rates")):
        return True
    words = term.split()
    # Phrases made from incidental qualifiers are not independent evidence.
    return any(word not in _WEAK for word in words)


def _signed(features: dict[str, int]) -> dict[str, int]:
    # A proposition repeated on both sides is still one proposition.
    return {term: 1 if value > 0 else -1 for term, value in features.items() if _specific(term)}


def _weight(term: str) -> float:
    if term.endswith((" tax base", "tax rate change")):
        return 4.
    return 2. if " " in term else 1.


def _comparable_terms(left: dict[str, int], right: dict[str, int]) -> tuple[dict[str, int], dict[str, int]]:
    # When both texts describe rate changes on the same tax, the signed
    # change replaces the unsigned instrument names. A beneficiary or other
    # distinguishing provision can still contribute independently. In a
    # tiered change, the instrument alone implies no overall rate direction.
    def rate_instruments(features: dict) -> set[str]:
        return {term.rsplit(" ", 2)[0] for term in features if term.endswith(("tax rate change", "tax mixed rates"))}

    for instrument in rate_instruments(left) & rate_instruments(right):
        rate = instrument + " rate change"
        scoped_words = _RATE_QUALIFIERS | set(instrument.split())
        aliases = {term for term in left.keys() | right.keys()
                   if term != rate and set(term.split()) <= scoped_words}
        left = {term: sign for term, sign in left.items() if term not in aliases}
        right = {term: sign for term, sign in right.items() if term not in aliases}
    return left, right


def _overlap(left: dict[str, int], right: dict[str, int]) -> tuple[float, tuple[str, ...]]:
    """Similarity of signed content; a score's sign changes if one ballot flips."""
    left, right = _comparable_terms(left, right)
    shared = sorted(left.keys() & right.keys())
    if not shared:
        return 0., ()
    # A single unqualified word such as a town name is a poor point of
    # comparison between two detailed measures. It can identify a short,
    # explicit alternative, such as a choice between Saturday and Sunday.
    words = {word for term in shared for word in term.split() if word not in _WEAK}
    if (len(words) < 2 and min(len(left), len(right)) > 4
            and not any(term.endswith((" tax base", " tax rate change")) for term in shared)):
        return 0., ()
    support = sum(left[term] * right[term] * _weight(term) for term in shared)
    if not support:
        return 0., ()
    # A repeated mention never creates a second observation. Cap the effect of
    # packet length without forcing a tiny overlap to count as a perfect match.
    scale = math.sqrt(min(32., sum(map(_weight, left))) * min(32., sum(map(_weight, right))))
    alignment = max(-1., min(1., support / scale))
    oriented = [term for term in shared if left[term] * right[term] * alignment > 0]
    terms = sorted(oriented, key=lambda term: (-_weight(term), sum(word in _WEAK for word in term.split()), term))
    return alignment, tuple(terms)


def _different_fiscal_decisions(target: dict, earlier: dict) -> bool:
    def governing_stages(features: dict) -> set[str]:
        stages = features.keys() & _FISCAL_STAGES
        # Spending receipts "without a new levy" describes the levy as an
        # alternative to the governing action. This also holds on a label swap.
        if len(stages) == 2 and features["allocate revenue"] * features["new levy"] < 0:
            return {"allocate revenue"}
        return stages

    target_stages = governing_stages(target)
    earlier_stages = governing_stages(earlier)
    return bool(target_stages and earlier_stages and not target_stages & earlier_stages)


def _direct_preference(clause: str) -> dict[str, int]:
    match = _DIRECT.search(clause.replace("’", "'"))
    if not match:
        return {}
    negation, verb, object_text = match.groups()
    direction = -1 if verb.casefold() in {"oppose", "reject", "dislike"} else 1
    if negation:
        direction *= -1
    return {term: direction * sign for term, sign in _signed(content_features(object_text)).items()}


def _outside_stated_scope(terms: dict[str, int], notes: list[tuple[str, bool]], vote_score: float) -> bool:
    for text, _ in notes:
        for sentence in _SENTENCES.split(text):
            limit = _ONLY_FOR.match(sentence)
            if not limit or not (limit["initial"] or limit["inside"]):
                continue
            orientation, _ = _overlap(terms, _signed(content_features(limit["subject"])))
            if orientation * vote_score <= 0:
                continue
            # A stated necessary condition can rule out transferring a Yes
            # analogy. Silence about the condition never establishes a No.
            required = {term: sign for term, sign in _signed(content_features(limit["condition"])).items()
                        if " " not in term or term.endswith(" tax base")}
            polarity = 1 if orientation > 0 else -1
            if not required or any(terms.get(term) != sign * polarity for term, sign in required.items()):
                return True
    return False


def _switch(item: PastDecision, target: JournalMeasure, alignment: float) -> bool | None:
    condition = v1._counterfactual_condition(item)
    if not condition or not alignment:
        return None
    declined_maps_to_yes = (alignment > 0) == (item.vote == "no")
    candidate = target.yesMeaning if declined_maps_to_yes else target.noMeaning
    alternative = target.noMeaning if declined_maps_to_yes else target.yesMeaning
    original = item.measure.noMeaning if item.vote == "yes" else item.measure.yesMeaning
    requirements = {term: sign for term, sign in condition.items() if " " not in term}

    def satisfies(text: str) -> bool:
        features = outcome_features(text)
        return bool(requirements) and all(features.get(term) == sign for term, sign in requirements.items())

    if satisfies(candidate) and not satisfies(alternative) and not satisfies(original):
        return declined_maps_to_yes
    return None


def _match(target: JournalMeasure, target_raw: dict[str, int], terms: dict[str, int], item: PastDecision) -> CaseMatch:
    earlier_raw = outcome_difference(item.measure)
    earlier = _signed(earlier_raw)
    compatible = not _different_fiscal_decisions(target_raw, earlier_raw)
    alignment, anchors = _overlap(terms, earlier) if compatible else (0., ())
    direction = 1 if item.vote == "yes" else -1
    notes = [(item.reasoning, True)]
    if item.clarification:
        notes.append((item.clarification.answer, item.clarification.kind in {"weight", "contrast"}))
    if alignment and _outside_stated_scope(terms, notes, direction * alignment):
        alignment, anchors = 0., ()
    score = .72 * alignment * direction

    switch = _switch(item, target, alignment)
    if switch is not None:
        score = max(abs(alignment), .25) * (1 if switch else -1)
        return CaseMatch(item, score, anchors, item.clarification.answer, switch)

    # A note can highlight a distinguishing ballot feature or state a general
    # preference directly. Other mentions, including the text of a question,
    # have no direction. Only the strongest contribution in each direction is
    # used so repetition and unrelated sentences cannot inflate or dilute it.
    positive = (0., (), None)
    negative = (0., (), None)
    for text, observed in notes:
        for sentence in _SENTENCES.split(text):
            # Keep conditions attached to the full sentence. A comparison
            # cannot become an unconditional stance by splitting at a comma.
            qualified = v1.QUALIFIER.search(sentence)
            for clause in v1.CLAUSE.split(sentence):
                mentioned = content_features(clause)
                if _different_fiscal_decisions(target_raw, mentioned):
                    continue
                direct = {} if qualified else _direct_preference(clause)
                if direct:
                    effect, matches = _overlap(terms, direct)
                    effect *= .85
                elif observed and alignment and not qualified:
                    # The note can highlight the participant's actual choice
                    # on this ballot, including what they voted to decline.
                    projection = {term: sign for term, sign in earlier.items() if term in mentioned}
                    effect, matches = _overlap(terms, projection)
                    effect *= .5 * direction
                else:
                    continue
                if effect > positive[0]:
                    positive = (effect, matches, sentence)
                if effect < negative[0]:
                    negative = (effect, matches, sentence)
    note_effect = positive[0] + negative[0]
    citation = None
    if note_effect:
        _, reason_terms, citation = positive if note_effect > 0 else negative
        # A direct statement can override a weak vote analogy, but supplies at
        # most one case's worth of evidence together with that decision.
        score = max(-1., min(1., score + note_effect))
        if score * note_effect > 0:
            anchors = tuple(dict.fromkeys((*reason_terms, *anchors)))
    return CaseMatch(item, score, anchors, citation, note_effect > 0 if citation else None)


def ranked_cases(measure: JournalMeasure, history: list[PastDecision]) -> list[CaseMatch]:
    """The exact signed precedents used in the probability and its explanation."""
    raw = outcome_difference(measure)
    terms = _signed(raw)
    cases = (_match(measure, raw, terms, item) for item in history)
    return sorted((case for case in cases if case.score), key=lambda case: -abs(case.score))


def _describe(match: CaseMatch) -> str:
    title = v1._excerpt(match.item.measure.title, 100)
    choice = "Yes" if match.score > 0 else "No"
    anchor = match.matched_terms[0]
    if anchor.endswith(" tax base"):
        feature = "a tax on " + anchor.removesuffix(" tax base")
    elif anchor.endswith("tax rate change"):
        feature = "the direction of the " + anchor.removesuffix(" change")
    else:
        feature = "the allocation of revenue" if anchor == "allocate revenue" else anchor
    if match.citation:
        description = f"The closest evidence from “{title}” concerns {feature}."
        note_choice = "Yes" if match.citation_supports_yes else "No"
        quote = v1._excerpt(match.citation, 200)
        description += f" Your written reason points toward {note_choice} here. You wrote “{quote}”"
        if not quote.endswith((".", "!", "?", "…")):
            description += "."
        if note_choice != choice:
            description += f" The vote and reason together still lean {choice}."
    else:
        description = f"Your vote on “{title}” points toward {choice} here based on the outcome wording about {feature}."
    return description


def reasoning_forecast(req: JournalRequest) -> Forecast:
    cases = ranked_cases(req.measure, req.history)
    weight = sum(abs(case.score) for case in cases)
    probability = round(.5 + .5 * sum(case.score for case in cases) / (2 + weight), 6)
    if cases:
        best = cases[0]
        explanation = _describe(best)
        contrary = next((case for case in cases[1:] if case.score * best.score < 0), None)
        if contrary:
            explanation += " One earlier choice points the other way. " + _describe(contrary)
    else:
        explanation = "No earlier choice or stated reason matches a distinguishing outcome here. Both outcomes score 50%."
    if probability == .5:
        explanation += " A repeatable tie-break supplies the displayed choice."
    return Forecast(choice=_choice(req, probability), probabilityYes=probability, explanation=explanation,
                    model=MODEL, historyCount=len(req.history))


def paired_forecast(req: JournalRequest) -> v1.PairedForecast:
    masked = req.model_copy(update={"history": [
        item.model_copy(update={"reasoning": "", "clarification": None}) for item in req.history
    ]})
    return v1.PairedForecast(reasoning=reasoning_forecast(req), baseline=wording_forecast(masked),
                             withoutReasoning=reasoning_forecast(masked).model_copy(
                                 update={"model": MODEL + "-without-reasoning"}))


def profile(req: v1.HistoryRequest) -> v1.Profile:
    return v1.profile(req).model_copy(update={"model": MODEL})


def question(req: v1.QuestionRequest) -> v1.QuestionResult:
    target = req.target
    # Reuse the trigger policy and generic counterfactual/weight prompts. The
    # old retriever never sees history; references come from the v2 scorer.
    result = v1.question(req.model_copy(update={"history": []}))
    if not result.question:
        return result
    history = [item for item in req.history if item.id != target.id]
    cases = ranked_cases(target.measure, history)
    direction = 1 if target.vote == "yes" else -1
    reference = max(cases, key=lambda case: abs(case.score) * (1.5 if case.score * direction < 0 else 1),
                    default=None)
    earlier = reference.item if reference else None
    if earlier is None:
        # A prior clarification can mention a comparable decision without
        # committing to a side. It is suitable for an elicitation question,
        # but must never enter the forecast as a vote or a preference.
        terms = _signed(outcome_difference(target.measure))
        best = 0.
        for item in history:
            if item.clarification:
                overlap, anchors = _overlap(terms, _signed(content_features(item.clarification.answer)))
                if len(anchors) > 1 and abs(overlap) > best:
                    best, earlier = abs(overlap), item
    if earlier is None:
        return result
    reason = v1._excerpt(target.reasoning, 150)
    prompt = (f"You wrote “{reason}”. " if reason else "") + (
        f"Here you chose “{v1._chosen(target)}”. On “{v1._excerpt(earlier.measure.title, 75)}” "
        f"you chose “{v1._chosen(earlier)}”. What distinction or shared consideration best explains those choices?"
    )
    return v1.QuestionResult(question=v1.Question(trigger=result.question.trigger, kind="contrast", prompt=prompt,
                                                   referenceId=earlier.id))

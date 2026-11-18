"""Case-based preference estimates and follow-up selection for the personal journal."""

import math
import re
from collections import Counter
from typing import Literal
from uuid import UUID

from .journal_forecast import (
    Forecast, JournalData, JournalMeasure, JournalRequest, PastDecision, QuestionKind, _choice,
)


MODEL = "reasoning-examples-v1"
COUNTERFACTUAL = "What would need to change about the other outcome,"
STOP = set("""
a an the i me my we our you your it its is am was are were be been being has have had
of for on to from and or with in at as by this that these those their they them then than
but would will can could should may yes vote votes voting measure proposal if so do does
did very just i'm really personally because what which who it's something about
""".split())
LABEL = re.compile(
    r"^(?:(?:a\s+)?(?:yes|no)\s+vote\b|(?:a\s+)?vot(?:e|ing)\s+(?:yes|no)\b"
    r"|(?:yes|no)(?=\s*(?:[:\-–—]|means\b)))\s*[:\-–—]?\s*(?:means\s+)?", re.I,
)
CLAUSE = re.compile(r"[.!?;,\n]+|\b(?:but|whereas|however)\b", re.I)
WORDS = re.compile(r"[^\W_]+(?:'[^\W_]+)?")
STANCE = re.compile(
    r"^(?:i|we)\s+(?:(?:generally|strongly|personally|usually)\s+)?"
    r"(?:(do not|don't|never)\s+)?"
    r"(support|favor|prefer|want|value|oppose|reject|dislike)\s+(.+)$", re.I,
)
QUALIFIER = re.compile(r"\b(if|unless|except|only|when|over|rather than|instead of)\b", re.I)
CONDITION_START = re.compile(
    r"^(?:only\s+)?(?:if\s+(?:(?:there\s+(?:were to be|were|was)|(?:it|they|the measure)\s+"
    r"(?:included|added|provided|required|offered))\s+)?|with(?:out)?\s+|"
    r"(?:adding|including|removing|dropping|eliminating)\s+)", re.I,
)
REMOVE = re.compile(r"^(?:without|removing|dropping|eliminating)\s+"
                    r"|^(?:only\s+)?if\s+(?:it|they)\s+(?:removed|dropped|eliminated)\s+", re.I)
REMOVED = re.compile(r"\s+(?:were|was|is|are)\s+(?:removed|dropped|eliminated)$", re.I)
ADDED = re.compile(r"\s+(?:were|was|is|are)\s+(?:added|required|included|provided)$", re.I)
GENERIC_ACTIONS = set("""
approve approved approval disapprove reject rejected rejection decline deny accept adopt enact pass
authorize authorization amend amendment permit allow require establish change fund continue keep maintain
current existing retain preserve repeal prohibit proposed new ballot ordinance act program proposal
result mean means law policy plan item effect favor support oppose
""".split())


def _substantive(term: str) -> bool:
    return any(word not in GENERIC_ACTIONS for word in term.split())


def _features(text: str) -> dict[str, int]:
    """Presence of content words and adjacent pairs, with simple local negation."""
    scores: Counter[str] = Counter()
    for clause in CLAUSE.split(LABEL.sub("", text.strip()).casefold().replace("’", "'")):
        previous = ""
        sign = 1
        for word in WORDS.findall(clause):
            if word in {"not", "no", "never", "without"} or word.endswith("n't"):
                sign = -1
                previous = ""
            elif word in {"and", "or"}:
                sign, previous = 1, ""
            elif word not in STOP:
                # Match common singular/plural forms in short written answers.
                if len(word) > 4 and word.endswith("s") and not word.endswith(("ss", "us", "is")):
                    word = word[:-1]
                scores[word] += sign
                if previous:
                    scores[previous + " " + word] += sign
                previous = word
    return {term: 1 if value > 0 else -1 for term, value in scores.items() if value}


def _difference(measure: JournalMeasure) -> dict[str, int]:
    yes, no = _features(measure.yesMeaning), _features(measure.noMeaning)
    # Procedural words alone carry no preference evidence. Pairs like "approve
    # bookmobile" still distinguish accepting and declining a related outcome.
    return {term: diff for term in yes.keys() | no.keys()
            if _substantive(term) and (diff := yes.get(term, 0) - no.get(term, 0))}


def _cosine(a: dict, b: dict) -> float:
    norm = math.sqrt(sum(x*x for x in a.values()) * sum(x*x for x in b.values()))
    return sum(a[term] * b[term] for term in a.keys() & b.keys()) / norm if norm else 0.


def _preference_vector(decision: PastDecision, target: dict[str, int]) -> tuple[dict, str | None]:
    direction = 1 if decision.vote == "yes" else -1
    contrast = _difference(decision.measure)
    vector: Counter[str] = Counter({term: value * direction for term, value in contrast.items()})
    contributions: list[tuple[int, str]] = []
    notes = [(decision.reasoning, False)]
    if decision.clarification:
        # Older untyped answers can contribute explicit preferences, but their
        # relationship to a particular ballot outcome is unknown.
        notes.append((decision.clarification.answer, decision.clarification.kind not in ("weight", "contrast")))
    for note, hypothetical in notes:
        adjustment: Counter[str] = Counter()
        # Mention establishes salience, not endorsement. A reason referring to a
        # declined outcome strengthens the evidence against that outcome.
        if not hypothetical:
            for term in contrast.keys() & _features(note).keys():
                adjustment[term] += contrast[term] * direction
        # Only simple stated preferences contribute direction outside the ballot
        # contrast. Conditional and comparative claims stay in the evidence for
        # retrieval/follow-up; splitting them can reverse their intended meaning.
        for sentence in re.split(r"[.!?;\n]+", note.replace("’", "'")):
            if QUALIFIER.search(sentence):
                continue
            for clause in CLAUSE.split(sentence):
                match = STANCE.fullmatch(clause.strip())
                if match:
                    negated, verb, object_text = match.groups()
                    sign = -1 if verb.casefold() in {"oppose", "reject", "dislike"} else 1
                    if negated:
                        sign *= -1
                    for term, value in _features(object_text).items():
                        adjustment[term] += 2 * sign * value
        vector.update(adjustment)
        projection = sum(target[term] * adjustment[term] for term in target.keys() & adjustment.keys())
        if projection:
            # Prefer a sentence containing an actual matching feature if the
            # entry is long. Keep its qualifiers in the returned quotation.
            matched = target.keys() & adjustment.keys()
            sentences = re.split(r"(?<=[.!?])\s+|\n+", note)
            relevant = max(sentences, key=lambda text: len(_features(text).keys() & matched))
            contributions.append((projection, relevant))
    citation = None
    if sum(effect for effect, _ in contributions):
        citation = max(contributions, key=lambda part: abs(part[0]))[1]
    return dict(vector), citation


def _counterfactual_condition(item: PastDecision) -> dict[str, int]:
    """Recognize a short addition/removal given in response to our switch question."""
    clarification = item.clarification
    if not clarification or clarification.kind != "counterfactual":
        return {}
    answer = clarification.answer.strip().rstrip(".!?").casefold()
    prefix = CONDITION_START.match(answer)
    removal = REMOVE.match(answer)
    if (not (prefix or removal) or len(answer) > 160 or
            re.search(r"[.!?;,]|\b(?:but|or|unless|except|maybe|unsure|possibly|perhaps)\b", answer)):
        return {}
    condition = answer[(removal or prefix).end():]
    suffix = REMOVED.search(condition)
    if suffix:
        condition = condition[:suffix.start()]
    else:
        condition = ADDED.sub("", condition)
    features = _features(condition)
    # A compound condition with ambiguous scope is retained verbatim in the
    # profile and LLM input. The lexical forecaster abstains on these cases.
    if not features or len(features) > 15 or QUALIFIER.search(condition):
        return {}
    return {term: -sign if removal or suffix else sign for term, sign in features.items()}


def _case_score(target: JournalMeasure, contrast: dict[str, int], item: PastDecision) -> tuple[float, str | None]:
    vector, citation = _preference_vector(item, contrast)
    score = _cosine(contrast, vector)
    condition = _counterfactual_condition(item)
    if not condition:
        return score, citation
    # Transfer a conditional switch only to a related choice. Reverse the
    # orientation when YES and NO describe the opposite outcomes on this ballot.
    earlier = _difference(item.measure)
    alignment = _cosine(earlier, contrast)
    anchors = {word for term in earlier.keys() & contrast.keys() for word in term.split()} - GENERIC_ACTIONS
    if abs(alignment) < .2 or not anchors:
        return score, citation
    declined_maps_to_yes = (alignment > 0) == (item.vote == "no")
    candidate = _features(target.yesMeaning if declined_maps_to_yes else target.noMeaning)
    alternative = _features(target.noMeaning if declined_maps_to_yes else target.yesMeaning)
    original = _features(item.measure.noMeaning if item.vote == "yes" else item.measure.yesMeaning)
    # Require the complete, signed condition on the formerly declined side.
    # Silence about an item does not establish that it was removed.
    requirements = {term: sign for term, sign in condition.items() if " " not in term}
    def satisfies(outcome: dict[str, int]) -> bool:
        return all(outcome.get(term) == sign for term, sign in requirements.items())
    if satisfies(candidate) and not satisfies(alternative) and not satisfies(original):
        return (abs(alignment) if declined_maps_to_yes else -abs(alignment)), item.clarification.answer
    return score, citation


def _excerpt(text: str, limit: int) -> str:
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    return (text[:limit-1].rsplit(" ", 1)[0] or text[:limit-1]) + "…"


def reasoning_forecast(req: JournalRequest) -> Forecast:
    target = _difference(req.measure)
    cases = [(item, *_case_score(req.measure, target, item)) for item in req.history]
    relevant = [case for case in cases if abs(case[1]) > 1e-9]
    # Each past decision supplies at most one example, regardless of length or
    # number of notes. Two neutral pseudo-observations shrink sparse estimates.
    weight = sum(abs(score) for _, score, _ in relevant)
    probability = round(0.5 + 0.5 * sum(score for _, score, _ in relevant) / (2 + weight), 6)
    if relevant:
        strongest, similarity, citation = max(relevant, key=lambda case: abs(case[1]))
        direction = "Yes" if similarity > 0 else "No"
        explanation = f"The strongest match is “{_excerpt(strongest.measure.title, 100)}”. "
        if citation:
            explanation += f"Your decision points toward {direction} here. In that entry you wrote “{_excerpt(citation, 150)}”."
        else:
            explanation += f"The wording of the outcomes you chose and declined points toward {direction} here."
    else:
        explanation = "There is no matching evidence in your previous choices and reasons. Both outcomes score 50%."
    if probability == .5:
        explanation += " A repeatable tie-break supplies the displayed choice."
    return Forecast(choice=_choice(req, probability), probabilityYes=probability, explanation=explanation,
                    model=MODEL, historyCount=len(req.history))


class Evidence(PastDecision):
    id: UUID


class HistoryRequest(JournalData):
    history: list[Evidence]


class Facet(JournalData):
    label: str
    evidenceIds: list[UUID]


class Profile(JournalData):
    model: str
    evidenceCount: int
    facets: list[Facet]


def profile(req: HistoryRequest) -> Profile:
    # Show the participant's actual words, including qualifiers or negation.
    # Show clarifications first and retain sourcing for repeated statements.
    facets: dict[str, Facet] = {}
    for follow_up in (True, False):
        for item in reversed(req.history):
            if follow_up and not item.clarification:
                continue
            note = item.clarification.answer if follow_up else item.reasoning
            label = _excerpt(note, 240)
            if not label:
                continue
            key = " ".join(note.casefold().split())
            if key not in facets and len(facets) < 12:
                facets[key] = Facet(label=label, evidenceIds=[])
            if key in facets and item.id not in facets[key].evidenceIds:
                facets[key].evidenceIds.append(item.id)
    return Profile(model=MODEL, evidenceCount=len(req.history), facets=list(facets.values()))


class QuestionTarget(Evidence):
    prediction: Forecast


class QuestionRequest(HistoryRequest):
    target: QuestionTarget


class Question(JournalData):
    trigger: Literal["miss", "uncertain"]
    kind: QuestionKind
    prompt: str
    referenceId: UUID | None = None


class QuestionResult(JournalData):
    question: Question | None


def _chosen(item: Evidence) -> str:
    return _excerpt(item.measure.yesMeaning if item.vote == "yes" else item.measure.noMeaning, 95)


def _precedent_tokens(item: Evidence) -> dict[str, int]:
    m = item.measure
    notes = [m.title, m.text, m.yesMeaning, m.noMeaning, item.reasoning]
    if item.clarification:
        notes.append(item.clarification.answer)
    content = " . ".join(notes)
    return dict.fromkeys((term for term in _features(content) if _substantive(term)), 1)


def question(req: QuestionRequest) -> QuestionResult:
    target = req.target
    missed = target.vote != target.prediction.choice
    if not missed and not .4 <= target.prediction.probabilityYes <= .6:
        return QuestionResult(question=None)
    trigger = "miss" if missed else "uncertain"
    target_words = _precedent_tokens(target)
    contrast = _difference(target.measure)
    best_rank = 0.
    reference = None
    for item in req.history:
        if item.id == target.id:
            continue
        words = _precedent_tokens(item)
        relevance = _cosine(target_words, words)
        # Require shared content and prefer a relevant precedent whose chosen
        # outcome would have pointed the other way on the present measure.
        if relevance < .18 or len(target_words.keys() & words.keys()) < 2:
            continue
        alignment = _cosine(contrast, _difference(item.measure))
        if target.vote != item.vote:
            alignment *= -1
        rank = relevance * (1 + max(0, -alignment))
        if rank > best_rank:
            reference, best_rank = item, rank
    reason = _excerpt(target.reasoning, 150)
    anchor = f"You wrote “{reason}”. " if reason else ""
    if reference:
        kind = "contrast"
        prompt = (
            f"{anchor}Here you chose “{_chosen(target)}”. On “{_excerpt(reference.measure.title, 75)}” "
            f"you chose “{_chosen(reference)}”. What distinction or shared consideration best explains those choices?"
        )
    elif missed and not .4 <= target.prediction.probabilityYes <= .6:
        kind = "weight"
        prompt = f"{anchor}What detail should the model give more or less weight to when a similar measure comes up?"
    else:
        kind = "counterfactual"
        declined = target.measure.noMeaning if target.vote == "yes" else target.measure.yesMeaning
        prompt = f"{anchor}{COUNTERFACTUAL} “{_excerpt(declined, 95)}”, for you to choose it?"
    follow_up = Question(trigger=trigger, kind=kind, prompt=prompt)
    if reference:
        follow_up.referenceId = reference.id
    return QuestionResult(question=follow_up)

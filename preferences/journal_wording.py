"""Signed, open-vocabulary evidence from the described effects of ballot choices."""

import re
from collections import Counter, defaultdict

from .journal_forecast import JournalMeasure


_LABEL = re.compile(
    r"^(?:(?:a\s+)?(?:yes|no)\s+vote\b|(?:a\s+)?vot(?:e|ing)\s+(?:yes|no)\b"
    r"|(?:a\s+)?(?:yes|no)(?=\s*(?:[:–—-]|means?\b|support|oppos|favor|reject|would\b)))"
    r"\s*[:–—-]?\s*"
)
_JURISDICTION = re.compile(
    r"\b(?i:(?:in|within|throughout) the (?:city|county|town|village|borough|state) of) "
    r"[A-Z][a-zA-Z'-]+(?: (?:[A-Z][a-zA-Z'-]+|(?:of|de|la) [A-Z][a-zA-Z'-]+))*"
)
_OPPOSE = set("oppose opposes opposed opposing reject rejects rejected rejecting disapprove "
              "disapproves disapproved prohibit prohibits prohibited prohibiting ban bans banned banning "
              "prohibition repeal repeals repealed repealing abolish abolishes abolished abolishing "
              "lift lifts lifting lifted prevent prevents prevented preventing".split())
_SUPPORT = set("support supports supported supporting favor favors favored favoring approve approves "
               "approved approving adopt adopts adopted adopting allow allows allowed allowing "
               "permit permits permitted permitting enact enacts enacted enacting authorize authorizes "
               "authorized authorizing establish establishes established establishing".split())
_STOP = set("""
    a an the at of in by on for with from to into upon and or it its is am are was were be been being
    will would shall should can could may might do does did have has had this that these those
    their they them itself as than such so i my me we our you your if which who what there
    city county district state local municipal ballot measure proposal proposed proposition
    voter voters vote votes means mean meaning following changes change making
    maintaining maintain maintains retain retaining keep keeping current existing status quo
    instead thereby otherwise unchanged including advising according asks whether
""".split())
# Reset the scope of an opposed proposal at an explicitly described alternative.
# Ordinary commas can introduce details of that same proposal (e.g. its beneficiaries).
_CLAUSE = re.compile(
    r"[;!?\n]+|\.(?!\d)|\b(?:but|whereas|instead|however)\b"
    r"|,\s*(?=(?:thereby\s+)?(?:support|oppos|retain|maintain|keep|continu|leav)\w*\b)"
    r"|\b(?:and|or)\s+(?=(?:would|will|shall|support|oppos|reject|retain|maintain|keep|prohibit|allow)\w*\b)"
)
_ADOPTION = re.compile(
    r"(?:(?:means?|would|will|to)\s+)*"
    r"(approve|adopt|pass|support|reject|oppose|defeat)"
    r"(?:s|d|ed|ing)?(?: (?:the |this |a )?(?:proposed )?(?:measure|proposal|ordinance|amendment))?[.!]?"
)
_PROPERTY = r"(?:property|real estate|real property|land(?: value)?)"
_ON_BASE = (r"(?:(?:(?:base|basis|burden|structure|method) )?"
            r"(?:is|are|falls?|(?:would|should) be) )?on (?:the )?")
_PROPERTY_TAX = re.compile(
    rf"\b(?:{_PROPERTY} tax(?:es)?|(?:tax(?:es)?|levy|levies) {_ON_BASE}{_PROPERTY}|taxing {_PROPERTY})\b"
)
_TRANSFER = re.compile(rf"\b(?:{_PROPERTY} transfer tax(?:es)?|tax(?:es)? on {_PROPERTY} transfers?)\b")
_ASSESSED_LEVY = re.compile(
    r"\b(levy|tax rate|increase)\b(?:[^.!?;]|\.(?=\d)){0,90}?\b(?:assessed value of (?:all |the |taxable )*property"
    r"|assessed property value)\b"
)
_EXISTING_REVENUE = re.compile(
    r"\b(?:(?:existing|current|already collected)\s+((?:[a-z]+\s+){0,2})(?:revenues?|receipts|funds)"
    r"|(?:revenues?|funds|money) (?:already collected|currently collected))\b"
)
_ALLOCATE = re.compile(
    r"\b(?:us(?:e|es|ing)|allocat(?:e|es|ing)|earmark(?:s|ing)?|dedicat(?:e|es|ing)|direct(?:s|ing)?) "
    r"(?:the |a portion of (?:the )?)?((?:[a-z]+ )?tax )?(existing revenue|revenues?|receipts|funds|proceeds)\b"
)
# Keep tax relief and the tax itself as different terms. Otherwise the words
# "fund property tax relief" can make an income tax look like a levy on land.
_BENEFIT = r"(?:relief|rebates?|credits?|exemptions?|refunds?|abatements?)"
_WORDS = re.compile(
    rf"(?:(?:property transfer|[a-z]+) )?tax {_BENEFIT}\b"
    r"|property transfer tax\b|property tax\b|existing revenue\b|allocate revenue\b|[a-z]+(?:'[a-z]+)?"
)
_LEVY = set("increase increases increased increasing raise raises raised raising impose imposes "
            "imposed imposing introduce introduces introduced introducing establish establishes established "
            "establishing enact enacts enacted enacting new additional".split())
_FISCAL = {"tax", "taxes", "levy", "levies", "property tax", "property transfer tax", "surcharge"}
_RISE = set("raise raises raised raising rise rises rising higher increase increases increased "
            "increasing hike hikes hiked hiking".split())
_FALL = set("lower lowers lowered lowering decrease decreases decreased decreasing cut cuts "
            "cutting reduce reduces reduced reducing reduction reductions fall falls falling".split())
_RATE_LINK = set("a an the this its their our to on of in by at be being been is are was were would "
                 "will should shall now proposed existing current local city district county state "
                 "rate rates".split())
_NEGATIONS = {"not", "no", "never", "without"}
_RATE_PREFIX = _RATE_LINK | _RISE | _FALL | _NEGATIONS
_TIER = re.compile(r"\b(?:brackets?|tiers?|thresholds?|valued|above|below|under|over|less than|more than)\b")
_TIER_STANCE = re.compile(r"^(?:would |means? )?(?:(not) )?(support\w*|oppos\w*|reject\w*)\b")
_BASE = re.compile(rf"\b([a-z]+)\s+tax(?:es)?\b(?!\s+{_BENEFIT}\b)")
_NON_BASE = _STOP | _OPPOSE | _SUPPORT | _LEVY | _FISCAL | _RISE | _FALL | set(
    "any all no lower higher high low reduced reduce reducing cuts cut cutting pay pays paid paying "
    "collect collected collecting general special annual rate different more less".split()
)


def _normalize(text: str) -> str:
    text = _JURISDICTION.sub(" ", text)
    text = text.casefold().translate(str.maketrans({"“": "", "”": "", '"': "", "‘": "'", "’": "'"}))
    # Strip paired single quotes around labels only. Keep substantive contractions.
    text = re.sub(r"'(yes|no)'", r"\1", text)
    text = re.sub(r"(?<=\w)-(?=\w)", " ", text)
    text = re.sub(r"\b(\w+)'s\b", r"\1", text)
    text = re.sub(r"\b(?:rather than|instead of)\b", "without", text)
    text = re.sub(r"\b(?:not change|no changes? to)\b", "maintain", text)
    return _PROPERTY_TAX.sub("property tax", _TRANSFER.sub("property transfer tax", text))


def _singular(word: str) -> str:
    if word == "sales":
        return word
    if word.endswith("ies") and len(word) > 4:
        return word[:-3] + "y"
    if word == "taxes":
        return "tax"
    if len(word) > 4 and word.endswith("s") and not word.endswith(("ss", "us", "is")):
        return word[:-1]
    return word


def _words(clause: str) -> list[tuple[str, int]]:
    tokens = []
    for match in _WORDS.finditer(clause):
        word = match[0]
        first, _, rest = word.partition(" ")
        if " tax " in word and first in _NON_BASE:
            # "No tax rebates" retains its negation. "Payroll tax rebates"
            # stays one benefit so it cannot masquerade as a payroll tax.
            tokens.append((first, match.start() + len(first)))
            word = rest
        tokens.append((word, match.end()))
    return tokens


def _rate_move(words: list[str], first: int, last: int) -> tuple[int, int] | None:
    """Find the action attached to the fiscal noun, without crossing spending or another object."""
    for start, step in ((first - 1, -1), (last + 1, 1)):
        sign = 1
        for index in range(start, -1 if step < 0 else len(words), step):
            word = words[index]
            if word in _RISE or word in _FALL:
                return (1 if word in _RISE else -1) * sign, index
            if word in _NEGATIONS or word.endswith("n't"):
                if step > 0:  # The main scanner already counted negation before the noun.
                    sign *= -1
            elif word not in _RATE_LINK or (step > 0 and word in {"to", "by", "on", "in"}):
                break
    return None


def _features(text: str) -> dict[str, int]:
    counts: Counter[str] = Counter()
    normalized = _normalize(text.strip())
    tax_names: set[str] = set()
    changes: dict[str, list[tuple[int, int]]] = defaultdict(list)
    for clause in _CLAUSE.split(normalized):
        clause = _LABEL.sub("", clause.strip())
        clause = re.sub(r"\badvis(?:e|es|ed|ing) [^,;]{1,80}? to\b", "", clause)
        clause = _ASSESSED_LEVY.sub(r"\1 property tax", clause)
        # Keep the underlying revenue source, e.g. "existing sales tax receipts".
        clause = _EXISTING_REVENUE.sub(lambda m: (m[1] or "") + "existing revenue", clause)
        clause = _ALLOCATE.sub(lambda m: "allocate revenue " + (m[1] or "") +
                               ("existing revenue" if m[2] == "existing revenue" else ""), clause)
        tokens = _words(clause)
        words = [word for word, _ in tokens]
        # Take the adjacent noun from the text, regardless of the policy area.
        # "Payroll tax" identifies a base; "raise tax" and "tax relief" do not.
        bases = {m.end(): m[1] for m in _BASE.finditer(clause) if m[1] not in _NON_BASE}
        sign, previous, allocating = 1, "", False
        named_moves: set[int] = set()
        unqualified_rates = {}
        for index, word in enumerate(words):
            if word in _OPPOSE or word in _NEGATIONS or word.endswith("n't"):
                sign, previous = -sign, ""
                if word == "without":
                    allocating = False
                continue
            if word in _SUPPORT or word in _STOP:
                if word in {"and", "or"}:
                    previous = ""
                continue
            if word == "allocate revenue":
                # In "impose a tax, using its revenue ...", the main decision is
                # the levy. Only mark an earmark when it governs this clause.
                if previous:
                    continue
                allocating = True
            term = _singular(word)
            counts[term] += sign
            pair = f"{previous} {term}"
            if previous and previous != term and not (allocating and pair == "new levy"):
                counts[pair] += sign
            previous = term
            tax_name = None
            first = index
            if word in {"property tax", "property transfer tax"}:
                tax_name = word
                counts["property tax base"] += sign
            elif word in {"tax", "taxes"}:
                base = bases.get(tokens[index][1])
                tax_name = f"{_singular(base)} tax" if base else "tax"
                if base:
                    counts[f"{tax_name} base"] += sign
                    first -= 1
            bare_rate = word in {"rate", "rates"} and (
                index == 0 or words[index - 1] in _RATE_PREFIX
            )
            if not allocating and (tax_name or bare_rate):
                if tax_name:
                    tax_names.add(tax_name)
                movement = _rate_move(words, first, index)
                if movement:
                    direction, action_index = movement
                    if tax_name:
                        named_moves.add(action_index)
                        changes[tax_name].append((direction, sign))
                    else:
                        unqualified_rates[action_index] = (direction, sign)
            if word in _FISCAL and not allocating and (
                _LEVY.intersection(words[max(0, index - 4):index])
                or words[index + 1:index + 2] in (["increase"], ["hike"], ["surcharge"])
            ):
                counts["new levy"] += sign
        # A bracket may say only "lower the rate below $X" after naming its
        # tax in the introduction. Do not guess a base in a multi-tax packet.
        changes[""].extend(move for index, move in unqualified_rates.items() if index not in named_moves)
    anonymous = changes.pop("", [])
    named = tax_names - {"tax"} or tax_names
    if len(named) == 1:
        changes[next(iter(named))].extend(anonymous)
    for name, moves in changes.items():
        signed = {direction * stance for direction, stance in moves}
        physical = {direction for direction, _ in moves}
        tiered = len(physical) > 1 and _TIER.search(normalized)
        if tiered or len(signed) > 1:
            # Several brackets do not establish the direction of the tax as a
            # whole, even if more brackets rise than fall.
            stance = moves[0][1]
            if head := _TIER_STANCE.match(_LABEL.sub("", normalized)):
                stance = (1 if head[2].startswith("support") else -1) * (-1 if head[1] else 1)
            counts[f"{name} mixed rates"] = stance
            if len(named) == 1:
                counts.pop("new levy", None)
        elif signed:
            counts[f"{name} rate change"] = signed.pop()
    return {term: 1 if value > 0 else -1 for term, value in counts.items() if value}


def content_features(text: str) -> dict[str, int]:
    """Content words and local phrases from a reason, title or packet."""
    return _features(text)


def outcome_features(text: str) -> dict[str, int]:
    """A positive term describes an endorsed effect, independently of the YES/NO label."""
    return _features(text)


def outcome_difference(measure: JournalMeasure) -> dict[str, int]:
    yes, no = outcome_features(measure.yesMeaning), outcome_features(measure.noMeaning)
    difference = {term: diff for term in yes.keys() | no.keys()
                  if (diff := yes.get(term, 0) - no.get(term, 0))}
    yes_action = _ADOPTION.fullmatch(_LABEL.sub("", _normalize(measure.yesMeaning).strip()))
    no_action = _ADOPTION.fullmatch(_LABEL.sub("", _normalize(measure.noMeaning).strip()))
    if yes_action and no_action:
        positive = {"approve", "adopt", "pass", "support"}
        direction = int(yes_action[1] in positive) - int(no_action[1] in positive)
        # In an up/down vote, the proposition can be the only place the action
        # is described. Use a single proposition, never a mixed backgrounder.
        body = measure.text.strip()
        clauses = [part for part in _CLAUSE.split(body.casefold()) if part.strip()]
        if direction and len(clauses) == 1 and not re.search(
            r"\b(?:status quo|current law|currently|yes vote|no vote|opponents|supporters)\b", body, re.I
        ):
            return {term: 2 * direction * value for term, value in outcome_features(body).items()}
        return {}
    return difference

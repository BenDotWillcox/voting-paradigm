from uuid import UUID

import pytest

from preferences.journal_forecast import JournalMeasure, JournalRequest, PastDecision
from preferences.journal_reasoning_v2 import paired_forecast, ranked_cases, reasoning_forecast


def ballot(title, proposal):
    return JournalMeasure(
        title=title, sourceUrl="https://example.org/measure", text=proposal, familiar=False,
        yesMeaning=f'A “yes” vote supported {proposal}.', noMeaning=f'A “no” vote opposed {proposal}.',
    )


def previous(number, measure, vote, note):
    return PastDecision(id=UUID(int=number), measure=measure, vote=vote, reasoning=note)


def forecast(target, history):
    return paired_forecast(JournalRequest(id=UUID(int=8), measure=target, history=history))


def reversed_meanings(measure):
    return measure.model_copy(update={"yesMeaning": measure.noMeaning, "noMeaning": measure.yesMeaning})


def test_a_charge_and_an_unrelated_rule_in_the_same_city_supply_no_evidence():
    previous_fee = previous(1, ballot("Annual license", "imposing a city license fee for tow trucks"),
                            "yes", "The fees help pay for inspections.")
    target = ballot("Riverbend decision", "adopting a city rule on secret bidding")
    assert ranked_cases(target, [previous_fee]) == []
    assert forecast(target, [previous_fee]).reasoning.probabilityYes == .5


def test_tax_creation_and_revenue_allocation_with_the_same_recipient():
    earmark = previous(1, ballot("Receipts", "allocating revenue from a payroll tax to harbor dredging"),
                       "yes", "I support harbor dredging.")
    levy = previous(2, ballot("Levy", "imposing a payroll tax to fund harbor dredging"),
                    "no", "I oppose the payroll tax.")
    targets = (("using proceeds from a payroll tax to fund harbor dredging", earmark, "yes"),
               ("establishing a new payroll tax for harbor dredging", levy, "no"))
    for proposal, expected, vote in targets:
        target = ballot("New decision", proposal)
        pair = forecast(target, [earmark, levy])
        assert ranked_cases(target, [earmark, levy])[0].item.id == expected.id
        assert pair.reasoning.choice == pair.withoutReasoning.choice == vote
        flipped = forecast(reversed_meanings(target), [earmark, levy])
        assert flipped.reasoning.probabilityYes == pytest.approx(1 - pair.reasoning.probabilityYes)


def test_authorizing_income_tax_and_spending_existing_receipts_without_new_tax():
    levy = previous(1, ballot("Harbor facilities", "establishing an income tax surcharge for commuter ferries"),
                    "yes", "I support establishing an income tax surcharge for commuter ferries.")
    target = ballot("Harbor operating budget",
                    "using existing revenues from the income tax surcharge for commuter ferries without a new levy")
    for measure in (target, reversed_meanings(target)):
        assert ranked_cases(measure, [levy]) == []


def test_same_tax_different_purpose_changes_the_precedent_and_vote():
    habitat = previous(1, ballot("Habitat", "raising a parcel tax for river restoration"),
                       "yes", "I support river restoration.")
    races = previous(2, ballot("Races", "raising a parcel tax for a racing grandstand"),
                     "no", "I oppose the racing grandstand.")
    for purpose, expected in [("river restoration", habitat), ("a racing grandstand", races)]:
        target = ballot("Annual parcel charge", f"imposing a parcel tax for {purpose}")
        pair = forecast(target, [habitat, races])
        assert ranked_cases(target, [habitat, races])[0].item.id == expected.id
        assert pair.reasoning.choice == expected.vote
        assert expected.reasoning in pair.reasoning.explanation
        assert abs(pair.reasoning.probabilityYes - .5) > abs(pair.withoutReasoning.probabilityYes - .5)


@pytest.mark.parametrize("restriction", ["only for marsh restoration", "only if it funds marsh restoration"])
def test_an_explicit_requirement_in_a_yes_reason_blocks_transfer_to_another_use(restriction):
    old = ballot("Waterways", "imposing a parcel tax for marsh restoration")
    prior = previous(1, old, "yes", f"I support a parcel tax {restriction}.")
    same = ballot("Restoration grant", "increasing a parcel tax for marsh restoration")
    assert forecast(same, [prior]).reasoning.probabilityYes > .5
    changed = ballot("Arena", "increasing a parcel tax for an arena")
    for measure in (changed, reversed_meanings(changed)):
        result = forecast(measure, [prior])
        assert result.reasoning.probabilityYes == .5
        assert result.withoutReasoning.probabilityYes != .5


def test_only_before_support_also_limits_a_stated_tax_preference():
    old = ballot("Lunches", "increasing the property tax rate to fund school lunches")
    prior = previous(1, old, "yes", "I only support higher property taxes for school lunches.")
    stadium = ballot("Stadium", "increasing the property tax rate to fund the stadium")
    for measure in (stadium, reversed_meanings(stadium)):
        pair = forecast(measure, [prior])
        assert pair.reasoning.probabilityYes == .5
        assert pair.withoutReasoning.probabilityYes != .5


@pytest.mark.parametrize("vote,stance,cut_vote", [("yes", "favor", "no"), ("no", "oppose", "yes")])
def test_a_preference_about_higher_taxes_reverses_for_a_rate_cut(vote, stance, cut_vote):
    increase = ballot("Rate", "increasing the property tax rate")
    prior = previous(1, increase, vote, f"I {stance} higher property taxes.")
    cut = ballot("Change", "decreasing the property tax rate")
    pair = forecast(cut, [prior])
    assert pair.reasoning.choice == pair.withoutReasoning.choice == cut_vote
    assert prior.reasoning in pair.reasoning.explanation
    assert abs(pair.reasoning.probabilityYes - .5) > abs(pair.withoutReasoning.probabilityYes - .5)
    flipped = forecast(reversed_meanings(cut), [prior])
    assert flipped.reasoning.probabilityYes == pytest.approx(1 - pair.reasoning.probabilityYes)


def test_a_mixed_rate_change_has_no_directional_match_to_a_simple_increase():
    mixed = ballot("Tiers", "lowering the payroll tax rate on small companies and raising the payroll tax rate on large companies")
    increase = ballot("Rate", "raising the payroll tax rate")
    assert forecast(increase, [previous(1, mixed, "yes", "")]).reasoning.probabilityYes == .5
    assert forecast(mixed, [previous(1, increase, "yes", "I favor higher payroll taxes.")]).reasoning.probabilityYes == .5


def test_a_beneficiary_can_matter_independently_of_the_change_in_tax_rate():
    original = ballot("Waterways", "increasing the parcel tax for marsh restoration")
    lower = ballot("Restoration budget", "decreasing the parcel tax and funding marsh restoration")
    prior = previous(1, original, "yes", "I support marsh restoration.")
    result = forecast(lower, [prior])
    assert result.reasoning.probabilityYes > result.withoutReasoning.probabilityYes
    assert "marsh restoration" in result.reasoning.explanation


def test_substantive_non_tax_preference_transfers_both_polarities_without_case_length_penalty():
    old = ballot("Energy", "extending geothermal power permits")
    target = ballot("Transit", "requiring independent audits for a ferry")
    for stance, expected in [("support", "yes"), ("oppose", "no")]:
        note = f"I {stance} independent audits."
        case = previous(1, old, "yes", note)
        direct = forecast(target, [case])
        assert direct.reasoning.choice == expected
        assert direct.withoutReasoning.probabilityYes == .5
        assert note in direct.reasoning.explanation
        case.reasoning += " My neighbor uses a bicycle on weekends." * 12
        assert forecast(target, [case]).reasoning.probabilityYes == direct.reasoning.probabilityYes
        case.reasoning = f"I {stance} independent audits only if qualified specialists are available."
        assert ranked_cases(target, [case]) == []


def test_two_stated_views_in_one_reason_each_keep_their_own_direction():
    unrelated = ballot("Charter", "adding a deputy clerk")
    case = previous(1, unrelated, "yes", "I support longer library hours, but I oppose bridge tolls.")
    for proposal, vote in [("extending library hours", "yes"), ("imposing bridge tolls", "no")]:
        target = ballot("Proposal", proposal)
        assert forecast(target, [case]).reasoning.choice == vote


@pytest.mark.parametrize("base", ["property", "payroll"])
def test_relating_two_levies_by_the_same_tax_base_survives_different_uses(base):
    old = ballot("Maintenance", f"increasing the {base} tax to repair pipes in the harbor")
    new = ballot("Night school", f"imposing a {base} tax to maintain night classes for carpenters")
    for vote in ("yes", "no"):
        case = previous(1, old, vote, "")
        assert ranked_cases(new, [case])[0].item.id == case.id
        assert forecast(new, [case]).reasoning.choice == vote


def test_quote_representing_a_reservation_is_not_presented_as_endorsing_the_net_forecast():
    earlier = ballot("Habitat", "raising a parcel tax for river restoration and wildlife corridors")
    case = previous(1, earlier, "yes", "I oppose the parcel tax.")
    result = reasoning_forecast(JournalRequest(id=UUID(int=8), measure=earlier, history=[case]))
    assert result.choice == "yes"
    assert "written reason points toward No" in result.explanation

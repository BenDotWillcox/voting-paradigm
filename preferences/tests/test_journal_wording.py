"""Synthetic polarity and tax-base cases, independent of the private journal."""

from types import SimpleNamespace

import pytest

from preferences.journal_wording import content_features, outcome_difference, outcome_features


@pytest.mark.parametrize("prefix", [
    'A "yes" vote supported', "A ‘yes’ vote supports", "A YES vote would allow",
    'Voting "yes" means adopting', "Yes: approve", "Yes —", "A “no” supported",
])
def test_effect_is_independent_of_procedural_label(prefix):
    assert outcome_features(f"{prefix} neighborhood gardens") == outcome_features("neighborhood gardens")


@pytest.mark.parametrize(("description", "direction"), [
    ('A "no" opposed authorizing night markets', -1),
    ("A no vote supports a ban on night markets", -1),
    ("Yes: repeal the ban on night markets", 1),
    ("No: do not repeal the ban on night markets", -1),
    ('A “no” vote opposes repealing the ban on night markets', -1),
    ("Without repealing a ban on night markets", -1),
    ("No change to the ban on night markets", -1),
    ("No night markets", -1),
])
def test_effect_retains_policy_polarity(description, direction):
    assert outcome_features(description)["night market"] == direction


def test_alternative_clause_has_its_own_stance_and_swapping_negates_the_contrast():
    yes = 'A “yes” vote supported electric ferries instead of diesel boats.'
    no = 'A “no” opposed electric ferries, thereby maintaining diesel boats.'
    assert outcome_features(yes)["diesel boat"] == -1
    assert outcome_features(no)["diesel boat"] == 1
    assert outcome_features(no)["electric ferry"] == -1
    forward = outcome_difference(SimpleNamespace(yesMeaning=yes, noMeaning=no))
    reverse = outcome_difference(SimpleNamespace(yesMeaning=no, noMeaning=yes))
    assert reverse == {term: -value for term, value in forward.items()}
    assert forward["electric ferry"] == 2 and forward["diesel boat"] == -2


def test_geography_and_ballot_form_do_not_make_unrelated_measures_overlap():
    first = outcome_features('A "yes" vote supported adopting city compost collection.')
    second = outcome_features('A "no" vote opposed adopting city harbor rules.')
    assert first.keys().isdisjoint(second)
    election = outcome_features("Use cumulative voting in the City of Hazel Cove")
    pool = outcome_features("Close the swimming pool within the City of Hazel Cove")
    assert election.keys().isdisjoint(pool)
    assert outcome_features("Protect Hazel Cove Wildlife Refuge")["hazel cove"] == 1


def test_an_explicit_second_action_ends_the_scope_of_negation():
    effects = outcome_features("Would not raise income taxes and would fund libraries")
    assert effects["income tax"] == effects["new levy"] == -1
    assert effects["fund library"] == 1


def test_written_acronym_is_available_on_later_short_form_ballots():
    full = outcome_features("Adopt demand responsive transit (DRT)")
    reversed_short = outcome_features("Abolish DRT")
    assert full["drt"] == -reversed_short["drt"] == 1


def test_bare_approval_uses_the_proposition_only_for_unambiguous_up_or_down_votes():
    measure = SimpleNamespace(yesMeaning="Approve this proposal", noMeaning="Reject this proposal",
                              text="Shall the city prohibit nighttime deliveries?")
    assert outcome_difference(measure)["nighttime delivery"] == -2
    measure.noMeaning, measure.yesMeaning = measure.yesMeaning, measure.noMeaning
    assert outcome_difference(measure)["nighttime delivery"] == 2
    measure.text = "The current law prohibits nighttime deliveries. The measure would allow them."
    assert not outcome_difference(measure)
    measure.yesMeaning, measure.noMeaning = "Authorize tideside docks", "Reject tideside docks"
    assert "nighttime delivery" not in outcome_difference(measure)


def test_tax_base_is_distinct_from_the_benefit_and_from_merely_mentioning_land():
    land = outcome_features("Raise the real estate tax to restore the harbor")
    transfer = outcome_features("Change the tax on property transfers")
    other = outcome_features("Establish an income tax surcharge to fund property tax relief")
    assert land["new levy"] == land["property tax"] == land["property tax base"] == 1
    assert transfer["property transfer tax"] == transfer["property tax base"] == 1
    assert "property tax" not in transfer
    assert other["income tax"] == other["new levy"] == other["property tax relief"] == 1
    assert {"property tax base", "property tax"}.isdisjoint(other)
    assert "property tax base" not in outcome_features("Create a fund to acquire real estate")
    assert outcome_features("No tax rebates")["tax rebate"] == -1
    assert content_features("I prefer a levy on real property")["property tax base"] == 1
    assert outcome_features("An increase of 0.03% of the assessed value of all property")["property tax base"] == 1


@pytest.mark.parametrize("base", ["payroll", "sales", "lodging", "beacon"])
def test_an_open_vocabulary_tax_base_is_shared_between_measures(base):
    introduced = outcome_features(f"Establish a {base} tax to fund marinas")
    declined = outcome_features(f"Reject a {base} tax for water storage")
    assert introduced[f"{base} tax base"] == -declined[f"{base} tax base"] == 1
    unrelated_base = outcome_features(f"Raise a parking tax to fund {base} tax rebates")
    assert unrelated_base["parking tax base"] == 1
    assert f"{base} tax base" not in unrelated_base and f"{base} tax" not in unrelated_base
    assert not any(term.endswith(" tax base") for term in outcome_features("Raise taxes"))


def test_allocating_receipts_and_imposing_a_levy_have_different_effects():
    allocation = outcome_features("A yes vote supported using revenue from a proposed payroll tax surcharge")
    levy = outcome_features("A yes vote supported imposing a payroll tax surcharge, using the revenue for piers")
    assert allocation["allocate revenue"] == levy["new levy"] == 1
    assert "new levy" not in allocation and "existing revenue" not in allocation
    assert "new levy" not in outcome_features("Use revenue from a new levy for the pier")
    assert "allocate revenue" not in levy
    existing = outcome_features("Allocate existing funds without a new levy")
    assert existing["allocate revenue"] == existing["existing revenue"] == 1
    assert existing["new levy"] == -1
    existing = outcome_features("Use existing sales tax revenue without raising taxes")
    assert existing["allocate revenue"] == existing["existing revenue"] == existing["sales tax"] == 1
    assert existing["new levy"] == -1
    plural = outcome_features("Direct current revenues to the harbor")
    assert plural["existing revenue"] == plural["allocate revenue"] == 1


@pytest.mark.parametrize(("description", "direction"), [
    ("Increase the property tax rate", 1),
    ("A lower real estate tax", -1),
    ("A higher rate of property tax", 1),
    ("A yes vote would support a cut to the property tax", -1),
    ("A no vote would oppose reducing the property tax", 1),
    ("The property tax would not be increased", -1),
    ("Do not reject lowering the property tax", -1),
])
def test_named_rate_direction_preserves_operative_negation(description, direction):
    assert outcome_features(description)["property tax rate change"] == direction


def test_different_bases_can_move_oppositely_and_label_reversal_is_exact():
    measure = SimpleNamespace(yesMeaning="Raise lodging taxes and cut payroll taxes",
                              noMeaning="Keep the existing rates")
    before = outcome_difference(measure)
    assert before["lodging tax rate change"] == 1
    assert before["payroll tax rate change"] == -1
    measure.noMeaning, measure.yesMeaning = measure.yesMeaning, measure.noMeaning
    assert outcome_difference(measure) == {term: -value for term, value in before.items()}


def test_mixed_tiers_do_not_become_a_directional_change_by_counting_brackets():
    ballot = ("Change the property transfer tax: lower the rate for transfers below the threshold; "
              "raise the rate in the middle bracket; raise the rate in the top bracket.")
    result = outcome_features(ballot)
    assert result["property transfer tax mixed rates"] == 1
    assert "property transfer tax rate change" not in result and "new levy" not in result
    opposed = outcome_features('A “no” vote opposed these changes to the property transfer tax:\n'
                               'cut rates below the threshold; raise rates above it.')
    assert opposed["property transfer tax mixed rates"] == -1


def test_an_increase_in_service_is_not_an_increase_in_the_underlying_tax():
    result = outcome_features("Use revenue from a lodging tax to increase clinic hours")
    assert not any(term.endswith("rate change") for term in result)
    result = outcome_features("Use the lodging tax to cut waiting times")
    assert "lodging tax rate change" not in result

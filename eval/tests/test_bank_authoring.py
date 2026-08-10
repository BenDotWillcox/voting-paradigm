"""Tests for Phase 3B source, batch, assembly, and review artifacts."""

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from eval.bank_authoring import (
    ContentTraceRecord,
    ConstructedAssumptionRecord,
    DomainBankBatch,
    DomainBankBatchItem,
    MeasureSourceEvidence,
    SourceCaptureRecord,
    SourceCaptureRole,
    SourceContentHashScope,
    assemble_final_fixture,
    source_content_sha256,
    validate_domain_bank_batch,
    validate_measure_source_evidence,
)
from eval.bank_profile import ReviewActorType, load_bank_profile
from eval.build_final_bank import main as build_final_bank_main
from eval.contracts import (
    BallotType,
    GeneralizationTier,
    MeasureDomain,
    MeasureOption,
    MeasurePacket,
    MeasureSourceKind,
    MeasureVersion,
    ResponseField,
    SourceRecord,
)
from eval.fixture_io import content_sha256, load_fixture
from eval.review_artifacts import (
    PHASE3_PACKET_REVIEW_PROMPT_SHA256,
    DomainBatchReviewLog,
    MeasureReviewApproval,
    PacketReviewCategory,
    PacketReviewFinding,
    ReviewFindingDisposition,
    ReviewFindingSeverity,
    bank_review_ledger_entries_for_batch,
    build_nonrevealing_review_summary,
    canonical_text_sha256,
    packet_review_record_for_measure,
    validate_domain_batch_review_log,
    validate_locked_review_prompt,
)
from eval.validate_batch_review import main as validate_batch_review_main
from eval.validate_domain_batch import main as validate_domain_batch_main

PROFILE_PATH = (
    Path(__file__).parents[1]
    / "fixtures"
    / "preference_eval_bank_profile_v1.json"
)
NOW = datetime(2026, 7, 31, 12, 0, tzinfo=timezone.utc)
PLANTED_RESTRICTED_TEXT = (
    "RESTRICTED_PACKET_DETAIL_9173 should never enter the safe summary"
)
PLANTED_ASSUMPTION_TEXT = (
    "RESTRICTED_ASSUMPTION_DETAIL_4021 must remain participant-blind"
)


def _source_records(
    slot_id: str,
    count: int,
) -> list[SourceRecord]:
    return [
        SourceRecord(
            source_id=f"{slot_id}_source_{index}",
            title=f"Source {index} for {slot_id}",
            publisher=f"Meridian source publisher {index}",
            url=f"https://example.gov/{slot_id}/{index}",
            accessed_date=NOW.date(),
            adaptation_notes=(
                "Synthetic source provenance for Phase 3B contract tests."
            ),
        )
        for index in range(count)
    ]


def _measure_for_slot(slot) -> MeasureVersion:
    option_count = (
        2 if slot.ballot_type is BallotType.SINGLE_CHOICE else 3
    )
    options = [
        MeasureOption(
            option_id=f"{slot.slot_id}_option_{index}",
            label=f"Option {index + 1}",
            description=f"Test option {index + 1} for {slot.slot_id}.",
            display_order=index,
        )
        for index in range(option_count)
    ]
    source_count = (
        2
        if slot.source_kind
        is MeasureSourceKind.REAL_WORLD_ANCHORED
        else 1
    )
    response_fields = (
        [ResponseField.TOP_CHOICE]
        if slot.ballot_type is BallotType.SINGLE_CHOICE
        else (
            [ResponseField.QUADRATIC]
            if slot.ballot_type is BallotType.QUADRATIC
            else [
                ResponseField.TOP_CHOICE,
                ResponseField.RANKING,
                ResponseField.APPROVAL,
                ResponseField.SCORES,
            ]
        )
    )
    packet = MeasurePacket(
        packet_id=f"{slot.slot_id}_packet",
        version=1,
        status_quo=f"Current synthetic policy for {slot.slot_id}.",
        proposal=f"Proposed synthetic change for {slot.slot_id}.",
        who_is_affected="Residents represented in the test fixture.",
        fiscal_or_operational_effects=(
            "A documented synthetic implementation effect."
        ),
        arguments_by_option={
            option.option_id: f"Argument for {option.option_id}."
            for option in options
        },
        uncertainties=["The synthetic estimate remains uncertain."],
        definitions={"test term": "A definition used only by this test."},
        sources=_source_records(slot.slot_id, source_count),
        authored_at=NOW,
    )
    return MeasureVersion(
        measure_id=f"measure_{slot.slot_id}",
        version=1,
        title=f"Measure for {slot.slot_id}",
        domain=slot.domain,
        ballot_type=slot.ballot_type,
        response_fields=response_fields,
        source_kind=slot.source_kind,
        intended_generalization_tier=(
            slot.intended_generalization_tier
        ),
        options=options,
        packet=packet,
        quadratic_credit_budget=(
            100 if slot.ballot_type is BallotType.QUADRATIC else None
        ),
        quadratic_allow_negative=(
            False if slot.ballot_type is BallotType.QUADRATIC else None
        ),
    )


def _source_evidence(measure: MeasureVersion) -> MeasureSourceEvidence:
    captures = [
        SourceCaptureRecord(
            source_id=source.source_id,
            source_record_sha256=content_sha256(source),
            source_role=(
                SourceCaptureRole.PRIMARY_OFFICIAL
                if (
                    measure.source_kind
                    is MeasureSourceKind.REAL_WORLD_ANCHORED
                    and index == 0
                )
                else SourceCaptureRole.INDEPENDENT_CONTEXT
            ),
            captured_at=NOW,
            retrieved_content_sha256=content_sha256(
                {"source_id": source.source_id, "test_content": True}
            ),
            content_hash_scope=(
                SourceContentHashScope.RETRIEVED_DOCUMENT_BYTES
            ),
            locator_notes="Synthetic document section used by the test.",
        )
        for index, source in enumerate(measure.packet.sources)
    ]
    constructed_assumptions = (
        [
            ConstructedAssumptionRecord(
                assumption_id=f"{measure.measure_id}_controlled_assumption",
                statement=PLANTED_ASSUMPTION_TEXT,
                selection_rationale=(
                    "The contract test needs an explicit constructed ground."
                ),
                calibration_source_ids=[
                    measure.packet.sources[0].source_id
                ],
            )
        ]
        if measure.source_kind is MeasureSourceKind.CONSTRUCTED
        else []
    )
    content_traces = [
        ContentTraceRecord(
            trace_id=f"{measure.measure_id}_status_quo",
            content_path="/packet/status_quo",
            adapted_text=measure.packet.status_quo,
            source_ids=[
                source.source_id
                for source in measure.packet.sources
            ],
            adaptation_notes=(
                "The exact test status quo is traced to every packet "
                "source."
            ),
        )
    ]
    if constructed_assumptions:
        content_traces.append(
            ContentTraceRecord(
                trace_id=f"{measure.measure_id}_proposal_assumption",
                content_path="/packet/proposal",
                adapted_text=measure.packet.proposal,
                constructed_assumption_ids=[
                    constructed_assumptions[0].assumption_id
                ],
                adaptation_notes=(
                    "The synthetic proposal is grounded in the explicit "
                    "controlled assumption."
                ),
            )
        )
    return MeasureSourceEvidence(
        measure_id=measure.measure_id,
        measure_version=measure.version,
        measure_sha256=content_sha256(measure),
        source_captures=captures,
        constructed_assumptions=constructed_assumptions,
        content_traces=content_traces,
    )


def _domain_batches():
    profile = load_bank_profile(PROFILE_PATH)
    batches = []
    for domain in MeasureDomain:
        items = []
        for slot in profile.slots:
            if slot.domain is not domain:
                continue
            measure = _measure_for_slot(slot)
            items.append(
                DomainBankBatchItem(
                    slot_id=slot.slot_id,
                    measure=measure,
                    source_evidence=_source_evidence(measure),
                )
            )
        batches.append(
            DomainBankBatch(
                batch_id=f"{domain.value}_batch",
                batch_version=1,
                profile_id=profile.profile_id,
                profile_version=profile.profile_version,
                profile_sha256=content_sha256(profile),
                domain=domain,
                authored_at=NOW,
                items=items,
            )
        )
    return profile, batches


def _review_log(
    batch: DomainBankBatch,
    profile,
) -> DomainBatchReviewLog:
    first = batch.items[0].measure
    finding = PacketReviewFinding(
        finding_id="review_finding_one",
        measure_id=first.measure_id,
        measure_version=first.version,
        category=PacketReviewCategory.CONTEXTUAL_SUFFICIENCY,
        severity=ReviewFindingSeverity.MAJOR,
        finding_text=PLANTED_RESTRICTED_TEXT,
        disposition=ReviewFindingDisposition.RESOLVED,
        resolution_notes=(
            f"Resolved without exposing {PLANTED_RESTRICTED_TEXT}."
        ),
    )
    return DomainBatchReviewLog(
        log_id=f"{batch.batch_id}_review",
        log_version=1,
        profile_id=profile.profile_id,
        profile_version=profile.profile_version,
        profile_sha256=content_sha256(profile),
        batch_id=batch.batch_id,
        batch_version=batch.batch_version,
        batch_sha256=content_sha256(batch),
        reviewer_type=ReviewActorType.AI,
        reviewer_system="claude",
        reviewer_model_version="claude-review-test",
        review_prompt_sha256=PHASE3_PACKET_REVIEW_PROMPT_SHA256,
        completed_at=NOW + timedelta(days=1),
        findings=[finding],
        measure_approvals=[
            MeasureReviewApproval(
                measure_id=item.measure.measure_id,
                measure_version=item.measure.version,
                measure_sha256=content_sha256(item.measure),
                findings_count=(
                    1 if item.measure.measure_id == first.measure_id else 0
                ),
                completed_checks=list(PacketReviewCategory),
                approved=True,
            )
            for item in batch.items
        ],
    )


def test_eight_domain_batches_assemble_in_frozen_slot_order():
    profile, batches = _domain_batches()

    fixture = assemble_final_fixture(
        profile,
        list(reversed(batches)),
        fixture_id="preference_eval_final_test_v1",
        fixture_version=1,
        created_at=NOW + timedelta(days=2),
    )

    assert len(fixture.measures) == 48
    assert [
        measure.measure_id.removeprefix("measure_")
        for measure in fixture.measures
    ] == [slot.slot_id for slot in profile.slots]
    assert not fixture.development_only


def test_source_evidence_rejects_adapted_text_drift():
    _, batches = _domain_batches()
    item = batches[0].items[0]
    trace = item.source_evidence.content_traces[0].model_copy(
        update={"adapted_text": "Drifted participant-facing text."}
    )
    drifted = item.source_evidence.model_copy(
        update={"content_traces": [trace]}
    )

    with pytest.raises(ValueError, match="exact adapted text"):
        validate_measure_source_evidence(drifted, item.measure)


def test_source_content_hashing_has_explicit_stable_scopes():
    assert source_content_sha256(
        "Line one\r\nCaf\u00e9\rLine two",
        SourceContentHashScope.NORMALIZED_RELEVANT_TEXT_UTF8,
    ) == source_content_sha256(
        "Line one\nCafe\u0301\nLine two",
        SourceContentHashScope.NORMALIZED_RELEVANT_TEXT_UTF8,
    )
    assert source_content_sha256(
        b"raw-document-bytes",
        SourceContentHashScope.RETRIEVED_DOCUMENT_BYTES,
    ) == (
        "3004e3fb4f15669f59d11067bf5bdfdf"
        "7c9e2e114b1932225c75a5b03646edfc"
    )

    with pytest.raises(TypeError, match="requires bytes"):
        source_content_sha256(
            "not bytes",
            SourceContentHashScope.RETRIEVED_DOCUMENT_BYTES,
        )


def test_source_evidence_rejects_a_decorative_untraced_source():
    _, batches = _domain_batches()
    item = next(
        candidate
        for candidate in batches[0].items
        if len(candidate.measure.packet.sources) == 2
    )
    trace = item.source_evidence.content_traces[0].model_copy(
        update={
            "source_ids": [
                item.measure.packet.sources[0].source_id,
            ]
        }
    )
    incomplete = item.source_evidence.model_copy(
        update={"content_traces": [trace]}
    )

    with pytest.raises(ValueError, match="every packet source"):
        validate_measure_source_evidence(incomplete, item.measure)


def test_constructed_measure_requires_an_explicit_assumption():
    _, batches = _domain_batches()
    item = next(
        candidate
        for candidate in batches[0].items
        if candidate.measure.source_kind is MeasureSourceKind.CONSTRUCTED
    )
    invalid = item.source_evidence.model_copy(
        update={"constructed_assumptions": []}
    )

    with pytest.raises(ValueError, match="explicit constructed assumption"):
        validate_measure_source_evidence(invalid, item.measure)


def test_source_evidence_rejects_an_unknown_constructed_assumption():
    _, batches = _domain_batches()
    item = next(
        candidate
        for candidate in batches[0].items
        if candidate.measure.source_kind is MeasureSourceKind.CONSTRUCTED
    )
    proposal_trace = item.source_evidence.content_traces[1].model_copy(
        update={
            "constructed_assumption_ids": ["unknown_assumption"]
        }
    )
    invalid = item.source_evidence.model_copy(
        update={
            "content_traces": [
                item.source_evidence.content_traces[0],
                proposal_trace,
            ]
        }
    )

    with pytest.raises(ValueError, match="unknown constructed assumptions"):
        validate_measure_source_evidence(invalid, item.measure)


def test_source_evidence_rejects_a_decorative_assumption():
    _, batches = _domain_batches()
    item = next(
        candidate
        for candidate in batches[0].items
        if candidate.measure.source_kind is MeasureSourceKind.CONSTRUCTED
    )
    invalid = item.source_evidence.model_copy(
        update={"content_traces": [item.source_evidence.content_traces[0]]}
    )

    with pytest.raises(ValueError, match="every constructed assumption"):
        validate_measure_source_evidence(invalid, item.measure)


def test_source_evidence_rejects_unknown_assumption_calibration_source():
    _, batches = _domain_batches()
    item = next(
        candidate
        for candidate in batches[0].items
        if candidate.measure.source_kind is MeasureSourceKind.CONSTRUCTED
    )
    assumption = item.source_evidence.constructed_assumptions[0].model_copy(
        update={"calibration_source_ids": ["unknown_source"]}
    )
    invalid = item.source_evidence.model_copy(
        update={"constructed_assumptions": [assumption]}
    )

    with pytest.raises(ValueError, match="unknown calibration sources"):
        validate_measure_source_evidence(invalid, item.measure)


def test_source_evidence_rejects_duplicate_constructed_assumptions():
    _, batches = _domain_batches()
    item = next(
        candidate
        for candidate in batches[0].items
        if candidate.measure.source_kind is MeasureSourceKind.CONSTRUCTED
    )
    assumption = item.source_evidence.constructed_assumptions[0]

    with pytest.raises(ValidationError, match="assumption ids must be unique"):
        MeasureSourceEvidence(
            measure_id=item.measure.measure_id,
            measure_version=item.measure.version,
            measure_sha256=content_sha256(item.measure),
            source_captures=item.source_evidence.source_captures,
            constructed_assumptions=[assumption, assumption],
            content_traces=item.source_evidence.content_traces,
        )


def test_traced_assumption_can_bind_its_calibration_source():
    _, batches = _domain_batches()
    item = next(
        candidate
        for candidate in batches[0].items
        if candidate.measure.source_kind is MeasureSourceKind.CONSTRUCTED
    )
    status_quo_trace = ContentTraceRecord(
        trace_id=f"{item.measure.measure_id}_jurisdiction_status_quo",
        content_path="/packet/status_quo",
        adapted_text=item.measure.packet.status_quo,
        jurisdiction_fact_keys=["decision_baseline"],
        adaptation_notes="The test status quo uses the frozen baseline.",
    )
    evidence = item.source_evidence.model_copy(
        update={
            "content_traces": [
                status_quo_trace,
                item.source_evidence.content_traces[1],
            ]
        }
    )

    validate_measure_source_evidence(evidence, item.measure)


def test_source_evidence_rejects_unknown_assumption_jurisdiction_fact():
    profile, batches = _domain_batches()
    item = next(
        candidate
        for candidate in batches[0].items
        if candidate.measure.source_kind is MeasureSourceKind.CONSTRUCTED
    )
    assumption = item.source_evidence.constructed_assumptions[0].model_copy(
        update={"jurisdiction_fact_keys": ["unknown_fact"]}
    )
    invalid = item.source_evidence.model_copy(
        update={"constructed_assumptions": [assumption]}
    )

    with pytest.raises(ValueError, match="unknown jurisdiction facts"):
        validate_measure_source_evidence(
            invalid,
            item.measure,
            jurisdiction_fact_keys={
                fact.key for fact in profile.jurisdiction.facts
            },
        )


def test_real_world_measure_may_have_no_constructed_assumptions():
    _, batches = _domain_batches()
    item = next(
        candidate
        for candidate in batches[0].items
        if (
            candidate.measure.source_kind
            is MeasureSourceKind.REAL_WORLD_ANCHORED
        )
    )

    validate_measure_source_evidence(item.source_evidence, item.measure)


def test_authoring_v1_content_trace_is_rejected():
    _, batches = _domain_batches()
    trace = batches[0].items[0].source_evidence.content_traces[0]
    serialized = trace.model_dump(mode="json")
    serialized["record_version"] = "content_trace.v1"

    with pytest.raises(ValidationError):
        ContentTraceRecord.model_validate(serialized)


def test_authoring_v1_domain_batch_is_rejected():
    _, batches = _domain_batches()
    serialized = batches[0].model_dump(mode="json")
    serialized["schema_version"] = "preference_eval_domain_batch.v1"

    with pytest.raises(ValidationError):
        DomainBankBatch.model_validate(serialized)


def test_authoring_v1_batch_item_is_rejected():
    _, batches = _domain_batches()
    serialized = batches[0].items[0].model_dump(mode="json")
    serialized["record_version"] = (
        "preference_eval_domain_batch_item.v1"
    )

    with pytest.raises(ValidationError):
        DomainBankBatchItem.model_validate(serialized)


def test_authoring_v1_source_evidence_is_rejected():
    _, batches = _domain_batches()
    serialized = batches[0].items[0].source_evidence.model_dump(mode="json")
    serialized["record_version"] = "measure_source_evidence.v1"

    with pytest.raises(ValidationError):
        MeasureSourceEvidence.model_validate(serialized)


def test_source_evidence_rejects_tracing_source_metadata_as_packet_text():
    _, batches = _domain_batches()
    item = batches[0].items[0]
    trace = item.source_evidence.content_traces[0].model_copy(
        update={
            "content_path": (
                "/packet/sources/0/adaptation_notes"
            ),
            "adapted_text": (
                item.measure.packet.sources[0].adaptation_notes
            ),
        }
    )
    invalid = item.source_evidence.model_copy(
        update={"content_traces": [trace]}
    )

    with pytest.raises(ValueError, match="participant-facing text field"):
        validate_measure_source_evidence(invalid, item.measure)


@pytest.mark.parametrize(
    "content_path",
    [
        "/options/01/label",
        "/options/\u0661/label",
        "/packet/uncertainties/00",
    ],
)
def test_source_evidence_rejects_noncanonical_array_indices(
    content_path,
):
    _, batches = _domain_batches()
    item = batches[0].items[0]
    trace = item.source_evidence.content_traces[0].model_copy(
        update={"content_path": content_path}
    )
    invalid = item.source_evidence.model_copy(
        update={"content_traces": [trace]}
    )

    with pytest.raises(ValueError, match="participant-facing text field"):
        validate_measure_source_evidence(invalid, item.measure)


def test_domain_batch_rejects_a_wrong_slot_binding():
    profile, batches = _domain_batches()
    batch = batches[0]
    first = batch.items[0].model_copy(
        update={"slot_id": "not_a_frozen_slot"}
    )
    invalid = batch.model_copy(
        update={"items": [first, *batch.items[1:]]}
    )

    with pytest.raises(ValueError, match="six frozen domain slots"):
        validate_domain_bank_batch(invalid, profile)


def test_real_world_batch_item_requires_a_primary_official_capture():
    profile, batches = _domain_batches()
    batch = batches[0]
    item_index = next(
        index
        for index, candidate in enumerate(batch.items)
        if (
            candidate.measure.source_kind
            is MeasureSourceKind.REAL_WORLD_ANCHORED
        )
    )
    item = batch.items[item_index]
    captures = [
        capture.model_copy(
            update={
                "source_role": SourceCaptureRole.INDEPENDENT_CONTEXT,
            }
        )
        for capture in item.source_evidence.source_captures
    ]
    evidence = item.source_evidence.model_copy(
        update={"source_captures": captures}
    )
    invalid_item = item.model_copy(
        update={"source_evidence": evidence}
    )
    items = list(batch.items)
    items[item_index] = invalid_item
    invalid = batch.model_copy(update={"items": items})

    with pytest.raises(ValueError, match="primary official"):
        validate_domain_bank_batch(invalid, profile)


def test_domain_batch_rejects_measure_source_minimum_before_assembly():
    profile, batches = _domain_batches()
    batch = batches[0]
    item_index = next(
        index
        for index, candidate in enumerate(batch.items)
        if (
            candidate.measure.source_kind
            is MeasureSourceKind.REAL_WORLD_ANCHORED
        )
    )
    item = batch.items[item_index]
    packet = item.measure.packet.model_copy(
        update={"sources": item.measure.packet.sources[:1]}
    )
    measure = item.measure.model_copy(update={"packet": packet})
    trace = item.source_evidence.content_traces[0].model_copy(
        update={"source_ids": [packet.sources[0].source_id]}
    )
    evidence = item.source_evidence.model_copy(
        update={
            "measure_sha256": content_sha256(measure),
            "source_captures": (
                item.source_evidence.source_captures[:1]
            ),
            "content_traces": [trace],
        }
    )
    invalid_item = item.model_copy(
        update={"measure": measure, "source_evidence": evidence}
    )
    items = list(batch.items)
    items[item_index] = invalid_item
    invalid = batch.model_copy(update={"items": items})

    with pytest.raises(ValueError, match="at least 2 source records"):
        validate_domain_bank_batch(invalid, profile)


def test_final_assembly_rejects_a_missing_domain():
    profile, batches = _domain_batches()

    with pytest.raises(ValueError, match="one batch per domain"):
        assemble_final_fixture(
            profile,
            batches[:-1],
            fixture_id="preference_eval_final_test_v1",
            fixture_version=1,
            created_at=NOW + timedelta(days=2),
        )


def test_locked_review_prompt_matches_its_pinned_hash():
    validate_locked_review_prompt()

    assert (
        canonical_text_sha256(
            Path(__file__).parents[1]
            / "prompts"
            / "phase3_packet_review_v1.md"
        )
        == PHASE3_PACKET_REVIEW_PROMPT_SHA256
    )


def test_exact_authoring_and_source_cache_paths_are_gitignored():
    ignore_rules = set(
        (Path(__file__).parents[2] / ".gitignore")
        .read_text(encoding="utf-8")
        .splitlines()
    )

    assert "/eval/restricted_bank/" in ignore_rules
    assert ".cache/" in ignore_rules


def test_review_log_builds_a_final_ledger_record():
    profile, batches = _domain_batches()
    batch = batches[0]
    log = _review_log(batch, profile)
    first = batch.items[0].measure

    validate_domain_batch_review_log(log, batch, profile)
    approval = packet_review_record_for_measure(
        log,
        batch,
        profile,
        measure_id=first.measure_id,
        measure_version=first.version,
    )

    assert approval.findings_count == 1
    assert approval.reviewer_system == "claude"
    assert approval.disposition_log_sha256 == content_sha256(log)


def test_review_log_builds_source_classified_bank_ledger_entries():
    profile, batches = _domain_batches()
    batch = batches[0]
    log = _review_log(batch, profile)

    entries = bank_review_ledger_entries_for_batch(
        log,
        batch,
        profile,
    )

    assert len(entries) == 6
    for entry in entries:
        item = next(
            candidate
            for candidate in batch.items
            if candidate.slot_id == entry.slot_id
        )
        expected_primary_ids = [
            capture.source_id
            for capture in item.source_evidence.source_captures
            if (
                capture.source_role
                is SourceCaptureRole.PRIMARY_OFFICIAL
            )
        ]
        assert entry.primary_official_source_ids == expected_primary_ids


def test_measure_review_approval_requires_every_review_check():
    profile, batches = _domain_batches()
    raw = _review_log(batches[0], profile).model_dump(mode="json")
    approvals = raw["measure_approvals"]
    assert isinstance(approvals, list)
    assert isinstance(approvals[0], dict)
    checks = approvals[0]["completed_checks"]
    assert isinstance(checks, list)
    checks.remove(PacketReviewCategory.SOURCE_INTEGRITY.value)

    with pytest.raises(ValidationError, match="every v1 packet-review check"):
        DomainBatchReviewLog.model_validate(raw)


def test_review_log_rejects_an_unlocked_ai_prompt():
    profile, batches = _domain_batches()
    batch = batches[0]
    invalid = _review_log(batch, profile).model_copy(
        update={"review_prompt_sha256": "f" * 64}
    )

    with pytest.raises(ValueError, match="locked Phase 3 prompt"):
        validate_domain_batch_review_log(invalid, batch, profile)


def test_review_log_rejects_the_packet_author_as_reviewer():
    profile, batches = _domain_batches()
    batch = batches[0]
    invalid = _review_log(batch, profile).model_copy(
        update={"reviewer_system": "CODEX"}
    )

    with pytest.raises(
        ValueError,
        match="participant-independent reviewer must differ",
    ):
        validate_domain_batch_review_log(invalid, batch, profile)


def test_review_log_rejects_an_unapproved_ai_reviewer():
    profile, batches = _domain_batches()
    batch = batches[0]
    invalid = _review_log(batch, profile).model_copy(
        update={"reviewer_system": "other_ai"}
    )

    with pytest.raises(
        ValueError,
        match="does not match the frozen exposure policy",
    ):
        validate_domain_batch_review_log(invalid, batch, profile)


def test_nonrevealing_summary_drops_all_restricted_free_text():
    profile, batches = _domain_batches()
    batch = batches[0]
    log = _review_log(batch, profile)

    summary = build_nonrevealing_review_summary(log, batch, profile)
    rendered = summary.model_dump_json()

    assert PLANTED_RESTRICTED_TEXT not in rendered
    assert PLANTED_ASSUMPTION_TEXT not in rendered
    assert batch.items[0].measure.title not in rendered
    assert str(batch.items[0].measure.packet.sources[0].url) not in rendered
    assert summary.findings_count == 1
    assert summary.reviewed_measure_count == 6
    assert summary.exact_packet_content_omitted


def test_nonrevealing_summary_rejects_incomplete_aggregate_counts():
    profile, batches = _domain_batches()
    summary = build_nonrevealing_review_summary(
        _review_log(batches[0], profile),
        batches[0],
        profile,
    )
    raw = summary.model_dump(mode="json")
    category_counts = raw["findings_by_category"]
    assert isinstance(category_counts, dict)
    del category_counts[PacketReviewCategory.SOURCE_INTEGRITY.value]

    with pytest.raises(ValidationError, match="every enum value"):
        type(summary).model_validate(raw)


def test_blocking_review_finding_cannot_be_merely_defended():
    with pytest.raises(ValidationError, match="must be resolved"):
        PacketReviewFinding(
            finding_id="blocking_finding",
            measure_id="measure_one",
            measure_version=1,
            category=PacketReviewCategory.FACTUAL_TRACEABILITY,
            severity=ReviewFindingSeverity.BLOCKING,
            finding_text="A blocking factual defect.",
            disposition=ReviewFindingDisposition.DEFENDED,
            resolution_notes="The author prefers the existing language.",
        )


def test_build_cli_writes_exact_content_only_to_output(
    tmp_path,
    capsys,
):
    profile, batches = _domain_batches()
    batch_paths = []
    for batch in batches:
        path = tmp_path / f"{batch.batch_id}.json"
        path.write_text(
            batch.model_dump_json(indent=2),
            encoding="utf-8",
        )
        batch_paths.append(path)
    output_path = tmp_path / "final_fixture.json"

    exit_code = build_final_bank_main(
        [
            str(PROFILE_PATH),
            *(str(path) for path in batch_paths),
            "--fixture-id",
            "preference_eval_final_test_v1",
            "--fixture-version",
            "1",
            "--created-at",
            (NOW + timedelta(days=2)).isoformat(),
            "--output",
            str(output_path),
        ]
    )

    assert exit_code == 0
    output = json.loads(capsys.readouterr().out)
    assert output["measure_count"] == 48
    assert output["exact_packet_content_omitted"]
    assert "Measure for" not in json.dumps(output)
    assert PLANTED_ASSUMPTION_TEXT not in json.dumps(output)
    assert len(load_fixture(output_path).measures) == 48


def test_domain_batch_cli_prints_only_aggregate_validation(
    tmp_path,
    capsys,
):
    _, batches = _domain_batches()
    batch = batches[0]
    batch_path = tmp_path / "batch.json"
    batch_path.write_text(
        batch.model_dump_json(indent=2),
        encoding="utf-8",
    )

    exit_code = validate_domain_batch_main(
        [str(PROFILE_PATH), str(batch_path)]
    )

    assert exit_code == 0
    output = json.loads(capsys.readouterr().out)
    assert output["schema_version"] == "preference_eval_domain_batch.v2"
    assert output["measure_count"] == 6
    assert output["exact_packet_content_omitted"]
    assert "Measure for" not in json.dumps(output)


def test_review_cli_emits_only_the_nonrevealing_summary(
    tmp_path,
    capsys,
):
    profile, batches = _domain_batches()
    batch = batches[0]
    log = _review_log(batch, profile)
    batch_path = tmp_path / "batch.json"
    log_path = tmp_path / "restricted_review_log.json"
    summary_path = tmp_path / "safe_summary.json"
    batch_path.write_text(
        batch.model_dump_json(indent=2),
        encoding="utf-8",
    )
    log_path.write_text(
        log.model_dump_json(indent=2),
        encoding="utf-8",
    )

    exit_code = validate_batch_review_main(
        [
            str(PROFILE_PATH),
            str(batch_path),
            str(log_path),
            "--summary-output",
            str(summary_path),
        ]
    )

    assert exit_code == 0
    stdout = capsys.readouterr().out
    written = summary_path.read_text(encoding="utf-8")
    assert PLANTED_RESTRICTED_TEXT not in stdout
    assert PLANTED_RESTRICTED_TEXT not in written
    assert PLANTED_ASSUMPTION_TEXT not in stdout
    assert PLANTED_ASSUMPTION_TEXT not in written
    assert json.loads(stdout) == json.loads(written)


def test_review_cli_suppresses_restricted_validation_error_input(
    tmp_path,
    capsys,
):
    profile, batches = _domain_batches()
    batch = batches[0]
    raw_log = _review_log(batch, profile).model_dump(mode="json")
    findings = raw_log["findings"]
    assert isinstance(findings, list)
    assert isinstance(findings[0], dict)
    findings[0]["unexpected_restricted_field"] = PLANTED_RESTRICTED_TEXT
    batch_path = tmp_path / "batch.json"
    log_path = tmp_path / "invalid_restricted_review_log.json"
    batch_path.write_text(
        batch.model_dump_json(indent=2),
        encoding="utf-8",
    )
    log_path.write_text(
        json.dumps(raw_log),
        encoding="utf-8",
    )

    exit_code = validate_batch_review_main(
        [
            str(PROFILE_PATH),
            str(batch_path),
            str(log_path),
            "--summary-output",
            str(tmp_path / "must_not_exist.json"),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    assert PLANTED_RESTRICTED_TEXT not in captured.err
    assert "restricted details omitted" in captured.err

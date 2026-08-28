from __future__ import annotations

from argparse import Namespace
from datetime import timedelta
from unittest.mock import patch

import pytest

from eval.assemble_phase4_two_deployment_qualification import (
    _require_new_outputs,
    _tracked_receipt_output,
    main,
)
from eval.fixture_io import content_sha256
from eval.phase4_capability import TogetherCapabilityOutputRecord
from eval.phase4_capability_continuation import (
    TogetherCandidateCapabilityExecutionState,
)
from eval.phase4_provider import (
    ProviderCallOutcome,
    ProviderExecutionJournal,
    ProviderHTTPErrorEnvelopeState,
    ProviderHTTPErrorMetadata,
    ProviderSeedStatus,
    ProviderTransportResult,
)
from eval.phase4_qualification_execution import QualificationCarryRecord
from eval.phase4_qualification_result_assembly import (
    assemble_two_deployment_qualification_result,
    build_result_sources_and_observations,
)
from eval.phase4_qualification_io import REPOSITORY_ROOT
from eval.phase4_robustness import (
    BudgetSegment,
    ProviderCallAuthorization,
    ProviderUsageLedger,
)
from eval.phase4_two_deployment_result import (
    QualificationResultStatus,
)
from eval.tests.test_phase4_capability import TickClock
from eval.tests.test_phase4_qualification_runtime import (
    APPROVAL_TIME,
    _execute,
    runtime_inputs,
)
from eval.tests.test_phase4_qualification_scope import _tracked_inputs
from eval.tests.test_phase4_two_deployment_result import (
    _observations as result_observations,
)
from eval.tests.test_phase4_selector_recovery import SelectorDeltaTransport


def _source_states_and_carry(runtime_inputs):
    observations = {
        item.call_id: item
        for item in result_observations()
        if item.call_id
        in {
            record.call_id for record in runtime_inputs["carry"].records
        }
    }
    plan_calls = {
        call.call_id: call
        for candidate in runtime_inputs["plan"].candidate_plans
        for call in candidate.calls
    }
    source_states = []
    carry_records = []
    for candidate_id in runtime_inputs["authorization"].authorized_candidate_ids:
        candidate_observations = [
            observations[record.call_id]
            for record in runtime_inputs["carry"].records
            if record.candidate_id == candidate_id
        ]
        authorizations = []
        usages = []
        bindings = []
        finalizations = []
        outputs = []
        for index, observation in enumerate(candidate_observations):
            authorization = ProviderCallAuthorization(
                call_id=observation.call_id,
                segment=BudgetSegment.QUALIFICATION,
                model_candidate_id=candidate_id,
                request_sha256=observation.request_content_sha256,
                authorized_max_cost_microusd=10_000,
                segment_remaining_before_microusd=4_000_000 - index * 10_000,
                total_remaining_before_microusd=20_000_000 - index * 10_000,
                created_at=observation.request_binding.created_at,
            )
            usage = observation.usage.model_copy(
                update={"authorization_sha256": content_sha256(authorization)}
            )
            finalization = observation.finalization.model_copy(
                update={
                    "authorization_sha256": content_sha256(authorization),
                    "usage_sha256": content_sha256(usage),
                }
            )
            authorizations.append(authorization)
            usages.append(usage)
            bindings.append(observation.request_binding)
            finalizations.append(finalization)
            outputs.append(
                TogetherCapabilityOutputRecord(
                    call_id=observation.call_id,
                    candidate_id=candidate_id,
                    role=observation.role,
                    output_sha256=observation.output_sha256,
                    output_payload=observation.parsed_output,
                )
            )
        profile = runtime_inputs["profile"]
        ledger = ProviderUsageLedger(
            ledger_id=f"{candidate_id}_assembly_source_ledger",
            robustness_profile_id=profile.profile_id,
            robustness_profile_version=profile.profile_version,
            robustness_profile_sha256=content_sha256(profile),
            authorizations=authorizations,
            calls=usages,
        )
        journal = ProviderExecutionJournal(
            journal_id=f"{candidate_id}_assembly_source_journal",
            robustness_profile_id=profile.profile_id,
            robustness_profile_version=profile.profile_version,
            robustness_profile_sha256=content_sha256(profile),
            request_bindings=bindings,
            finalizations=finalizations,
        )
        source_authorization_sha256 = content_sha256(
            {"candidate": candidate_id, "source_authorization": 1}
        )
        state = TogetherCandidateCapabilityExecutionState(
            state_id=f"{candidate_id}_assembly_source_state",
            state_version=1,
            continuation_plan_sha256=content_sha256(
                {"candidate": candidate_id, "continuation": 1}
            ),
            candidate_plan_sha256=content_sha256(
                {"candidate": candidate_id, "plan": 1}
            ),
            authorization_bundle_sha256=source_authorization_sha256,
            provider_ledger=ledger,
            provider_journal=journal,
            outputs=outputs,
        )
        source_states.append(state)
        state_sha256 = content_sha256(state)
        for observation, authorization, usage, finalization, output in zip(
            candidate_observations,
            authorizations,
            usages,
            finalizations,
            outputs,
            strict=True,
        ):
            call = plan_calls[observation.call_id]
            digest = content_sha256(
                {"call_id": observation.call_id, "assembly_test": 1}
            )
            carry_records.append(
                QualificationCarryRecord(
                    candidate_id=candidate_id,
                    role=observation.role,
                    call_id=observation.call_id,
                    source_manifest_ordinal=call.source_manifest_ordinal,
                    source_entry_sha256=call.source_entry_sha256,
                    corrected_capability_call_sha256=digest,
                    aggregation_role_evidence_sha256=digest,
                    source_state_schema_version=state.schema_version,
                    source_state_sha256=state_sha256,
                    source_authorization_sha256=source_authorization_sha256,
                    source_provider_ledger_sha256=content_sha256(ledger),
                    source_provider_journal_sha256=content_sha256(journal),
                    request_binding_sha256=content_sha256(
                        observation.request_binding
                    ),
                    provider_authorization_sha256=content_sha256(authorization),
                    provider_usage_sha256=content_sha256(usage),
                    finalization_sha256=content_sha256(finalization),
                    source_output_sha256=output.output_sha256,
                    current_response_schema_sha256=(
                        observation.request_binding.response_schema_sha256
                    ),
                    current_response_validator_sha256=(
                        observation.request_binding.response_validator_sha256
                    ),
                    current_revalidated_output_sha256=output.output_sha256,
                    output_payload=output.output_payload,
                    tool_call_count=finalization.tool_call_count,
                    response_validation_context_sha256=(
                        finalization.response_validation_context_sha256
                    ),
                )
            )
    carry_records.sort(
        key=lambda item: (item.candidate_id, item.source_manifest_ordinal)
    )
    carry = runtime_inputs["carry"].model_copy(
        update={
            "records": carry_records,
            "source_state_sha256s": sorted(
                content_sha256(item) for item in source_states
            ),
        }
    )
    return source_states, carry


def _candidate_states(runtime_inputs, carry):
    clock = TickClock(APPROVAL_TIME + timedelta(minutes=2))
    states, _ = _execute(
        runtime_inputs,
        SelectorDeltaTransport(clock),
    )
    records_by_candidate = {
        candidate_id: [
            content_sha256(item)
            for item in carry.records
            if item.candidate_id == candidate_id
        ]
        for candidate_id in states
    }
    return [
        state.model_copy(
            update={
                "carry_record_sha256s": records_by_candidate[candidate_id]
            }
        )
        for candidate_id, state in states.items()
    ]


class _ProviderPauseTransport(SelectorDeltaTransport):
    def __init__(self, clock) -> None:
        super().__init__(clock)
        self._failed = False

    def invoke(self, request):
        if not self._failed:
            self._failed = True
            return ProviderTransportResult(
                record_version="phase4_provider_transport_result.v3",
                outcome=ProviderCallOutcome.PROVIDER_ERROR,
                provider_http_error_metadata=ProviderHTTPErrorMetadata(
                    http_status_code=500,
                    envelope_state=ProviderHTTPErrorEnvelopeState.STANDARD,
                ),
                input_tokens=0,
                output_tokens=0,
                provider_request_sent=True,
                provider_seed_status=ProviderSeedStatus.SENT_UNCONFIRMED,
                latency_ms=1.0,
                failure_code="together_http_500",
                completed_at=self.clock(),
            )
        return super().invoke(request)


def _provider_pause_states(runtime_inputs, carry):
    clock = TickClock(APPROVAL_TIME + timedelta(minutes=2))
    states, _ = _execute(runtime_inputs, _ProviderPauseTransport(clock))
    records_by_candidate = {
        candidate_id: [
            content_sha256(item)
            for item in carry.records
            if item.candidate_id == candidate_id
        ]
        for candidate_id in states
    }
    return [
        state.model_copy(
            update={
                "carry_record_sha256s": records_by_candidate[candidate_id]
            }
        )
        for candidate_id, state in states.items()
    ]


def _assemble(runtime_inputs, source_states, carry, states, *, suffix):
    tracked = _tracked_inputs()
    with patch(
        "eval.phase4_qualification_result_assembly."
        "validate_two_deployment_qualification_authorization"
    ) as authorization_validator:
        result, receipt = assemble_two_deployment_qualification_result(
            tracked[0],
            tracked[1],
            tracked[2],
            tracked[3],
            tracked[4],
            tracked[5],
            tracked[9],
            runtime_inputs["plan"],
            carry,
            runtime_inputs["authorization"],
            runtime_inputs["catalog"],
            source_states,
            states,
            qualification_id=f"two_deployment_{suffix}_assembly_test",
            receipt_id=f"two_deployment_{suffix}_receipt_test",
            created_at=APPROVAL_TIME + timedelta(hours=2),
        )
    authorization_validator.assert_called_once()
    return result, receipt


def test_complete_fake_execution_converts_and_selects(runtime_inputs) -> None:
    source_states, carry = _source_states_and_carry(runtime_inputs)
    states = _candidate_states(runtime_inputs, carry)

    result, receipt = _assemble(
        runtime_inputs,
        source_states,
        carry,
        states,
        suffix="complete",
    )

    assert len(result.observations) == 304
    assert result.status is QualificationResultStatus.SELECTED
    assert result.selected_candidate_id is not None
    assert receipt.status is result.status
    assert result.result_source_bindings.candidate_state_sha256s == {
        item.candidate_id: content_sha256(item) for item in states
    }
    assert sum(
        item.historical_interviewer_replay_unverifiable_count
        for item in result.candidate_results
    ) == 2


def test_provider_pause_converts_without_selection(runtime_inputs) -> None:
    source_states, carry = _source_states_and_carry(runtime_inputs)
    states = _provider_pause_states(runtime_inputs, carry)
    result, receipt = _assemble(
        runtime_inputs,
        source_states,
        carry,
        states,
        suffix="pause",
    )

    assert result.status is (
        QualificationResultStatus.PAUSED_PENDING_PROVIDER_REVIEW
    )
    assert result.selected_candidate_id is None
    assert receipt.status is result.status


def test_carry_cannot_substitute_an_asserted_source_state_hash(
    runtime_inputs,
) -> None:
    source_states, carry = _source_states_and_carry(runtime_inputs)
    states = _candidate_states(runtime_inputs, carry)
    first = carry.records[0]
    forged = first.model_copy(update={"source_state_sha256": "0" * 64})
    forged_carry = carry.model_copy(
        update={"records": [forged, *carry.records[1:]]}
    )

    with pytest.raises(ValueError, match="result source is missing"):
        build_result_sources_and_observations(
            runtime_inputs["plan"],
            forged_carry,
            runtime_inputs["authorization"],
            source_states,
            states,
        )


def test_carry_provider_lineage_is_recomputed(runtime_inputs) -> None:
    source_states, carry = _source_states_and_carry(runtime_inputs)
    states = _candidate_states(runtime_inputs, carry)
    first = carry.records[0]
    forged = first.model_copy(update={"provider_usage_sha256": "0" * 64})
    forged_carry = carry.model_copy(
        update={"records": [forged, *carry.records[1:]]}
    )

    with pytest.raises(ValueError, match="evidence differs"):
        build_result_sources_and_observations(
            runtime_inputs["plan"],
            forged_carry,
            runtime_inputs["authorization"],
            source_states,
            states,
        )


@pytest.mark.parametrize(
    "relative",
    [
        "eval/results/receipt.json",
        "eval/restricted_bank/receipt.json",
        "eval/private_runs/receipt.json",
    ],
)
def test_tracked_receipt_path_is_exactly_review_summaries(relative) -> None:
    with pytest.raises(ValueError, match="review_summaries"):
        _tracked_receipt_output(REPOSITORY_ROOT / relative)

    accepted = _tracked_receipt_output(
        REPOSITORY_ROOT / "eval/review_summaries/receipt.json"
    )
    assert accepted.parent.name == "review_summaries"


def test_existing_receipt_blocks_before_private_result_write(tmp_path) -> None:
    private_result = tmp_path / "private_result.json"
    aggregate_receipt = tmp_path / "aggregate_receipt.json"
    aggregate_receipt.write_text("already exists", encoding="utf-8")

    with pytest.raises(ValueError, match="result output already exists"):
        _require_new_outputs(private_result, aggregate_receipt)

    assert not private_result.exists()


def test_cli_path_error_does_not_echo_restricted_path(capsys, tmp_path) -> None:
    planted = "PLANTED_RESTRICTED_RESULT_TEXT"
    args = Namespace(run_output_directory=tmp_path / planted)
    with patch(
        "eval.assemble_phase4_two_deployment_qualification.build_parser"
    ) as parser:
        parser.return_value.parse_args.return_value = args
        assert main([]) == 1

    captured = capsys.readouterr()
    assert planted not in captured.err
    assert "restricted details omitted" in captured.err

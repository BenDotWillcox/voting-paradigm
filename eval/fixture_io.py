"""Load, validate, and hash versioned preference-evaluation fixtures."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict, JsonValue

from .contracts import (
    EvaluationRun,
    EvaluationFixture,
    MeasureDomain,
    MeasureVersion,
    NonEmptyText,
    PositiveVersion,
    StableId,
    validate_prediction_for_measure,
    validate_response_for_measure,
)


class MeasureManifestEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    measure_id: StableId
    measure_version: PositiveVersion
    packet_id: StableId
    packet_version: PositiveVersion
    measure_sha256: NonEmptyText
    packet_sha256: NonEmptyText


class FixtureManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = "preference_eval_manifest.v1"
    fixture_id: StableId
    fixture_version: PositiveVersion
    fixture_sha256: NonEmptyText
    jurisdiction_sha256: NonEmptyText
    measures: list[MeasureManifestEntry]


def load_fixture(path: Path) -> EvaluationFixture:
    """Load and validate one JSON fixture."""

    raw = json.loads(path.read_text(encoding="utf-8"))
    return EvaluationFixture.model_validate(raw)


def _json_value(value: BaseModel | JsonValue) -> JsonValue:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    return value


def canonical_json(value: BaseModel | JsonValue) -> str:
    """Canonical JSON used for content-addressed evaluation inputs."""

    return json.dumps(
        _json_value(value),
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def content_sha256(value: BaseModel | JsonValue) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def build_fixture_manifest(fixture: EvaluationFixture) -> FixtureManifest:
    """Build a deterministic manifest independent of source-file formatting."""

    measures = [
        MeasureManifestEntry(
            measure_id=measure.measure_id,
            measure_version=measure.version,
            packet_id=measure.packet.packet_id,
            packet_version=measure.packet.version,
            measure_sha256=content_sha256(measure),
            packet_sha256=content_sha256(measure.packet),
        )
        for measure in sorted(
            fixture.measures,
            key=lambda candidate: (candidate.measure_id, candidate.version),
        )
    ]
    return FixtureManifest(
        fixture_id=fixture.fixture_id,
        fixture_version=fixture.fixture_version,
        fixture_sha256=content_sha256(fixture),
        jurisdiction_sha256=content_sha256(fixture.jurisdiction),
        measures=measures,
    )


def validate_run_against_fixture(
    run: EvaluationRun,
    fixture: EvaluationFixture,
) -> None:
    """Bind a replayable run to the exact validated fixture it names."""

    if run.fixture_id != fixture.fixture_id:
        raise ValueError(
            f"run fixture_id {run.fixture_id!r} does not match "
            f"{fixture.fixture_id!r}"
        )
    if run.fixture_version != fixture.fixture_version:
        raise ValueError(
            f"run fixture_version {run.fixture_version} does not match "
            f"{fixture.fixture_version}"
        )
    fixture_sha256 = content_sha256(fixture)
    if run.fixture_sha256 != fixture_sha256:
        raise ValueError(
            f"run fixture_sha256 {run.fixture_sha256} does not match "
            f"{fixture_sha256}"
        )

    measure_by_key = {
        (measure.measure_id, measure.version): measure
        for measure in fixture.measures
    }

    def require_measure(
        measure_id: str,
        measure_version: int,
        packet_version: int,
        record_label: str,
    ) -> MeasureVersion:
        measure = measure_by_key.get((measure_id, measure_version))
        if measure is None:
            raise ValueError(
                f"{record_label} references unknown measure "
                f"{measure_id}@{measure_version}"
            )
        if packet_version != measure.packet.version:
            raise ValueError(
                f"{record_label} packet_version {packet_version} does not "
                f"match {measure.packet.version}"
            )
        return measure

    for presentation in run.measure_presentations:
        require_measure(
            presentation.measure_id,
            presentation.measure_version,
            presentation.packet_version,
            f"presentation {presentation.presentation_id}",
        )

    for response in run.participant_responses:
        measure = require_measure(
            response.measure_id,
            response.measure_version,
            response.packet_version,
            f"response {response.response_id}",
        )
        validate_response_for_measure(response, measure)

    for snapshot in run.prediction_snapshots:
        measure = require_measure(
            snapshot.target_measure_id,
            snapshot.target_measure_version,
            snapshot.target_packet_version,
            f"snapshot {snapshot.snapshot_id}",
        )
        validate_prediction_for_measure(snapshot, measure)

    for event in run.evidence_events:
        if event.measure_id is None:
            continue
        assert event.measure_version is not None
        assert event.packet_version is not None
        require_measure(
            event.measure_id,
            event.measure_version,
            event.packet_version,
            f"evidence event {event.event_id}",
        )


def validate_development_fixture(fixture: EvaluationFixture) -> None:
    """Enforce the Phase 1 fixture's one-measure-per-domain contract."""

    if not fixture.development_only:
        raise ValueError("Phase 1 fixture must be marked development_only")
    if len(fixture.measures) != len(MeasureDomain):
        raise ValueError(
            f"Phase 1 fixture requires {len(MeasureDomain)} measures; "
            f"received {len(fixture.measures)}"
        )
    domains = [measure.domain for measure in fixture.measures]
    if set(domains) != set(MeasureDomain):
        missing = sorted(domain.value for domain in set(MeasureDomain) - set(domains))
        extra = sorted(domain.value for domain in set(domains) - set(MeasureDomain))
        raise ValueError(
            "Phase 1 fixture must cover every domain exactly once; "
            f"missing={missing}, extra={extra}"
        )
    if len(domains) != len(set(domains)):
        raise ValueError("Phase 1 fixture contains a duplicate domain")

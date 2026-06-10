from __future__ import annotations

import pytest

from braindashboard.executors.events import (
    JOB_EVENT_PREFIX,
    JOB_EVENT_PREFIX_ENV,
    JOB_RUN_ID_ENV,
    JobEventParseError,
    JobEventType,
    build_job_event_environment,
    build_subjob_states,
    parse_job_event_line,
    parse_tqdm_progress_line,
)


def test_parse_job_event_line_ignores_regular_logs() -> None:
    assert parse_job_event_line("epoch 1 loss=2.4") is None


def test_parse_tqdm_progress_line_accepts_percent_bar() -> None:
    event = parse_tqdm_progress_line(
        "train:  42%|####      | 420/1,000 [00:12<00:18, 31.23it/s]",
        run_id="run-1",
    )

    assert event is not None
    assert event.type is JobEventType.PROGRESS
    assert event.run_id == "run-1"
    assert event.phase == "train"
    assert event.progress is not None
    assert event.progress.current == 420
    assert event.progress.total == 1000
    assert event.progress.percent == 42
    assert event.progress.unit == "it"
    assert event.metadata == {"source": "tqdm"}


def test_parse_tqdm_progress_line_accepts_unknown_total_counter() -> None:
    event = parse_tqdm_progress_line("download: 15it [00:02,  6.74it/s]")

    assert event is not None
    assert event.phase == "download"
    assert event.progress is not None
    assert event.progress.current == 15
    assert event.progress.total is None
    assert event.progress.percent is None
    assert event.progress.unit == "it"


def test_parse_tqdm_progress_line_ignores_regular_logs() -> None:
    assert parse_tqdm_progress_line("epoch 1 loss=2.4") is None


def test_parse_job_event_line_accepts_metric_event() -> None:
    event = parse_job_event_line(
        f'{JOB_EVENT_PREFIX}{{"version":1,"type":"metric","run_id":"run-1",'
        '"sequence":4,"phase":"train","metrics":{"loss":1.82},'
        '"progress":{"current":12,"total":100,"unit":"step"}}'
    )

    assert event is not None
    assert event.type is JobEventType.METRIC
    assert event.run_id == "run-1"
    assert event.sequence == 4
    assert event.metrics["loss"] == 1.82
    assert event.progress is not None
    assert event.progress.current == 12


def test_parse_job_event_line_exposes_subjob_identity() -> None:
    event = parse_job_event_line(
        f'{JOB_EVENT_PREFIX}{{"version":1,"type":"progress","run_id":"run-1",'
        '"metadata":{"subjob_id":"item-004","subjob_status":"running"}}'
    )

    assert event is not None
    assert event.subjob_id == "item-004"


def test_build_subjob_states_tracks_latest_subjob_event() -> None:
    events = [
        parse_job_event_line(
            f'{JOB_EVENT_PREFIX}{{"version":1,"type":"phase_changed","run_id":"run-1",'
            '"phase":"batch_item","metadata":{"subjob_id":"item-004","subjob_type":"batch_item",'
            '"subjob_index":4,"subjob_total":20,"subjob_status":"running",'
            '"subjob_label":"004_Rainy_Errand"}}'
        ),
        parse_job_event_line(
            f'{JOB_EVENT_PREFIX}{{"version":1,"type":"progress","run_id":"run-1",'
            '"phase":"hydrate","progress":{"current":4200,"total":16000,"unit":"token",'
            '"percent":26.25},"metrics":{"tokens_per_second":41.3},'
            '"metadata":{"subjob_id":"item-004","subjob_type":"batch_item",'
            '"subjob_status":"running"}}'
        ),
        parse_job_event_line(
            f'{JOB_EVENT_PREFIX}{{"version":1,"type":"completed","run_id":"run-1",'
            '"phase":"batch_item","metadata":{"subjob_id":"item-004",'
            '"subjob_type":"batch_item","subjob_status":"complete"}}'
        ),
    ]

    states = build_subjob_states([event for event in events if event is not None])

    assert len(states) == 1
    assert states[0].id == "item-004"
    assert states[0].label == "004_Rainy_Errand"
    assert states[0].index == 4
    assert states[0].total == 20
    assert states[0].status == "complete"
    assert states[0].latest_event_type is JobEventType.COMPLETED
    assert states[0].progress is not None
    assert states[0].progress.percent == 26.25
    assert states[0].metrics["tokens_per_second"] == 41.3


def test_parse_job_event_line_rejects_invalid_prefixed_json() -> None:
    with pytest.raises(JobEventParseError):
        parse_job_event_line(f"{JOB_EVENT_PREFIX}not-json")


def test_parse_job_event_line_rejects_unknown_fields() -> None:
    with pytest.raises(JobEventParseError):
        parse_job_event_line(f'{JOB_EVENT_PREFIX}{{"version":1,"type":"started","extra":true}}')


def test_build_job_event_environment() -> None:
    assert build_job_event_environment("run-123") == {
        JOB_RUN_ID_ENV: "run-123",
        JOB_EVENT_PREFIX_ENV: JOB_EVENT_PREFIX.strip(),
    }

from __future__ import annotations

from braindashboard.executors.events import JobEventType
from braindashboard.scheduler.service import _parse_stream_event, _split_completed_stream_records


def test_split_completed_stream_records_handles_newlines_and_carriage_returns() -> None:
    records, remainder = _split_completed_stream_records(
        "starting\n 10%|#         | 1/10 [00:00<00:09, 1.00it/s]\r"
        " 20%|##        | 2/10 [00:01<00:08, 1.00it/s]\r\npartial"
    )

    assert records == [
        "starting",
        " 10%|#         | 1/10 [00:00<00:09, 1.00it/s]",
        " 20%|##        | 2/10 [00:01<00:08, 1.00it/s]",
    ]
    assert remainder == "partial"


def test_parse_stream_event_falls_back_to_tqdm_progress() -> None:
    event = _parse_stream_event(
        " 20%|##        | 2/10 [00:01<00:08, 1.00it/s]",
        run_id="run-1",
    )

    assert event is not None
    assert event.type is JobEventType.PROGRESS
    assert event.run_id == "run-1"
    assert event.progress is not None
    assert event.progress.current == 2
    assert event.progress.total == 10
    assert event.progress.percent == 20

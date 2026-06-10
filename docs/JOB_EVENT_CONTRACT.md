# BrainDashboard Job Event Contract

This contract is for jobs that BrainDashboard launches and controls directly. It gives training scripts and other long-running jobs a low-overhead way to publish structured status through normal stdout or stderr. BrainDashboard still captures raw logs; these events are the machine-readable layer on top.

The first transport is structured log emit only. HTTP callbacks can use the same event schema later if needed.

## Environment

BrainDashboard executors should provide these environment variables when starting a controlled job:

- `BRAINDASHBOARD_RUN_ID`: stable ID for this job run.
- `BRAINDASHBOARD_EVENT_PREFIX`: line prefix for structured events. Default: `BD_EVENT`.

Jobs may ignore these variables and run normally. If a job emits events, it should use the run ID from `BRAINDASHBOARD_RUN_ID` when present.

## Line Format

Each event is one UTF-8 line on stdout or stderr:

```text
BD_EVENT {"version":1,"type":"metric","run_id":"run-123","metrics":{"loss":1.82}}
```

Rules:

- The prefix is exactly `BD_EVENT ` by default: `BD_EVENT`, one space, then JSON.
- The JSON payload must be a single object on one line.
- Regular log lines are allowed and ignored by the event parser.
- Unknown top-level fields are invalid. Put custom values under `metadata`.
- Event delivery is append-only. Emit a new event instead of editing previous state.

## Event Object

Required fields:

- `version`: currently `1`.
- `type`: event type string.

Recommended fields:

- `run_id`: value of `BRAINDASHBOARD_RUN_ID`.
- `sequence`: monotonic integer per process, starting at `0` or `1`.
- `timestamp`: ISO 8601 timestamp with timezone, for example `2026-05-25T12:34:56Z`.
- `message`: short human-readable status.

Optional fields:

- `event_id`: stable unique ID for deduplication if the event may be replayed.
- `phase`: current phase, such as `prepare`, `train`, `validate`, `checkpoint`, or `upload`.
- `progress`: progress object.
- `metrics`: flat object of scalar metric values.
- `artifacts`: list of produced files or URIs.
- `error`: structured failure details.
- `metadata`: extra integration-specific data.

## Subjobs

Some jobs own nested units of work that BrainDashboard should track separately from the parent process. Examples include batch items, per-file indexing tasks, distributed worker shards, export partitions, or validation suites. These are called subjobs.

Subjobs do not change the top-level event schema. A subjob event is a normal event with subjob identity under `metadata`.

Recommended `metadata` fields:

- `subjob_id`: stable ID for the nested unit of work within the parent run.
- `subjob_type`: short category such as `batch_item`, `worker`, `partition`, `validation_suite`, or `child_run`.
- `subjob_index`: zero-based or one-based numeric position when the parent has an ordered list.
- `subjob_total`: total sibling count when known.
- `parent_subjob_id`: parent nested unit, for multi-level trees.
- `subjob_status`: current status such as `pending`, `running`, `complete`, `failed`, `skipped`, or `retrying`.
- `subjob_label`: human-readable display label.

Rules:

- `subjob_id` should be stable across retries and resumes. Do not use a retry attempt number as the ID.
- Subjob lifecycle should use the same top-level event types as jobs: `started`, `phase_changed`, `progress`, `warning`, `completed`, and `failed`.
- Use `progress` for parent aggregate progress and subjob-local progress. The subjob identity in `metadata` disambiguates them.
- A failed subjob may emit `warning` when the parent process can continue, or `failed` when that subjob is terminal. The parent process may still later emit `completed` if partial success is acceptable for that job.
- Parent job `completed`/`failed` remains about the whole supervised process. Subjob completion does not imply parent completion.
- Retry metadata should include both current retry state and stable position, for example `attempt`, `total_attempts`, `retry_scope`, or `resume_point`, under `metadata`.

Subjob example:

```text
BD_EVENT {"version":1,"type":"phase_changed","run_id":"run-123","phase":"batch_item","metadata":{"subjob_id":"item-004","subjob_type":"batch_item","subjob_index":4,"subjob_total":20,"subjob_status":"running","subjob_label":"004_Rainy_Errand"}}
BD_EVENT {"version":1,"type":"progress","run_id":"run-123","phase":"hydrate","progress":{"current":4200,"total":16000,"unit":"token","percent":26.25},"metadata":{"subjob_id":"item-004","subjob_type":"batch_item","subjob_status":"running","child_run_id":"cpt-batches/mike-batch/004_Rainy_Errand"}}
BD_EVENT {"version":1,"type":"completed","run_id":"run-123","phase":"batch_item","metadata":{"subjob_id":"item-004","subjob_type":"batch_item","subjob_status":"complete","child_run_id":"cpt-batches/mike-batch/004_Rainy_Errand"}}
```

## Event Types

- `started`: process has started and parsed its configuration.
- `heartbeat`: process is alive, even if progress has not changed.
- `phase_changed`: process entered a new phase.
- `progress`: progress changed.
- `metric`: metrics changed, such as loss or throughput.
- `checkpoint`: checkpoint artifact was written.
- `artifact`: non-checkpoint artifact was written.
- `warning`: recoverable issue or degraded condition.
- `completed`: job believes work completed successfully.
- `failed`: job detected a terminal failure.

BrainDashboard should still treat the supervisor-observed process exit as authoritative. A `completed` event is useful status, but a non-zero process exit should still fail the run.

## Nested Objects

`progress`:

```json
{
  "current": 1200,
  "total": 10000,
  "unit": "step",
  "percent": 12
}
```

Fields are optional, but `percent` must be between `0` and `100` when present.

`metrics`:

```json
{
  "loss": 1.82,
  "learning_rate": 0.00002,
  "samples_per_second": 41.3
}
```

Metric values should be scalar JSON values: number, string, boolean, or null.

`artifacts`:

```json
[
  {
    "uri": "file:///runs/run-123/checkpoints/epoch-4.safetensors",
    "kind": "checkpoint",
    "name": "epoch-4",
    "metadata": {"epoch": 4}
  }
]
```

`error`:

```json
{
  "code": "cuda_oom",
  "message": "CUDA out of memory during validation",
  "retryable": true
}
```

## Training Example

Python jobs can emit events with a tiny helper:

```python
import json
import os
import sys
from datetime import UTC, datetime

RUN_ID = os.environ.get("BRAINDASHBOARD_RUN_ID")
PREFIX = os.environ.get("BRAINDASHBOARD_EVENT_PREFIX", "BD_EVENT")


def emit_event(event_type: str, **fields: object) -> None:
    payload = {
        "version": 1,
        "type": event_type,
        "run_id": RUN_ID,
        "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        **fields,
    }
    print(f"{PREFIX} {json.dumps(payload, separators=(',', ':'))}", flush=True)


emit_event("started", message="training initialized")

for step in range(1, 1001):
    loss = train_one_step()
    if step % 10 == 0:
        emit_event(
            "metric",
            phase="train",
            sequence=step,
            progress={"current": step, "total": 1000, "unit": "step"},
            metrics={"loss": loss},
        )

emit_event("completed", message="training complete")
```

## Compatibility Promise

Consumers should key off `version`. BrainDashboard may add optional fields in a future version, but it should not change the meaning of existing version `1` fields. If the schema needs incompatible changes, use `version: 2`.
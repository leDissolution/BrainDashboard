from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
from pytest import MonkeyPatch
from sqlalchemy.exc import SQLAlchemyError

from braindashboard.api.routes import jobs as jobs_route
from braindashboard.core.config import Settings
from braindashboard.db.models import (
    JobDefinitionRecord,
    JobEventRecord,
    JobParameterRecord,
    JobRunRecord,
)
from braindashboard.db.session import get_db_session
from braindashboard.domain.enums import JobExecutionMode, JobRunState
from braindashboard.main import create_app


def job_definition_payload() -> dict[str, object]:
    return {
        "id": "custom-job",
        "name": "Custom job",
        "description": "Loaded from the database.",
        "enabled": True,
        "execution_mode": "docker",
        "command": ["python", "-m", "custom.pipeline"],
        "working_directory": None,
        "image": "ghcr.io/local/custom:latest",
        "default_priority": "high",
        "timeout_seconds": 900,
        "event_contract": "structured_stdout",
        "resource_hints": {
            "gpu_count": 1,
            "min_vram_gib": 12.0,
            "exclusive_gpu": False,
            "docker_required": True,
        },
        "retry_policy": {"max_attempts": 3, "backoff_seconds": 60},
        "parameters": [
            {
                "name": "input_path",
                "label": "Input path",
                "description": "Input folder.",
                "value_type": "path",
                "cli_flag": "--input",
                "default_value": None,
                "required_at_queue": True,
                "allow_queue_override": True,
                "choices": [],
            }
        ],
    }


def job_definition_record() -> JobDefinitionRecord:
    return JobDefinitionRecord(
        id="custom-job",
        position=0,
        name="Custom job",
        description="Loaded from the database.",
        enabled=True,
        execution_mode=JobExecutionMode.DOCKER.value,
        command=["python", "-m", "custom.pipeline"],
        image="ghcr.io/local/custom:latest",
        default_priority="high",
        timeout_seconds=900,
        event_contract="structured_stdout",
        resource_hints={
            "gpu_count": 1,
            "min_vram_gib": 12.0,
            "exclusive_gpu": False,
            "docker_required": True,
        },
        retry_policy={"max_attempts": 3, "backoff_seconds": 60},
        parameters=[
            JobParameterRecord(
                position=0,
                name="input_path",
                label="Input path",
                description="Input folder.",
                value_type="path",
                cli_flag="--input",
                default_value=None,
                required_at_queue=True,
                allow_queue_override=True,
                choices=[],
            )
        ],
    )


def native_job_definition_record() -> JobDefinitionRecord:
    record = job_definition_record()
    record.execution_mode = JobExecutionMode.NATIVE.value
    record.command = ["python", "job.py"]
    record.image = None
    return record


def job_run_record() -> JobRunRecord:
    now = datetime.now(UTC)
    return JobRunRecord(
        id="run-123",
        definition_id="custom-job",
        state=JobRunState.QUEUED.value,
        priority="high",
        attempt=1,
        effective_parameters={"input_path": "/srv/data"},
        effective_command=["python", "job.py", "--input", "/srv/data"],
        timeout_seconds=900,
        log_stdout_path="/tmp/run-123/stdout.log",
        log_stderr_path="/tmp/run-123/stderr.log",
        queued_at=now,
        created_at=now,
        updated_at=now,
        definition=native_job_definition_record(),
    )


def job_event_record() -> JobEventRecord:
    now = datetime.now(UTC)
    return JobEventRecord(
        id=1,
        run_id="run-123",
        event_id=None,
        sequence=8,
        type="phase_changed",
        timestamp=now,
        stream="stdout",
        line_number=1,
        phase="cpt_artifact",
        message="CPT artifact run initialized",
        progress=None,
        metrics={},
        artifacts=[],
        error=None,
        event_metadata={
            "subjob_id": "cpt-batches/batch-1/001_item",
            "subjob_type": "batch_item",
            "subjob_index": 1,
            "subjob_status": "running",
        },
        raw_payload={
            "version": 1,
            "type": "phase_changed",
            "run_id": "run-123",
            "sequence": 8,
            "phase": "cpt_artifact",
            "message": "CPT artifact run initialized",
            "metadata": {
                "subjob_id": "cpt-batches/batch-1/001_item",
                "subjob_type": "batch_item",
                "subjob_index": 1,
                "subjob_status": "running",
            },
        },
        created_at=now,
    )


def job_progress_event_record() -> JobEventRecord:
    now = datetime.now(UTC)
    return JobEventRecord(
        id=2,
        run_id="run-123",
        event_id=None,
        sequence=94,
        type="progress",
        timestamp=now,
        stream="stdout",
        line_number=2,
        phase="batch",
        message="Narrator rewrite batch progress updated",
        progress={"current": 93.0, "total": 750.0, "unit": "item", "percent": 12.4},
        metrics={},
        artifacts=[],
        error=None,
        event_metadata={
            "mode": "narrator_rewrite_batch",
            "completed_items": 93,
            "pending_items": 657,
        },
        raw_payload={
            "version": 1,
            "type": "progress",
            "run_id": "run-123",
            "sequence": 94,
            "phase": "batch",
            "message": "Narrator rewrite batch progress updated",
            "progress": {"current": 93.0, "total": 750.0, "unit": "item", "percent": 12.4},
            "metadata": {
                "mode": "narrator_rewrite_batch",
                "completed_items": 93,
                "pending_items": 657,
            },
        },
        created_at=now,
    )


class FakeSession:
    def __init__(self, definition: JobDefinitionRecord | None = None) -> None:
        self.definition = definition
        self.rolled_back = False

    async def get(self, model: object, identifier: str, **_kwargs: object) -> object | None:
        if model is JobDefinitionRecord and identifier == "custom-job":
            return self.definition
        return None

    async def rollback(self) -> None:
        self.rolled_back = True


async def fake_session() -> AsyncGenerator[object, None]:
    yield object()


def app_with_scheduler_disabled(**settings: object) -> object:
    return create_app(Settings(scheduler_enabled=False, hardware_monitor_enabled=False, **settings))


def fake_db_session(session: object) -> object:
    async def _fake_session() -> AsyncGenerator[object, None]:
        yield session

    return _fake_session


def test_job_definitions_endpoint_falls_back_to_seeded_definitions(
    monkeypatch: MonkeyPatch,
) -> None:
    async def raise_database_unavailable(_session: object) -> list[JobDefinitionRecord]:
        raise SQLAlchemyError("database unavailable")

    monkeypatch.setattr(jobs_route, "list_job_definition_records", raise_database_unavailable)

    app = app_with_scheduler_disabled()
    app.dependency_overrides[get_db_session] = fake_db_session(FakeSession())
    client = TestClient(app)

    response = client.get("/api/jobs/definitions")

    assert response.status_code == 200
    body = response.json()
    assert len(body["definitions"]) == 3
    assert body["definitions"][0]["id"] == "train-lora-native"
    assert body["definitions"][0]["execution_mode"] == "native"
    assert body["definitions"][0]["event_contract"] == "structured_stdout"
    assert body["definitions"][0]["resource_hints"]["exclusive_gpu"] is True
    assert body["definitions"][0]["parameters"][0]["name"] == "dataset_path"
    assert body["definitions"][0]["parameters"][0]["required_at_queue"] is True
    assert body["definitions"][0]["parameters"][3]["default_value"] == 1200
    assert body["definitions"][0]["parameters"][3]["allow_queue_override"] is True
    assert body["definitions"][1]["resource_hints"]["docker_required"] is True
    assert body["definitions"][1]["parameters"][3]["choices"] == [
        "joycaption",
        "wd14",
        "florence2",
    ]


def test_job_definitions_endpoint_reads_persisted_definitions(monkeypatch: MonkeyPatch) -> None:
    seed_calls = 0

    async def list_records(_session: object) -> list[JobDefinitionRecord]:
        return [job_definition_record()]

    async def seed_if_empty(_session: object, _definitions: object) -> None:
        nonlocal seed_calls
        seed_calls += 1

    monkeypatch.setattr(jobs_route, "list_job_definition_records", list_records)
    monkeypatch.setattr(jobs_route, "ensure_seeded_job_definitions", seed_if_empty)

    app = app_with_scheduler_disabled()
    app.dependency_overrides[get_db_session] = fake_session
    client = TestClient(app)

    response = client.get("/api/jobs/definitions")

    assert response.status_code == 200
    body = response.json()
    assert body["definitions"] == [job_definition_payload()]
    assert seed_calls == 0


def test_job_definitions_endpoint_seeds_only_when_empty(monkeypatch: MonkeyPatch) -> None:
    seeded_payloads: list[object] = []

    async def list_records(_session: object) -> list[JobDefinitionRecord]:
        return []

    async def seed_if_empty(_session: object, definitions: object) -> None:
        seeded_payloads.append(definitions)

    monkeypatch.setattr(jobs_route, "list_job_definition_records", list_records)
    monkeypatch.setattr(jobs_route, "ensure_seeded_job_definitions", seed_if_empty)

    app = app_with_scheduler_disabled()
    app.dependency_overrides[get_db_session] = fake_session
    client = TestClient(app)

    response = client.get("/api/jobs/definitions")

    assert response.status_code == 200
    body = response.json()
    assert len(body["definitions"]) == 3
    assert body["definitions"][0]["id"] == "train-lora-native"
    assert len(seeded_payloads) == 1


def test_create_job_definition_endpoint_saves_payload(monkeypatch: MonkeyPatch) -> None:
    saved_payloads: list[dict[str, object]] = []

    async def save_record(_session: object, definition: dict[str, object]) -> JobDefinitionRecord:
        saved_payloads.append(definition)
        return job_definition_record()

    monkeypatch.setattr(jobs_route, "save_job_definition_record", save_record)

    app = app_with_scheduler_disabled()
    app.dependency_overrides[get_db_session] = fake_session
    client = TestClient(app)

    response = client.post("/api/jobs/definitions", json=job_definition_payload())

    assert response.status_code == 201
    assert response.json() == job_definition_payload()
    assert saved_payloads == [job_definition_payload()]


def test_create_job_definition_endpoint_accepts_flag_parameters(monkeypatch: MonkeyPatch) -> None:
    saved_payloads: list[dict[str, object]] = []
    payload = job_definition_payload()
    parameters = payload["parameters"]
    assert isinstance(parameters, list)
    parameters.append(
        {
            "name": "explicit",
            "label": "Explicit mode",
            "description": "Include --explicit when enabled.",
            "value_type": "flag",
            "cli_flag": "--explicit",
            "default_value": False,
            "required_at_queue": False,
            "allow_queue_override": True,
            "choices": [],
        }
    )

    async def save_record(_session: object, definition: dict[str, object]) -> JobDefinitionRecord:
        saved_payloads.append(definition)
        return job_definition_record()

    monkeypatch.setattr(jobs_route, "save_job_definition_record", save_record)

    app = app_with_scheduler_disabled()
    app.dependency_overrides[get_db_session] = fake_session
    client = TestClient(app)

    response = client.post("/api/jobs/definitions", json=payload)

    assert response.status_code == 201
    assert saved_payloads == [payload]


def test_update_job_definition_rejects_id_mismatch() -> None:
    app = app_with_scheduler_disabled()
    app.dependency_overrides[get_db_session] = fake_session
    client = TestClient(app)

    response = client.put("/api/jobs/definitions/different-job", json=job_definition_payload())

    assert response.status_code == 400


def test_delete_job_definition_endpoint(monkeypatch: MonkeyPatch) -> None:
    deleted_ids: list[str] = []

    async def delete_record(_session: object, definition_id: str) -> bool:
        deleted_ids.append(definition_id)
        return True

    monkeypatch.setattr(jobs_route, "delete_job_definition_record", delete_record)

    app = app_with_scheduler_disabled()
    app.dependency_overrides[get_db_session] = fake_session
    client = TestClient(app)

    response = client.delete("/api/jobs/definitions/custom-job")

    assert response.status_code == 204
    assert deleted_ids == ["custom-job"]


def test_queue_native_job_definition_creates_run(
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
) -> None:
    saved_payload: dict[str, Any] = {}

    async def create_run(_session: object, **kwargs: object) -> JobRunRecord:
        saved_payload.update(kwargs)
        run = job_run_record()
        run.id = str(kwargs["run_id"])
        run.log_stdout_path = str(kwargs["log_stdout_path"])
        run.log_stderr_path = str(kwargs["log_stderr_path"])
        effective_parameters = kwargs["effective_parameters"]
        effective_command = kwargs["effective_command"]
        assert isinstance(effective_parameters, dict)
        assert isinstance(effective_command, list)
        run.effective_parameters = effective_parameters
        run.effective_command = effective_command
        return run

    monkeypatch.setattr(jobs_route, "create_job_run_record", create_run)

    app = app_with_scheduler_disabled(job_logs_dir=str(tmp_path))
    app.dependency_overrides[get_db_session] = fake_db_session(
        FakeSession(native_job_definition_record())
    )
    client = TestClient(app)

    response = client.post(
        "/api/jobs/definitions/custom-job/queue",
        json={"parameters": {"input_path": "/srv/data"}, "priority": "high"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["state"] == "queued"
    assert body["priority"] == "high"
    assert body["effective_parameters"]["input_path"] == "/srv/data"
    assert body["effective_command"] == ["python", "job.py", "--input", "/srv/data"]
    assert saved_payload["definition_id"] == "custom-job"
    assert Path(str(saved_payload["log_stdout_path"])).parent.exists()


def test_queue_native_job_preserves_parameter_values_with_spaces(
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
) -> None:
    saved_payload: dict[str, Any] = {}

    async def create_run(_session: object, **kwargs: object) -> JobRunRecord:
        saved_payload.update(kwargs)
        return job_run_record()

    monkeypatch.setattr(jobs_route, "create_job_run_record", create_run)

    app = app_with_scheduler_disabled(job_logs_dir=str(tmp_path))
    app.dependency_overrides[get_db_session] = fake_db_session(
        FakeSession(native_job_definition_record())
    )
    client = TestClient(app)

    response = client.post(
        "/api/jobs/definitions/custom-job/queue",
        json={"parameters": {"input_path": "/srv/data/folder with spaces"}},
    )

    assert response.status_code == 201
    assert saved_payload["effective_command"] == [
        "python",
        "job.py",
        "--input",
        "/srv/data/folder with spaces",
    ]


def test_queue_rejects_unsupported_execution_mode() -> None:
    app = app_with_scheduler_disabled()
    app.dependency_overrides[get_db_session] = fake_db_session(FakeSession(job_definition_record()))
    client = TestClient(app)

    response = client.post(
        "/api/jobs/definitions/custom-job/queue",
        json={"parameters": {"input_path": "/srv/data"}},
    )

    assert response.status_code == 409


def test_queue_requires_queue_time_parameters() -> None:
    app = app_with_scheduler_disabled()
    app.dependency_overrides[get_db_session] = fake_db_session(
        FakeSession(native_job_definition_record())
    )
    client = TestClient(app)

    response = client.post("/api/jobs/definitions/custom-job/queue", json={"parameters": {}})

    assert response.status_code == 422


def test_job_runs_endpoint_lists_recent_runs(monkeypatch: MonkeyPatch) -> None:
    async def list_counts(_session: object, _run_ids: list[str]) -> dict[str, int]:
        return {}

    async def list_runs(
        _session: object,
        *,
        state: str | None = None,
        definition_id: str | None = None,
        limit: int = 50,
        include_events: bool = False,
    ) -> list[JobRunRecord]:
        assert state == "queued"
        assert definition_id == "custom-job"
        assert limit == 10
        assert include_events is True
        run = job_run_record()
        run.events = [job_event_record()]
        return [run]

    monkeypatch.setattr(jobs_route, "list_job_run_records", list_runs)
    monkeypatch.setattr(jobs_route, "list_job_subjob_summaries", list_counts)

    app = app_with_scheduler_disabled()
    app.dependency_overrides[get_db_session] = fake_session
    client = TestClient(app)

    response = client.get("/api/jobs/runs?state=queued&definition_id=custom-job&limit=10")

    assert response.status_code == 200
    run = response.json()["runs"][0]
    assert run["id"] == "run-123"
    assert run["progress"] is None
    assert run["subjob_count"] == 0
    assert run["subjob_summary"] == {"finished": 0, "failed": 0, "total": 0}
    assert run["subjobs"] == []


def test_job_runs_endpoint_includes_subjob_summary_without_loading_subjobs(
    monkeypatch: MonkeyPatch,
) -> None:
    async def list_runs(
        _session: object,
        *,
        state: str | None = None,
        definition_id: str | None = None,
        limit: int = 50,
        include_events: bool = False,
    ) -> list[JobRunRecord]:
        assert include_events is True
        return [job_run_record()]

    async def list_counts(_session: object, run_ids: list[str]) -> dict[str, dict[str, int]]:
        assert run_ids == ["run-123"]
        return {"run-123": {"finished": 2, "failed": 1, "total": 5}}

    monkeypatch.setattr(jobs_route, "list_job_run_records", list_runs)
    monkeypatch.setattr(jobs_route, "list_job_subjob_summaries", list_counts)

    app = app_with_scheduler_disabled()
    app.dependency_overrides[get_db_session] = fake_session
    client = TestClient(app)

    response = client.get("/api/jobs/runs?include_subjobs=true")

    assert response.status_code == 200
    run = response.json()["runs"][0]
    assert run["subjob_count"] == 5
    assert run["subjob_summary"] == {"finished": 2, "failed": 1, "total": 5}
    assert run["subjobs"] == []


def test_job_runs_endpoint_can_include_subjobs(monkeypatch: MonkeyPatch) -> None:
    async def list_counts(_session: object, _run_ids: list[str]) -> dict[str, int]:
        return {}

    async def list_runs(
        _session: object,
        *,
        state: str | None = None,
        definition_id: str | None = None,
        limit: int = 50,
        include_events: bool = False,
    ) -> list[JobRunRecord]:
        assert include_events is True
        run = job_run_record()
        run.events = [job_event_record()]
        return [run]

    monkeypatch.setattr(jobs_route, "list_job_run_records", list_runs)
    monkeypatch.setattr(jobs_route, "list_job_subjob_summaries", list_counts)

    app = app_with_scheduler_disabled()
    app.dependency_overrides[get_db_session] = fake_session
    client = TestClient(app)

    response = client.get("/api/jobs/runs?include_subjobs=true")

    assert response.status_code == 200
    run = response.json()["runs"][0]
    assert run["subjobs"][0]["id"] == "cpt-batches/batch-1/001_item"
    assert run["subjob_count"] == 1
    assert run["subjob_summary"] == {"finished": 0, "failed": 0, "total": 1}
    assert run["subjobs"][0]["status"] == "running"
    assert run["subjobs"][0]["message"] == "CPT artifact run initialized"


def test_job_runs_endpoint_includes_latest_parent_progress(monkeypatch: MonkeyPatch) -> None:
    async def list_counts(_session: object, _run_ids: list[str]) -> dict[str, int]:
        return {}

    async def list_runs(
        _session: object,
        *,
        state: str | None = None,
        definition_id: str | None = None,
        limit: int = 50,
        include_events: bool = False,
    ) -> list[JobRunRecord]:
        assert include_events is True
        run = job_run_record()
        run.events = [job_event_record(), job_progress_event_record()]
        return [run]

    monkeypatch.setattr(jobs_route, "list_job_run_records", list_runs)
    monkeypatch.setattr(jobs_route, "list_job_subjob_summaries", list_counts)

    app = app_with_scheduler_disabled()
    app.dependency_overrides[get_db_session] = fake_session
    client = TestClient(app)

    response = client.get("/api/jobs/runs")

    assert response.status_code == 200
    run = response.json()["runs"][0]
    assert run["progress"] == {
        "current": 93.0,
        "total": 750.0,
        "unit": "item",
        "percent": 12.4,
    }
    assert run["subjobs"] == []


def test_cancel_job_run_endpoint(monkeypatch: MonkeyPatch) -> None:
    async def cancel_run(_session: object, run_id: str) -> JobRunRecord:
        assert run_id == "run-123"
        run = job_run_record()
        run.state = JobRunState.CANCELED.value
        return run

    monkeypatch.setattr(jobs_route, "request_cancel_job_run", cancel_run)

    app = app_with_scheduler_disabled()
    app.dependency_overrides[get_db_session] = fake_session
    client = TestClient(app)

    response = client.post("/api/jobs/runs/run-123/cancel")

    assert response.status_code == 200
    assert response.json()["state"] == "canceled"


def test_job_run_logs_endpoint_tails_file(monkeypatch: MonkeyPatch, tmp_path: Path) -> None:
    stdout_path = tmp_path / "stdout.log"
    stdout_path.write_text("line 1\nline 2\nline 3\n", encoding="utf-8")

    async def get_run(_session: object, run_id: str) -> JobRunRecord:
        assert run_id == "run-123"
        run = job_run_record()
        run.log_stdout_path = str(stdout_path)
        return run

    monkeypatch.setattr(jobs_route, "get_job_run_record", get_run)

    app = app_with_scheduler_disabled()
    app.dependency_overrides[get_db_session] = fake_session
    client = TestClient(app)

    response = client.get("/api/jobs/runs/run-123/logs?stream=stdout&tail=2")

    assert response.status_code == 200
    assert response.json()["lines"] == ["line 2", "line 3"]

import time

import pytest
from fastapi.testclient import TestClient

from app.api.dashboard import create_app
from app.memory.jobs import TERMINAL
from app.models.settings import Settings


def wait_job(client, job_id):
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        row = client.get(f"/jobs/{job_id}").json()
        if row["state"] in TERMINAL:
            return row
        time.sleep(.08)
    raise AssertionError(f"Job did not finish: {row}")


def test_real_background_job_and_bounded_retry(tmp_path):
    with TestClient(create_app(tmp_path, Settings(_env_file=None))) as client:
        config = client.get("/control").json()
        headers = {"x-swarm-token": config["token"]}
        job = client.post("/jobs", headers=headers, json={"task": "Demo plan", "provider": "demo"}).json()
        row = wait_job(client, job["id"])
        assert row["state"] == "succeeded", row
        run = client.get(f"/runs/{row['run_id']}").json()
        assert run["summary"]["status"] == "succeeded"
        assert run["artifacts"]["plan.md"]
        budget = client.post("/jobs", headers=headers, json={"task": "Demo implementation", "mode": "implement", "max_model_calls": 1}).json()
        limited = wait_job(client, budget["id"])
        assert limited["state"] == "budget_exceeded", limited
        assert client.get(f"/runs/{limited['run_id']}").json()["summary"]["status"] == "budget_exceeded"
        retry = client.post(f"/jobs/{job['id']}/retry", headers=headers, json={}).json()
        assert retry["retry_of"] == job["id"]
        assert wait_job(client, retry["id"])["state"] == "succeeded"


def test_control_rejects_cross_origin_bad_host_and_missing_session(tmp_path):
    with TestClient(create_app(tmp_path, Settings(_env_file=None))) as client:
        token = client.get("/control").json()["token"]
        payload = {"task": "Task"}
        assert client.post("/jobs", json=payload).status_code == 403
        assert client.post("/jobs", headers={"x-swarm-token": token, "origin": "https://evil.example"}, json=payload).status_code == 403
        assert client.get("/control", headers={"host": "evil.example"}).status_code == 403
        assert client.post("/jobs", headers={"x-swarm-token": "stale-session"}, json=payload).status_code == 403
        assert client.post("/jobs", headers={b"x-swarm-token": b"\xff"}, json=payload).status_code == 403
        assert client.post("/jobs", headers={"x-swarm-token": token, "origin": "http://[invalid"}, json=payload).status_code == 403
        assert client.get("/jobs").json() == []


@pytest.mark.parametrize("extra", [{"root": "C:/"}, {"commands": ["anything"]}, {"mode": "plan", "apply_changes": True}, {"max_repairs": 1}])
def test_browser_cannot_choose_root_commands_or_invalid_workflow(tmp_path, extra):
    with TestClient(create_app(tmp_path, Settings(_env_file=None))) as client:
        token = client.get("/control").json()["token"]
        assert client.post("/jobs", headers={"x-swarm-token": token}, json={"task": "Task", **extra}).status_code == 422


def test_operator_limits_cannot_be_exceeded_by_requests(tmp_path):
    with TestClient(create_app(tmp_path, Settings(_env_file=None, swarm_job_max_calls=4))) as client:
        token = client.get("/control").json()["token"]
        assert client.post("/jobs", headers={"x-swarm-token": token}, json={"task": "Task", "max_model_calls": 5}).status_code == 409


def test_credentials_stay_out_of_capabilities_and_queue_and_api_docs_are_local(tmp_path):
    sentinel = "test-only-key-never-persist"
    with TestClient(create_app(tmp_path, Settings(_env_file=None, nvidia_api_key=sentinel))) as client:
        config = client.get("/control")
        assert sentinel not in config.text
        assert client.get("/docs").status_code == 200
        assert "cdn.jsdelivr.net" not in client.get("/docs").text
        assert "script-src 'self'" in client.get("/docs").headers["content-security-policy"]
        headers = {"x-swarm-token": config.json()["token"]}
        result = client.post("/jobs", headers=headers, json={"task": "Demo plan", "provider": "demo"})
        assert sentinel not in result.text
        assert wait_job(client, result.json()["id"])["state"] == "succeeded"


def test_health_reports_a_failed_supervisor(tmp_path, monkeypatch):
    from app.orchestrator.jobs import JobManager
    def broken_tick(self):
        raise RuntimeError("Test supervisor failure")
    monkeypatch.setattr(JobManager, "_tick", broken_tick)
    with TestClient(create_app(tmp_path, Settings(_env_file=None))) as client:
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline and client.get("/health").status_code == 200:
            time.sleep(.02)
        assert client.get("/health").status_code == 503
        assert client.get("/control").status_code == 503


def test_real_worker_approval_and_syntax_repair_in_isolated_branch(tmp_path):
    import subprocess
    from pathlib import Path
    def git(*args):
        return subprocess.run(["git", *args], cwd=tmp_path, capture_output=True, text=True, check=True).stdout.strip()
    git("init", "-q")
    git("config", "user.name", "Demo")
    git("config", "user.email", "demo@example.invalid")
    (tmp_path / "original.txt").write_text("source remains unchanged")
    git("add", "original.txt")
    git("-c", "commit.gpgsign=false", "commit", "-qm", "Initial")
    branch = git("branch", "--show-current")
    with TestClient(create_app(tmp_path, Settings(_env_file=None))) as client:
        token = client.get("/control").json()["token"]
        headers = {"x-swarm-token": token}
        response = client.post("/jobs", headers=headers, json={"task": "Guided demo", "mode": "implement", "provider": "demo", "scenario": "repair_demo", "apply_changes": True, "max_repairs": 1})
        assert response.status_code == 202, response.text
        job = response.json()
        tickets = []
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            current = client.get(f"/jobs/{job['id']}").json()
            if current["state"] in TERMINAL:
                break
            approval = current["approval"]
            if approval and approval["ticket"] not in tickets:
                assert not (tmp_path / "swarm_demo_example.py").exists()
                assert client.post(f"/jobs/{job['id']}/approval", headers=headers, json={"ticket": "stale", "approve": True}).status_code == 409
                assert client.post(f"/jobs/{job['id']}/approval", headers=headers, json={"ticket": approval["ticket"], "approve": True}).status_code == 200
                tickets.append(approval["ticket"])
            time.sleep(.08)
        assert current["state"] == "succeeded", current
        assert len(set(tickets)) == 2
        data = client.get(f"/runs/{current['run_id']}").json()
        assert [attempt["validation_status"] for attempt in data["artifacts"]["attempts.json"]] == ["failed", "passed"]
        workspace = Path(data["summary"]["workspace_path"])
        assert (workspace / "swarm_demo_example.py").read_text() == "demo_value = 42\n"
        assert git("branch", "--show-current") == branch
        assert not (tmp_path / "swarm_demo_example.py").exists()

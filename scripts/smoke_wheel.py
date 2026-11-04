"""Exercise packaged workflows and a real approval/repair worker outside the checkout."""

import argparse
import gc
import os
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("wheel", nargs="?", type=Path)
    args = parser.parse_args()
    candidates = list(Path("dist").glob("*.whl"))
    wheel = args.wheel or (max(candidates, key=lambda p: p.stat().st_mtime) if candidates else None)
    if wheel is None:
        parser.error("Build a wheel first, or supply its path.")
    wheel = wheel.resolve()
    checkout = Path.cwd()
    old_pythonpath = os.environ.get("PYTHONPATH")
    with tempfile.TemporaryDirectory(prefix="swarm-wheel-smoke-") as temporary:
        folder = Path(temporary).resolve()
        assert folder.parent == Path(tempfile.gettempdir()).resolve() and folder.name.startswith("swarm-wheel-smoke-")
        package = folder / "package"
        with zipfile.ZipFile(wheel) as archive:
            for name in ["index.html", "dashboard.css", "dashboard.js", "mission.js"]:
                assert f"app/api/static/{name}" in archive.namelist(), name
            archive.extractall(package)
        try:
            os.chdir(folder)
            sys.path.insert(0, str(package))
            os.environ["PYTHONPATH"] = str(package) + (os.pathsep + old_pythonpath if old_pythonpath else "")
            import app
            from app.api.dashboard import create_app
            from app.models.settings import Settings
            from app.orchestrator.engine import Orchestrator
            from fastapi.testclient import TestClient
            assert Path(app.__file__).is_relative_to(package)
            root = folder / "workspace"
            root.mkdir()
            def git(*git_args):
                subprocess.run(["git", *git_args], cwd=root, capture_output=True, check=True)
            git("init", "-q")
            git("config", "user.name", "Wheel Smoke")
            git("config", "user.email", "smoke@example.invalid")
            (root / "original.txt").write_text("Original workspace\n", encoding="utf-8")
            git("add", "original.txt")
            git("-c", "commit.gpgsign=false", "commit", "-qm", "Initial")
            settings = Settings(_env_file=None, nvidia_provider_mode="demo", swarm_data_dir=folder / "data")
            engine = Orchestrator(root, settings)
            results = [engine.analyze_repo(), engine.plan("Plan demo"), engine.implement("Preview demo"), engine.review(), engine.release()]
            assert all(result.success for result in results)
            with TestClient(create_app(root, settings)) as client:
                assert client.get("/health").status_code == 200
                assert client.get("/").status_code == 200
                assert client.get("/docs").status_code == 200
                for name in ["dashboard.js", "mission.js", "dashboard.css"]:
                    assert client.get(f"/static/{name}").status_code == 200
                token = client.get("/control").json()["token"]
                headers = {"x-swarm-token": token}
                response = client.post("/jobs", headers=headers, json={"task": "Packaged repair demo", "mode": "implement", "provider": "demo", "scenario": "repair_demo", "apply_changes": True, "max_repairs": 1})
                assert response.status_code == 202, response.text
                job_id = response.json()["id"]
                tickets = set()
                deadline = time.monotonic() + 60
                while time.monotonic() < deadline:
                    job = client.get(f"/jobs/{job_id}").json()
                    if job["state"] in {"succeeded", "failed", "cancelled", "interrupted", "budget_exceeded"}:
                        break
                    approval = job["approval"]
                    if approval and approval["ticket"] not in tickets:
                        result = client.post(f"/jobs/{job_id}/approval", headers=headers, json={"ticket": approval["ticket"], "approve": True})
                        assert result.status_code == 200, result.text
                        tickets.add(approval["ticket"])
                    time.sleep(.08)
                assert job["state"] == "succeeded", job
                assert len(tickets) == 2
                evidence = client.get(f"/runs/{job['run_id']}").json()
                assert [attempt["validation_status"] for attempt in evidence["artifacts"]["attempts.json"]] == ["failed", "passed"]
                assert not (root / "swarm_demo_example.py").exists()
                assert (Path(evidence["summary"]["workspace_path"]) / "swarm_demo_example.py").read_text() == "demo_value = 42\n"
            print("PASS: built wheel outside checkout; five workflows, local assets/API, two approval tickets, real failed/passed validation, isolated worker")
        finally:
            os.chdir(checkout)
            if old_pythonpath is None:
                os.environ.pop("PYTHONPATH", None)
            else:
                os.environ["PYTHONPATH"] = old_pythonpath
            gc.collect()


if __name__ == "__main__":
    main()

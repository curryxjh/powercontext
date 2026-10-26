import json
import shutil
import subprocess
import sys
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
DOCUMENTS = (
    "minimax/manifest.json",
    "minimax/specs/order-list.md",
    "minimax/sample_app/orders.py",
    "minimax/tests/test_orders.py",
)


def test_reimport_and_cross_process_progress(tmp_path):
    project = tmp_path / "project"
    for relative_path in DOCUMENTS:
        destination = project / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPO / relative_path, destination)
    data_dir = tmp_path / "data"

    def run(*args):
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "minimax.sdd_context",
                *args,
                "--root",
                str(project),
                "--data-dir",
                str(data_dir),
            ],
            cwd=REPO,
            capture_output=True,
            text=True,
            check=True,
            timeout=120,
        )
        return json.loads(result.stdout)

    indexed = run("ingest")
    assert {item["category"] for item in indexed["indexed"]} == {"spec", "code", "test"}
    before = run("context", "--query", "status")
    assert {item["path"] for item in before["documents"]} == set(DOCUMENTS) - {"minimax/manifest.json"}
    assert before["progress"] is None

    run("save-state", "--completed", "baseline failed", "--pending", "fix filter")
    first_resume = run("resume", "--query", "status")
    assert first_resume["progress"]["record"]["pending"] == "fix filter"
    run("save-state", "--completed", "filter fixed", "--validation", "two tests passed")
    assert run("resume")["progress"]["record"]["completed"] == "filter fixed"

    spec_path = project / "minimax/specs/order-list.md"
    spec_path.write_text(spec_path.read_text().replace("empty list", "zero results"), encoding="utf-8")
    run("ingest")
    after = run("context", "--query", "status")
    old_spec = next(item for item in before["documents"] if item["category"] == "spec")
    new_spec = next(item for item in after["documents"] if item["category"] == "spec")
    assert old_spec["sha256"] != new_spec["sha256"]
    assert "zero results" in new_spec["content"]
    assert "empty list" not in new_spec["content"]

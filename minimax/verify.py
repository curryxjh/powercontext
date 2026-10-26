"""Run the same functional and compatibility tests against both code snapshots."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEST = ROOT / "minimax/tests/test_orders.py"
COMMAND = ["-m", "pytest", "-q", "-p", "no:cacheprovider", "minimax/tests/test_orders.py"]


def run_snapshot(source: Path) -> dict[str, object]:
    with tempfile.TemporaryDirectory(prefix="minimax-order-tests-") as directory:
        root = Path(directory)
        (root / "minimax/sample_app").mkdir(parents=True)
        (root / "minimax/tests").mkdir()
        (root / "minimax/__init__.py").write_text("")
        (root / "minimax/sample_app/__init__.py").write_text("")
        shutil.copyfile(source, root / "minimax/sample_app/orders.py")
        shutil.copyfile(TEST, root / "minimax/tests/test_orders.py")
        environment = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
        result = subprocess.run(
            [sys.executable, *COMMAND],
            cwd=root,
            env=environment,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        return {
            "command": "python " + " ".join(COMMAND),
            "code_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
            "test_sha256": hashlib.sha256(TEST.read_bytes()).hexdigest(),
            "exit_code": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
        }


def main() -> None:
    before = run_snapshot(ROOT / "minimax/evidence/orders-before.py")
    after = run_snapshot(ROOT / "minimax/sample_app/orders.py")
    print(json.dumps({"before": before, "after": after}, ensure_ascii=False, indent=2))
    if before["exit_code"] != 1 or after["exit_code"] != 0:
        raise SystemExit("Expected functional failure before and full pass after")


if __name__ == "__main__":
    main()

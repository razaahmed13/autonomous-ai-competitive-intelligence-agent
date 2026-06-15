from __future__ import annotations

import subprocess
import sys


def test_run_py_help_imports_local_package():
    result = subprocess.run(
        [sys.executable, "run.py", "--help"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert "AI competitive intelligence agent" in result.stdout

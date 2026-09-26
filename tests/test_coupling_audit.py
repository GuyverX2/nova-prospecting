import subprocess
import sys
from pathlib import Path


def test_coupling_audit_passes_for_standalone_sources():
    root = Path(__file__).resolve().parents[1]
    completed = subprocess.run([sys.executable, "scripts/audit-coupling.py"], cwd=root, capture_output=True, text=True)
    assert completed.returncode == 0, completed.stdout + completed.stderr

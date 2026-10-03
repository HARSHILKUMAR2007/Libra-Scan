"""Run pairing algorithm unit tests via node test runner inside pytest."""

import subprocess


def test_pairing_unit_tests():
    result = subprocess.run(["node", "--test", "tests/test_pairing.mjs"], capture_output=True, text=True)
    assert result.returncode == 0, f"Pairing unit tests failed:\n{result.stderr}\n{result.stdout}"

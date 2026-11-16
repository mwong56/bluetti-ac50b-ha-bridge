import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from bridge import energy_increment, load_token


class BridgeTests(unittest.TestCase):
    def test_integrates_watts_to_kwh(self):
        self.assertAlmostEqual(energy_increment(1000, 30), 1 / 120)

    def test_skips_gaps_and_invalid_intervals(self):
        for elapsed in (91, 3600, 0, -1):
            self.assertEqual(energy_increment(1000, elapsed), 0)

    def test_environment_token_takes_precedence(self):
        with patch.dict(os.environ, {"HA_ACCESS_TOKEN": "example-token"}):
            self.assertEqual(
                load_token({"token_file": "does-not-exist"}), "example-token"
            )

    def test_token_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "token.txt"
            path.write_text("example-token\n")
            with patch.dict(os.environ, {}, clear=True):
                self.assertEqual(load_token({"token_file": str(path)}), "example-token")

    def test_bashrc_assignment_is_read_without_execution(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bashrc"
            path.write_text(
                'exit 1\nexport HA_ACCESS_TOKEN="example-token" # comment\n'
            )
            with patch.dict(os.environ, {}, clear=True):
                self.assertEqual(
                    load_token({"bashrc_path": str(path)}), "example-token"
                )


if __name__ == "__main__":
    unittest.main()

from pathlib import Path
import stat
import tempfile
import unittest

from apm_notifier.config import save_env_values


class SaveEnvironmentTests(unittest.TestCase):
    def test_creates_from_template_and_updates_selected_values(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            template = root / ".env.example"
            target = root / ".env"
            template.write_text("TOKEN=\nUNCHANGED=yes\n", encoding="utf-8")
            save_env_values(target, {"TOKEN": "secret", "CHAT_ID": "123"}, template)
            self.assertEqual(
                target.read_text(encoding="utf-8"),
                "TOKEN=secret\nUNCHANGED=yes\n\nCHAT_ID=123\n",
            )
            self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o600)


if __name__ == "__main__":
    unittest.main()

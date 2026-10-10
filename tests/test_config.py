from pathlib import Path
import stat
import tempfile
import unittest

from apm_notifier.config import load_sources, save_env_values


class SaveEnvironmentTests(unittest.TestCase):
    def test_loads_priority_source_option_and_defaults_off(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sources.json"
            path.write_text(
                '{"sources":[{"id":"priority","name":"Priority",'
                '"urls":["https://jobs.example.com"],"priority":true},'
                '{"id":"regular","name":"Regular","urls":["https://jobs.example.com"]}]}',
                encoding="utf-8",
            )
            priority, regular = load_sources(path)
            self.assertTrue(priority.priority)
            self.assertFalse(regular.priority)

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

    def test_loads_adjacent_marketing_source_option(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sources.json"
            path.write_text(
                '{"sources":[{"id":"example","name":"Example",'
                '"urls":["https://jobs.example.com"],'
                '"include_adjacent_marketing":true}]}',
                encoding="utf-8",
            )
            sources = load_sources(path)
            self.assertTrue(sources[0].include_adjacent_marketing)

    def test_loads_growth_product_source_option(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sources.json"
            path.write_text(
                '{"sources":[{"id":"example","name":"Example",'
                '"urls":["https://jobs.example.com"],'
                '"include_growth_product_roles":true}]}',
                encoding="utf-8",
            )
            sources = load_sources(path)
            self.assertTrue(sources[0].include_growth_product_roles)

    def test_requested_company_sources_are_enabled(self) -> None:
        project_root = Path(__file__).resolve().parent.parent
        sources = load_sources(project_root / "config" / "sources.json")
        by_id = {source.id: source for source in sources}
        requested = {
            "autodesk-canada",
            "coinbase",
            "doordash",
            "duolingo",
            "linkedin",
            "lyft",
            "reddit",
            "snap",
            "visa",
            "zynga",
            "nvidia",
            "anthropic",
            "openai",
        }
        self.assertTrue(requested <= by_id.keys())
        self.assertTrue(all(by_id[source_id].include_adjacent_marketing for source_id in requested))
        self.assertTrue(
            all(
                '"locationCountry":["a30a87ed25634629aa6c3958aa2b91ea"]' in body
                for body in by_id["autodesk-canada"].request_bodies
            )
        )
        self.assertNotIn("adidas-canada", by_id)
        self.assertTrue(by_id["anthropic"].include_growth_product_roles)
        self.assertTrue(by_id["openai"].include_growth_product_roles)
        self.assertIn("figma", by_id)
        self.assertIn("questrade", by_id)
        self.assertTrue(by_id["mastercard-product"].include_product_specialists)
        self.assertTrue(by_id["mastercard-product"].paginate)
        self.assertTrue(by_id["questrade"].paginate)
        self.assertIn("revolut", by_id)
        self.assertIn("newgrad-community-backcheck", by_id)
        self.assertEqual(len(sources), 53)


if __name__ == "__main__":
    unittest.main()

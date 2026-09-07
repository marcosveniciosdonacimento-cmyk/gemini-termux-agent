import tempfile
import unittest
from pathlib import Path

import gemini_termux_agent as agent


class AgentTests(unittest.TestCase):
    def test_default_model_is_gemini_35_flash(self):
        self.assertEqual(agent.DEFAULT_MODEL, "gemini-3.5-flash")

    def test_safe_path_stays_inside_workspace(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            self.assertEqual(agent.safe_path(root, "src/main.py"), root / "src/main.py")
            with self.assertRaises(ValueError):
                agent.safe_path(root, "../outside.txt")

    def test_redact_hides_api_key_like_values(self):
        value = "GEMINI_API_KEY=AIzaSyExampleSecretValue123456789"
        self.assertNotIn("AIzaSyExampleSecretValue123456789", agent.redact(value))
        self.assertIn("[REDACTED]", agent.redact(value))

    def test_extract_commands_from_bash_block(self):
        answer = """Faça assim:\n```bash\npwd\npython -m unittest\n```"""
        self.assertEqual(agent.extract_commands(answer), ["pwd\npython -m unittest"])

    def test_command_pause_is_positive(self):
        self.assertGreater(agent.COMMAND_PAUSE_SECONDS, 0)
        self.assertEqual(agent.NIGHT_PAUSE_SECONDS, 1800)

    def test_ai_profiles_are_complete(self):
        self.assertEqual(set(agent.AI_PROFILES), {"alto", "baixo", "rapido"})
        for profile in agent.AI_PROFILES.values():
            self.assertIn("temperature", profile)
            self.assertIn("max_output_tokens", profile)
            self.assertIn("pause", profile)


if __name__ == "__main__":
    unittest.main()

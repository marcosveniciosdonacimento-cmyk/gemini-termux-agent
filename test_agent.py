import tempfile
import unittest
from pathlib import Path

import gemini_termux_agent as agent


class AgentTests(unittest.TestCase):
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
        self.assertEqual(agent.extract_commands(answer), ["pwd", "python -m unittest"])


if __name__ == "__main__":
    unittest.main()

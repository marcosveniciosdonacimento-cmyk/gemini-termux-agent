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

    def test_extract_preserves_here_doc_block(self):
        answer = """```bash\ncat > settings.gradle <<'EOF'\nrootProject.name = 'HelloWorld'\nEOF\n```"""
        self.assertIn("cat > settings.gradle", agent.extract_commands(answer)[0])

    def test_file_targets_are_reported(self):
        command = "cat > app/src/main/AndroidManifest.xml <<'EOF'\n<manifest/>\nEOF"
        self.assertIn("app/src/main/AndroidManifest.xml", agent.file_targets(command))

    def test_network_error_detection(self):
        self.assertTrue(agent.is_network_error("Gemini API HTTP 503: unavailable"))
        self.assertTrue(agent.is_network_error("Temporary failure in name resolution"))
        self.assertFalse(agent.is_network_error("arquivo Kotlin inválido"))

    def test_quota_error_detection(self):
        self.assertTrue(agent.is_quota_error("HTTP 429: quota exceeded"))
        self.assertTrue(agent.is_quota_error("resource exhausted"))
        self.assertFalse(agent.is_quota_error("arquivo não encontrado"))

    def test_create_file_tool_writes_real_workspace(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            result = agent.execute_tool(root, "create_file", {"path": "app/Main.kt", "content": "fun main() {}"})
            self.assertTrue(result["ok"])
            self.assertEqual((root / "app/Main.kt").read_text(encoding="utf-8"), "fun main() {}")

    def test_create_file_tool_reports_storage_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            result = agent.execute_tool(root, "create_file", {"path": "../outside.txt", "content": "x"})
            self.assertFalse(result["ok"])

    def test_command_pause_is_positive(self):
        self.assertGreater(agent.COMMAND_PAUSE_SECONDS, 0)
        self.assertEqual(agent.NIGHT_PAUSE_SECONDS, 1800)

    def test_ai_profiles_are_complete(self):
        self.assertEqual(set(agent.AI_PROFILES), {"alto", "baixo", "rapido"})
        for profile in agent.AI_PROFILES.values():
            self.assertIn("temperature", profile)
            self.assertIn("max_output_tokens", profile)
            self.assertIn("pause", profile)

    def test_model_options_include_default(self):
        self.assertTrue(any(model == agent.DEFAULT_MODEL for model, _ in agent.MODEL_OPTIONS))

    def test_gemini_key_lookup_is_local(self):
        config = {"api_key": "AIza_test"}
        self.assertEqual(agent.get_key(config), "AIza_test")

    def test_tool_declarations_are_real(self):
        names = {item["name"] for item in agent.TOOL_DECLARATIONS[0]["functionDeclarations"]}
        self.assertEqual(names, {"create_file", "run_shell_command"})

    def test_tool_response_reports_real_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            result = agent.execute_tool(root, "create_file", {"path": "real.txt", "content": "feito"})
            self.assertEqual(result["tool"], "create_file")
            self.assertTrue(result["ok"])
            self.assertTrue((root / "real.txt").is_file())

    def test_gradle_init_is_blocked(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = agent.execute_tool(Path(tmp).resolve(), "run_shell_command", {"command": "gradle init --type basic"})
            self.assertFalse(result["ok"])
            self.assertIn("gradle init bloqueado", result["error"])

    def test_artifact_request_detection(self):
        self.assertTrue(agent.task_requests_artifact("compile o APK debug"))
        self.assertTrue(agent.task_requests_artifact("crie um ZIP do projeto"))
        self.assertFalse(agent.task_requests_artifact("explique como funciona o Kotlin"))

    def test_project_artifacts_only_returns_real_build_outputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            apk = root / "app" / "build" / "outputs" / "apk" / "debug" / "app-debug.apk"
            apk.parent.mkdir(parents=True)
            apk.write_bytes(b"apk")
            (root / "app" / "build" / "outputs" / "apk" / "debug" / "empty.apk").touch()
            self.assertEqual(agent.project_artifacts(root), [apk])

    def test_setup_only_has_required_packages(self):
        setup = Path(__file__).with_name("setup.sh").read_text(encoding="utf-8")
        self.assertIn("REQUIRED_PACKAGES", setup)
        self.assertNotIn("EXTRA_PACKAGES", setup)
        self.assertIn("installed-packages.txt", setup)
        self.assertIn("environment-prepared", setup)
        for package in ("aapt", "aapt2", "apksigner", "d8", "ecj", "android-tools"):
            self.assertIn(package, setup)


if __name__ == "__main__":
    unittest.main()

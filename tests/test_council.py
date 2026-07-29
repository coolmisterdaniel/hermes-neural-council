from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "src" / "council.py"
FAKE = ROOT / "tests" / "fake_hermes.py"


class CouncilCliTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.hermes_home = self.base / "hermes-home"
        self.input = self.base / "материал.md"
        self.input.write_text("План проекта без секретов.\n", encoding="utf-8")
        self.log = self.base / "fake-args.json"
        self.env = os.environ.copy()
        self.env.update({
            "HERMES_HOME": str(self.hermes_home),
            "HNC_HERMES_BIN": str(FAKE),
            "HNC_FAKE_LOG": str(self.log),
        })

    def tearDown(self):
        self.tmp.cleanup()

    def run_cli(self, *args, ok=True, extra_env=None):
        env = self.env.copy()
        if extra_env:
            env.update(extra_env)
        result = subprocess.run(
            [sys.executable, str(SCRIPT), *map(str, args)],
            text=True,
            capture_output=True,
            env=env,
            check=False,
        )
        if ok and result.returncode != 0:
            self.fail(f"Команда упала: {result.stderr}\n{result.stdout}")
        if not ok and result.returncode == 0:
            self.fail(f"Команда неожиданно успешна: {result.stdout}")
        stream = result.stdout if result.returncode == 0 else result.stderr
        return result, json.loads(stream)

    def test_dry_run_shows_isolated_command_without_call(self):
        _, data = self.run_cli(
            "mini", "--profile", "council-1", "--input", self.input,
            "--topic", "проверка", "--dry-run",
        )
        self.assertTrue(data["dry_run"])
        self.assertFalse(self.log.exists())
        command = data["command"]
        self.assertIn("--ignore-rules", command)
        self.assertEqual(command[command.index("--toolsets") + 1], "safe")
        self.assertEqual(command[command.index("--profile") + 1], "council-1")
        self.assertEqual(command[-1], "<собранный запрос>")

    def test_mini_requires_confirmation(self):
        _, data = self.run_cli(
            "mini", "--profile", "council-1", "--input", self.input,
            ok=False,
        )
        self.assertIn("--confirm", data["error"])
        self.assertFalse(self.log.exists())

    def test_mini_saves_response_and_state(self):
        _, data = self.run_cli(
            "mini", "--profile", "council-1", "--input", self.input,
            "--topic", "архитектура", "--confirm",
        )
        response = Path(data["response"])
        self.assertEqual(response.read_text(encoding="utf-8"), "Ответ профиля council-1.\n")
        state = json.loads((response.parent / "state.json").read_text(encoding="utf-8"))
        self.assertEqual(state["successful_rounds"], 1)
        args = json.loads(self.log.read_text(encoding="utf-8"))[0]
        self.assertEqual(args[args.index("--profile") + 1], "council-1")
        self.assertIn("--ignore-rules", args)

    def test_secret_filename_and_content_are_blocked(self):
        env_file = self.base / ".env"
        env_file.write_text("HELLO=world\n", encoding="utf-8")
        _, first = self.run_cli(
            "mini", "--profile", "council-1", "--input", env_file,
            "--confirm", ok=False,
        )
        self.assertIn("заблокирован", first["error"])

        secret_file = self.base / "note.md"
        secret_file.write_text("api_key = sk-abcdefghijklmnopqrstuvwxyz123456\n", encoding="utf-8")
        _, second = self.run_cli(
            "mini", "--profile", "council-1", "--input", secret_file,
            "--confirm", ok=False,
        )
        self.assertIn("токена", second["error"])
        self.assertFalse(self.log.exists())

    def test_spor_three_rounds_profile_lock_and_ceiling(self):
        _, first = self.run_cli(
            "spor", "--profile", "council-1", "--input", self.input,
            "--topic", "схема", "--confirm",
        )
        conversation = Path(first["conversation"])
        rebuttal = self.base / "разбор.md"
        rebuttal.write_text("Оспариваю один пункт с обоснованием.\n", encoding="utf-8")

        _, changed = self.run_cli(
            "spor", "--profile", "council-2", "--input", rebuttal,
            "--conversation", conversation, "--confirm", ok=False,
        )
        self.assertIn("менять", changed["error"])

        for expected_round in (2, 3):
            _, data = self.run_cli(
                "spor", "--profile", "council-1", "--input", rebuttal,
                "--conversation", conversation, "--confirm",
            )
            self.assertEqual(data["round"], expected_round)

        _, ceiling = self.run_cli(
            "spor", "--profile", "council-1", "--input", rebuttal,
            "--conversation", conversation, "--confirm", ok=False,
        )
        self.assertIn("три успешных", ceiling["error"])
        state = json.loads((conversation / "state.json").read_text(encoding="utf-8"))
        self.assertEqual(state["successful_rounds"], 3)
        self.assertEqual(len(state["responses"]), 3)

    def test_failure_does_not_count_as_round(self):
        result, data = self.run_cli(
            "spor", "--profile", "council-1", "--input", self.input,
            "--topic", "сбой", "--confirm", ok=False,
            extra_env={"HNC_FAKE_MODE": "fail"},
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("кодом 7", data["error"])
        conversations = list((self.hermes_home / "neural-council").iterdir())
        state = json.loads((conversations[0] / "state.json").read_text(encoding="utf-8"))
        self.assertEqual(state["successful_rounds"], 0)
        self.assertEqual(state["attempts"], 1)

    def test_changed_source_is_rejected(self):
        _, first = self.run_cli(
            "spor", "--profile", "council-1", "--input", self.input,
            "--confirm",
        )
        conversation = Path(first["conversation"])
        (conversation / "source.md").write_text("Подменённый материал\n", encoding="utf-8")
        rebuttal = self.base / "разбор.md"
        rebuttal.write_text("Возражение\n", encoding="utf-8")
        _, data = self.run_cli(
            "spor", "--profile", "council-1", "--input", rebuttal,
            "--conversation", conversation, "--confirm", ok=False,
        )
        self.assertIn("изменён", data["error"])


class PackageTests(unittest.TestCase):
    def test_built_scripts_match_source(self):
        expected = hashlib.sha256(SCRIPT.read_bytes()).hexdigest()
        for name in ("mini-sovet", "spor"):
            built = ROOT / "skills" / name / "scripts" / "council.py"
            self.assertTrue(built.is_file())
            self.assertEqual(hashlib.sha256(built.read_bytes()).hexdigest(), expected)

    def test_skill_manifests_have_required_fields_and_portable_path(self):
        for name in ("mini-sovet", "spor", "consigliere"):
            text = (ROOT / "skills" / name / "SKILL.md").read_text(encoding="utf-8")
            self.assertIn(f"name: {name}", text)
            self.assertIn("description:", text)
            self.assertIn("version: 0.2.0", text)
            expected = "consigliere.py" if name == "consigliere" else "council.py"
            self.assertIn(f"${{HERMES_SKILL_DIR}}/scripts/{expected}", text)


if __name__ == "__main__":
    unittest.main()

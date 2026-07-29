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
SCRIPT = ROOT / "src" / "consigliere.py"
BUILT = ROOT / "skills" / "consigliere" / "scripts" / "consigliere.py"
FAKE = ROOT / "tests" / "fake_hermes.py"
SKILL = ROOT / "skills" / "consigliere"


class ConsigliereCliTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.hermes_home = self.base / "hermes-home"
        self.log = self.base / "fake-log.json"
        self.env = os.environ.copy()
        self.env.update({
            "HERMES_HOME": str(self.hermes_home),
            "HNC_HERMES_BIN": str(FAKE),
            "HNC_BUNDLE_DIR": str(SKILL),
            "HNC_FAKE_LOG": str(self.log),
        })
        _, prepared = self.run_cli("--prepare", "--topic", "тест")
        self.conversation = Path(prepared["conversation"])
        (self.conversation / "goal.md").write_text(
            "# Цель\nРешить, запускать ли проект.\n"
            "Входит рынок; не входит разработка.\n"
            "Итог: решение с условиями.\nДостаточно трёх проверяемых рисков.\n",
            encoding="utf-8",
        )
        (self.conversation / "brief.md").write_text(
            "# Бриф\nФакт: бюджет утверждён документом.\n"
            "Предположение: спрос высокий.\nОткрытый вопрос: требования рынка.\n",
            encoding="utf-8",
        )

    def tearDown(self):
        self.tmp.cleanup()

    def run_cli(self, *args, ok=True, extra_env=None):
        env = self.env.copy()
        if extra_env:
            env.update(extra_env)
        result = subprocess.run(
            [sys.executable, str(SCRIPT), *map(str, args)],
            text=True, capture_output=True, env=env, check=False,
        )
        if ok and result.returncode != 0:
            self.fail(f"Команда упала: {result.stderr}\n{result.stdout}")
        if not ok and result.returncode == 0:
            self.fail(f"Команда неожиданно успешна: {result.stdout}")
        stream = result.stdout if result.returncode == 0 else result.stderr
        return result, json.loads(stream)

    def common(self):
        return (
            "--conversation", self.conversation,
            "--profile", "council-1",
            "--research-profile", "council-2",
        )

    def calls(self):
        if not self.log.exists():
            return []
        return json.loads(self.log.read_text(encoding="utf-8"))

    def guard(self, verdict="ГОТОВО"):
        return self.run_cli(
            *self.common(), "--only-guard", "--confirm",
            extra_env={"HNC_FAKE_GUARD": f"Проверено.\nИТОГ: {verdict}"},
            ok=verdict in {"ГОТОВО", "НЕ ГОТОВО"},
        )

    def test_prepare_and_missing_inputs_are_clear(self):
        (self.conversation / "goal.md").unlink()
        _, data = self.run_cli(*self.common(), "--only-guard", "--dry-run", ok=False)
        self.assertIn("goal.md", data["error"])

    def test_missing_profile_stops_before_model_call(self):
        _, data = self.run_cli(
            *self.common(), "--only-guard", "--confirm", ok=False,
            extra_env={"HNC_FAKE_PROFILES": "council-1"},
        )
        self.assertIn("council-2", data["error"])
        self.assertEqual(self.calls(), [])

    def test_optional_critic_must_be_independent_profile(self):
        _, data = self.run_cli(
            *self.common(), "--critic-profile", "council-2",
            "--only-guard", "--dry-run", ok=False,
        )
        self.assertIn("отличаться", data["error"])
        self.assertEqual(self.calls(), [])

    def test_not_ready_stops_without_research(self):
        _, data = self.guard("НЕ ГОТОВО")
        self.assertEqual(data["guard"]["verdict"], "НЕ ГОТОВО")
        self.assertEqual(len(self.calls()), 1)
        _, blocked = self.run_cli(*self.common(), "--confirm", ok=False)
        self.assertIn("НЕ ГОТОВО", blocked["error"])
        self.assertEqual(len(self.calls()), 1)

    def test_changed_brief_rechecks_guard(self):
        self.guard("НЕ ГОТОВО")
        brief = self.conversation / "brief.md"
        brief.write_text(brief.read_text(encoding="utf-8") + "Новый факт.\n", encoding="utf-8")
        self.guard("ГОТОВО")
        self.assertEqual(len(self.calls()), 2)

    def test_unchanged_ready_guard_is_reused(self):
        self.guard("ГОТОВО")
        _, data = self.run_cli(*self.common(), "--only-guard", "--confirm")
        self.assertTrue(data["guard"]["cached"])
        self.assertEqual(len(self.calls()), 1)

    def test_full_run_uses_profiles_isolation_and_anonymization(self):
        self.guard("ГОТОВО")
        _, data = self.run_cli(
            *self.common(), "--critic-profile", "council-3", "--confirm",
        )
        self.assertTrue(Path(data["result"]).is_file())
        calls = self.calls()
        self.assertEqual(len(calls), 5)
        profiles = [call[call.index("--profile") + 1] for call in calls]
        self.assertEqual(profiles, [
            "council-1", "council-1", "council-2", "council-3", "council-1",
        ])
        for call in calls:
            self.assertIn("--ignore-rules", call)
            self.assertEqual(call[call.index("--toolsets") + 1], "safe")
        critique_prompt = calls[3][-1]
        self.assertNotIn("Claude", critique_prompt)
        self.assertNotIn("Codex", critique_prompt)

    def test_changed_inputs_after_maps_are_rejected(self):
        self.guard("ГОТОВО")
        self.run_cli(*self.common(), "--confirm")
        brief = self.conversation / "brief.md"
        brief.write_text(brief.read_text(encoding="utf-8") + "Изменение.\n", encoding="utf-8")
        _, data = self.run_cli(*self.common(), "--only-guard", "--confirm", ok=False)
        self.assertIn("старые карты", data["error"])
        self.assertEqual(len(self.calls()), 5)

    def test_dry_run_makes_no_model_call(self):
        _, data = self.run_cli(*self.common(), "--only-guard", "--dry-run")
        self.assertTrue(data["guard"]["dry_run"])
        self.assertEqual(self.calls(), [])

    def test_full_dry_run_lists_four_calls_after_ready_guard(self):
        self.guard("ГОТОВО")
        _, data = self.run_cli(*self.common(), "--dry-run")
        self.assertEqual(len(data["planned_calls"]), 4)
        self.assertEqual(
            [item["stage"] for item in data["planned_calls"]],
            ["research-a", "research-b", "critique", "judge"],
        )
        self.assertEqual(len(self.calls()), 1)

    def test_invalid_guard_response_is_not_cached(self):
        _, data = self.run_cli(
            *self.common(), "--only-guard", "--confirm", ok=False,
            extra_env={"HNC_FAKE_GUARD": "Кажется, можно начинать."},
        )
        self.assertIn("точную строку", data["error"])
        state = json.loads((self.conversation / "state.json").read_text(encoding="utf-8"))
        self.assertIsNone(state["guard"])


class ConsiglierePackageTests(unittest.TestCase):
    def test_built_script_matches_source(self):
        self.assertEqual(
            hashlib.sha256(SCRIPT.read_bytes()).hexdigest(),
            hashlib.sha256(BUILT.read_bytes()).hexdigest(),
        )

    def test_required_resources_exist(self):
        manifest = (SKILL / "SKILL.md").read_text(encoding="utf-8")
        for relative in (
            "SKILL.md", "assets/goal-template.md", "assets/brief-template.md",
            "references/readiness-criteria.md", "scripts/consigliere.py",
        ):
            self.assertTrue((SKILL / relative).is_file(), relative)
            if relative != "SKILL.md":
                self.assertIn(f"]({relative})", manifest)


if __name__ == "__main__":
    unittest.main()

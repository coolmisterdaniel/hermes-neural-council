#!/usr/bin/env python3
"""Подставная команда Hermes для тестов без модели и сети."""

import json
import os
import sys
from pathlib import Path

args = sys.argv[1:]

if args[:2] == ["profile", "show"]:
    available = set(os.environ.get(
        "HNC_FAKE_PROFILES", "council-1,council-2,council-3"
    ).split(","))
    profile = args[2] if len(args) > 2 else ""
    if profile not in available:
        print(f"Profile '{profile}' does not exist", file=sys.stderr)
        raise SystemExit(2)
    print(f"Profile: {profile}")
    raise SystemExit(0)

log_path = os.environ.get("HNC_FAKE_LOG")
if log_path:
    path = Path(log_path)
    entries = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
    entries.append(args)
    path.write_text(json.dumps(entries, ensure_ascii=False), encoding="utf-8")

mode = os.environ.get("HNC_FAKE_MODE", "ok")
if mode == "fail":
    print("подставной сбой", file=sys.stderr)
    raise SystemExit(7)
if mode == "empty":
    raise SystemExit(0)

profile = "unknown"
if "--profile" in args:
    profile = args[args.index("--profile") + 1]
prompt = args[-1] if args else ""

if "[ROLE:GUARD]" in prompt:
    print(os.environ.get(
        "HNC_FAKE_GUARD",
        "Все критерии подтверждены.\nИТОГ: ГОТОВО",
    ))
elif "[ROLE:RESEARCH-A]" in prompt:
    print(f"Карта Claude от профиля {profile}: факт A и источник.")
elif "[ROLE:RESEARCH-B]" in prompt:
    print(f"Карта Codex от профиля {profile}: факт B и источник.")
elif "[ROLE:CRITIQUE]" in prompt:
    print(f"Критика профиля {profile}: проверить два риска.")
elif "[ROLE:JUDGE]" in prompt:
    print(f"РЕШЕНИЕ профиля {profile}: продолжать при выполнении условий.")
else:
    print(f"Ответ профиля {profile}.")

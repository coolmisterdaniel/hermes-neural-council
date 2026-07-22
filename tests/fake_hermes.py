#!/usr/bin/env python3
"""Подставная команда Hermes для тестов без модели и сети."""

import json
import os
import sys
from pathlib import Path

log_path = os.environ.get("HNC_FAKE_LOG")
if log_path:
    Path(log_path).write_text(json.dumps(sys.argv[1:], ensure_ascii=False), encoding="utf-8")

mode = os.environ.get("HNC_FAKE_MODE", "ok")
if mode == "fail":
    print("подставной сбой", file=sys.stderr)
    raise SystemExit(7)
if mode == "empty":
    raise SystemExit(0)

profile = "unknown"
if "--profile" in sys.argv:
    profile = sys.argv[sys.argv.index("--profile") + 1]
print(f"Ответ профиля {profile}.")


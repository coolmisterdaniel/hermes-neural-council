#!/usr/bin/env python3
"""Собирает два самостоятельных Hermes-скилла из одного исходника."""

from pathlib import Path
import hashlib
import shutil

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src" / "council.py"
TARGETS = [
    ROOT / "skills" / "mini-sovet" / "scripts" / "council.py",
    ROOT / "skills" / "spor" / "scripts" / "council.py",
]


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    for target in TARGETS:
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(SOURCE, target)
        target.chmod(0o755)
    expected = digest(SOURCE)
    if any(digest(target) != expected for target in TARGETS):
        raise SystemExit("Сборка разошлась с исходником")
    print(f"Собрано: {len(TARGETS)} файла, sha256={expected}")


if __name__ == "__main__":
    main()


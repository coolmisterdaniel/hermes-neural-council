#!/usr/bin/env python3
"""Собирает самостоятельные Hermes-скиллы из исходников."""

from pathlib import Path
import hashlib
import shutil

ROOT = Path(__file__).resolve().parents[1]
BUILDS = [
    (
        ROOT / "src" / "council.py",
        ROOT / "skills" / "mini-sovet" / "scripts" / "council.py",
    ),
    (
        ROOT / "src" / "council.py",
        ROOT / "skills" / "spor" / "scripts" / "council.py",
    ),
    (
        ROOT / "src" / "consigliere.py",
        ROOT / "skills" / "consigliere" / "scripts" / "consigliere.py",
    ),
]


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    for source, target in BUILDS:
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        target.chmod(0o755)
        if digest(target) != digest(source):
            raise SystemExit(f"Сборка разошлась с исходником: {target}")
    print(f"Собрано: {len(BUILDS)} файла")


if __name__ == "__main__":
    main()

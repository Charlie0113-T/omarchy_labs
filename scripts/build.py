#!/usr/bin/env python3
"""Build omarchy-lab.pyz from src/. Run from anywhere: python3 scripts/build.py"""
from pathlib import Path
import zipapp

ROOT = Path(__file__).resolve().parent.parent
TARGET = ROOT / "omarchy-lab.pyz"


def include(path):
    return "__pycache__" not in path.parts and path.suffix != ".pyc"


zipapp.create_archive(ROOT / "src", TARGET, interpreter="/usr/bin/env python3", filter=include, compressed=True)
print(f"built {TARGET.relative_to(ROOT)} ({TARGET.stat().st_size:,} bytes)")

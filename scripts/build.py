#!/usr/bin/env python3
"""Build omarchy-lab.pyz from src/. Run from anywhere: python3 scripts/build.py"""
from pathlib import Path
import zipapp

ROOT = Path(__file__).resolve().parent.parent
# Release artifact, uploaded to GitHub Releases; the plugin runs src/ directly.
TARGET = ROOT / "dist" / "omarchy-lab.pyz"


def include(path):
    return "__pycache__" not in path.parts and path.suffix != ".pyc"


TARGET.parent.mkdir(exist_ok=True)
zipapp.create_archive(ROOT / "src", TARGET, interpreter="/usr/bin/env python3", filter=include, compressed=True)
print(f"built {TARGET.relative_to(ROOT)} ({TARGET.stat().st_size:,} bytes)")

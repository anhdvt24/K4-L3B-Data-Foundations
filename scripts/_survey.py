"""Survey repo to find dead files and oversized content."""
from pathlib import Path
import json

root = Path(r"c:\Users\Thai Anh\Desktop\VinAi\K4-L3B-Data-Foundations")

skip_dirs = {".venv", "__pycache__", ".git", ".pytest_cache", "node_modules", ".cursor"}

print("=" * 80)
print("FILES IN REPO (sorted by size, descending)")
print("=" * 80)
files = []
for p in root.rglob("*"):
    if not p.is_file():
        continue
    rel = p.relative_to(root)
    if any(part in skip_dirs for part in rel.parts):
        continue
    files.append((p.stat().st_size, p))

files.sort(reverse=True)
for size, p in files:
    print(f"{size:>8}  {p.relative_to(root)}")
print()
print(f"Total files (excluding venv, pycache, git, cursor): {len(files)}")

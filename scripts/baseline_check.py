"""Chạy baseline ChunkingStrategyComparator để có số liệu thực cho REPORT_NHOM.md."""
from __future__ import annotations

import io
import sys
from pathlib import Path

if hasattr(sys.stdout, "buffer") and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", line_buffering=True)

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.chunking import ChunkingStrategyComparator


def load_body(path: Path) -> str:
    raw = path.read_text(encoding="utf-8")
    parts = raw.split("---", 2)
    return parts[2].strip() if len(parts) >= 3 else raw


DATA = Path("data/ecommerce")
SAMPLES = [
    DATA / "quy-dinh-chung-tra-hang-hoan-tien.md",   # file vừa, có heading
    DATA / "thoi-gian-nhan-tien-hoan.md",             # file ngắn, có bảng
    DATA / "chinh-sach-tra-hang-hoan-tien.md",        # file dài nhất, ~26k chars
]

cmp = ChunkingStrategyComparator()
for p in SAMPLES:
    text = load_body(p)
    res = cmp.compare(text, chunk_size=500)
    print(f"\n=== {p.name} (len={len(text)}) ===")
    for strat, stats in res.items():
        print(
            f"  {strat:14} count={stats['count']:3d}  "
            f"avg_length={stats['avg_length']:7.1f}"
        )
"""CP2 checkpoint script — chạy từ thư mục gốc project."""
import csv
import re
import sys
from pathlib import Path

D = Path("data/ecommerce")
REQ = ["doc_id", "title", "source_url", "retrieved_at", "document_version", "audience"]

mds = sorted(p for p in D.glob("*.md"))
rows = list(csv.DictReader(open(D / "sources.csv", encoding="utf-8")))

ids = []
auds = {}
all_ok = True

for p in mds:
    raw = p.read_text(encoding="utf-8")
    parts = raw.split("---", 2)
    fm_block = parts[1] if len(parts) >= 2 else ""
    fm = dict(re.findall(r"^(\w+):\s*(.+)$", fm_block, re.M))

    ok = all(k in fm for k in REQ) and fm.get("doc_id") == p.stem
    if not ok:
        all_ok = False
    ids.append(fm.get("doc_id"))
    auds[fm.get("audience")] = auds.get(fm.get("audience"), 0) + 1

    mark = "OK" if ok else "THIEU METADATA"
    print(f"{p.name:42} {mark:18} audience={fm.get('audience')}")

print("-" * 70)
md_only = [x for x in mds if x.suffix == ".md"]
print(f"so file .md    : {len(md_only)}  (can 5-10)  {'OK' if 5 <= len(md_only) <= 10 else 'FAIL'}")

csv_ids = sorted([r["doc_id"] for r in rows])
md_ids = sorted(ids)
print(f"csv khop md    : {'OK' if csv_ids == md_ids else 'LECH'}")
if csv_ids != md_ids:
    print(f"  csv only: {set(csv_ids) - set(md_ids)}")
    print(f"  md  only: {set(md_ids) - set(csv_ids)}")

print(f"audience       : {auds}")
n_aud = len([k for k in auds if k])
print(f"so audience khac nhau: {n_aud}  {'OK' if n_aud >= 2 else 'FAIL'}")

print("-" * 70)
overall = all_ok and csv_ids == md_ids and 5 <= len(md_only) <= 10 and n_aud >= 2
print("CP2 OVERALL    :", "PASS" if overall else "FAIL")
sys.exit(0 if overall else 1)

"""Strip surrounding quotes from YAML values in frontmatter (YAML chuẩn)."""
import re
from pathlib import Path

D = Path("data/ecommerce")
fixed = 0
for p in D.glob("*.md"):
    raw = p.read_text(encoding="utf-8")
    parts = raw.split("---", 2)
    if len(parts) < 3:
        continue
    fm = parts[1]
    # Strip matching double quotes around a value: key: "value" -> key: value
    new_fm = re.sub(r'^(\w+):\s+"([^"]*)"\s*$', r"\1: \2", fm, flags=re.M)
    if new_fm != fm:
        p.write_text("---" + new_fm + "---" + parts[2], encoding="utf-8")
        fixed += 1
        print("fixed:", p.name)
print("total fixed:", fixed)

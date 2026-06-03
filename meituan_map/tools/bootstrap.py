from pathlib import Path
ROOT = Path(r"c:/Users/Administrator/Desktop/Project/meituan_map")
def w(rel, text):
    p = ROOT / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text.lstrip("\n"), encoding="utf-8")
    print("ok", rel)

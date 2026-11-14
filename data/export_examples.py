"""Writes a few synthetic documents and the register as plain files in examples/in, to try velo.py on a folder."""
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
dst = ROOT / "examples" / "in"
dst.mkdir(parents=True, exist_ok=True)
docs = [json.loads(l) for l in open(ROOT / "data" / "corpus.jsonl", encoding="utf-8")]
for d in docs[:12]:
    (dst / f"{d['id']}_{d['kind']}.txt").write_text(d["text"], encoding="utf-8")
shutil.copy(ROOT / "data" / "registro_formazione.csv", dst)
print(f"wrote 12 documents + register to {dst}")

import hashlib, json
from pathlib import Path
root = Path(__file__).resolve().parent
manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
for name, expected in manifest["files"].items():
    if hashlib.sha256((root / name).read_bytes()).hexdigest() != expected:
        raise SystemExit("Hash mismatch: " + name)
for row in json.loads((root / "corpus.json").read_text(encoding="utf-8")):
    if hashlib.sha256(row["text"].encode()).hexdigest() != row["text_sha256"]:
        raise SystemExit("Text mismatch: " + row["id"])
print("PASS: packaged files and text hashes verified; not historical PIT certification")

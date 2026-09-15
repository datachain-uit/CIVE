import hashlib, json
from pathlib import Path
root=Path(__file__).resolve().parent
m=json.loads((root/'manifest.json').read_text(encoding='utf-8'))
for name,digest in m['files'].items():
    if hashlib.sha256((root/name).read_bytes()).hexdigest()!=digest:
        raise SystemExit('Hash mismatch: '+name)
for row in json.loads((root/'corpus.json').read_text(encoding='utf-8')):
    if hashlib.sha256(row['text'].encode()).hexdigest()!=row['text_sha256']:
        raise SystemExit('Text mismatch: '+row['id'])
print('PASS: package and text hashes verified; not predictive or PIT certification')

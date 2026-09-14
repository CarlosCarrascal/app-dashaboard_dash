"""Package a previously built Angular frontend without changing its AWS output."""
from pathlib import Path
import shutil
import json

ROOT = Path(__file__).resolve().parents[2]
source = ROOT / 'frontend/dist/frontend/browser'
destination = ROOT / 'data/salida/cloudflare-pages'
if not (source / 'index.html').is_file():
    raise SystemExit('Run npm run build in frontend first')
if destination.exists():
    assert destination.resolve().is_relative_to((ROOT / 'data/salida').resolve())
    shutil.rmtree(destination)
shutil.copytree(source, destination)
shutil.copyfile(Path(__file__).with_name('worker.mjs'), destination / '_worker.js')
(destination / '_routes.json').write_text(json.dumps({
    'version': 1, 'include': ['/v1', '/v1/*', '/docs', '/docs/*', '/redoc', '/openapi.json'], 'exclude': []
}), encoding='utf-8')
(destination / '_headers').write_text('/*\n  X-Content-Type-Options: nosniff\n  Referrer-Policy: strict-origin-when-cross-origin\n  X-Frame-Options: SAMEORIGIN\n', encoding='utf-8')
print(destination)

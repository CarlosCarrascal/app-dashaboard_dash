"""Regenera la copia versionada del contrato OpenAPI v1."""

import json
import sys
from pathlib import Path

API_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = API_ROOT.parents[1]
sys.path.insert(0, str(API_ROOT / "src"))

from aquanqa_campo_api.main import app  # noqa: E402

target = REPO_ROOT / "docs" / "api" / "openapi-v1.json"
target.write_text(
    json.dumps(app.openapi(), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    encoding="utf-8",
)
print(target)

import json
from pathlib import Path

from aquanqa_campo_api.main import app

SNAPSHOT = Path(__file__).resolve().parents[4] / "docs" / "api" / "openapi-v1.json"


def test_openapi_coincide_con_la_copia_versionada():
    expected = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    assert app.openapi() == expected

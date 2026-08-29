from __future__ import annotations

import pandas as pd

from analitica.proyeccion.fuentes import _firma


def test_firma_snapshot_es_reproducible_y_detecta_mutacion():
    original = pd.DataFrame({"id": [2, 1], "valor": [20.0, 10.0]})
    reordenado = original.iloc[::-1].reset_index(drop=True)
    mutado = original.copy()
    mutado.loc[0, "valor"] = 21.0
    firma = _firma("fixture", {"tabla": original}, None)
    assert firma == _firma("fixture", {"tabla": reordenado}, None)
    assert firma != _firma("fixture", {"tabla": mutado}, None)

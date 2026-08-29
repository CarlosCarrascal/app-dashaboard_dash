"""Paquete ZIP autocontenido para auditoría y reproducción."""

from __future__ import annotations

import json
import platform
import shutil
import subprocess
import sys
import zipfile
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from analitica import settings

from .compartido.hashes import sha256_archivo
from .gobernanza import commit_actual
from .relaciones import DAG_AGRONOMICO
from .torneo import REGLA_PROMOCION


def _guardar_tabla(tabla: pd.DataFrame | None, ruta: Path):
    if tabla is not None and not tabla.empty:
        salida = tabla.copy()
        # Las familias del torneo pueden declarar `componentes` como dict, lista o
        # NaN según el modelo. Parquet necesita un único tipo Arrow; JSON conserva el
        # contenido auditable sin imponer una estructura falsa al contrato SQL jsonb.
        if "componentes" in salida:
            salida["componentes"] = salida["componentes"].map(
                lambda valor: (
                    json.dumps(valor, ensure_ascii=False, default=str)
                    if valor is not None and not (isinstance(valor, float) and pd.isna(valor))
                    else None
                )
            )
        salida.to_parquet(ruta, index=False)


def generar_model_card(
    tipo: str,
    fuente,
    metricas: pd.DataFrame | None,
    decisiones: pd.DataFrame | None,
) -> str:
    tabla_metricas = (
        "```text\n" + metricas.to_string(index=False) + "\n```"
        if metricas is not None and not metricas.empty
        else "Sin métricas."
    )
    tabla_decisiones = (
        "```text\n" + decisiones.to_string(index=False) + "\n```"
        if decisiones is not None and not decisiones.empty
        else "Sin decisión."
    )
    return f"""# Model card · Aqu Anqa analytics

Generada: {datetime.now(UTC).isoformat()}

## Propósito

Proyectar kg por lote-semana para compromiso operativo (1–2 semanas), planificación
(3–6) y escenario (7–10). R09 es el campeón inicial; XGBoost es challenger y modelo de
relaciones, no pronóstico oficial por autoridad.

## Datos y población

- Fuente efectiva: `{fuente.nombre}`; fallback: `{fuente.fallback}`.
- Firma del snapshot: `{fuente.firma}`.
- Cobertura: `{json.dumps(fuente.conteos, ensure_ascii=False)}`.
- Cultivo objetivo: Sekoya Pop en fundos Aqu Anqa. Literatura de otras variedades/localidades
  solo formula hipótesis; no aporta coeficientes transferidos.

## Evaluación fuera de muestra

{tabla_metricas}

## Decisión champion–challenger

{tabla_decisiones}

## Supuestos y límites

- Semántica as-of: ningún censo o clima posterior a la emisión entra a sus variables.
- El clima es común a varios módulos; el tamaño efectivo es menor que el número de filas.
- Hay colinealidad temperatura–DPV–GDD y poda dispersa dentro del módulo.
- Censos no versionados y fenología concentrada en 2026 limitan validación externa.
- Faltan polinización, suelo y nutrición completa. El pronóstico meteorológico solo entra
  cuando existe un payload as-of archivado; climatología y escenarios se etiquetan aparte.
- SHAP, ALE, ARDL y precedencia temporal son explicaciones predictivas/asociativas, no causas.
- `Componentes_identidad` usa como tercer factor las plantas del maestro del lote, que no
  varían dentro de la campaña y son la única cifra disponible al emitir. Cada fila declara la
  base con la que se calculó «frutos por planta».
- El objetivo de frutos por planta es la identidad despejada desde los kilos cosechados, no un
  censo independiente; el conteo de campo no está reconciliado con cosecha.
- `Componentes_identidad` hereda de R09 el calendario de semanas con cosecha: estima cuántos
  kilos salen de una semana productiva, no qué semanas lo son.
- `FenologicoComponentes_v1` crea su propia rejilla lote–semana, estima ocurrencia, frutos y
  peso por separado y compone kg esperados; continúa experimental hasta superar los gates.
- `R09_componentes_publicados` no entrena: reexpresa `frutos_total × peso_baya / 1000` del
  propio forecast, sin el factor plantas, y sirve como control de consistencia interna.

## Usos no permitidos

No usar como recomendación causal de riego, poda o nutrición; no extrapolar a otra variedad,
fundo o campaña sin backtesting externo; no sustituir el R09 si la regla de promoción falla.

## Ejecución

Tipo: `{tipo}` · commit: `{commit_actual() or "no disponible"}`.
"""


def exportar_paquete(
    tipo: str,
    datos,
    *,
    predicciones: pd.DataFrame | None = None,
    metricas: pd.DataFrame | None = None,
    relaciones: pd.DataFrame | None = None,
    inferencia: pd.DataFrame | None = None,
    claims: pd.DataFrame | None = None,
    matriz_relaciones: pd.DataFrame | None = None,
    relaciones_packing: pd.DataFrame | None = None,
    auditoria_ensamblaje: pd.DataFrame | None = None,
    evidencia_features: pd.DataFrame | None = None,
    decisiones: pd.DataFrame | None = None,
    calidad: pd.DataFrame | None = None,
    registro_mlflow: dict[str, object] | None = None,
    explicaciones: dict[str, pd.DataFrame] | None = None,
    directorio: Path | None = None,
) -> tuple[Path, str]:
    raiz = Path(directorio or settings.ANALYTICS_EXPORT_DIR)
    marca = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    trabajo = raiz / f"{tipo}-{marca}-{datos.fuente.firma[:8]}"
    trabajo.mkdir(parents=True, exist_ok=False)
    tablas = {
        "predicciones.parquet": predicciones,
        "metricas.parquet": metricas,
        "relaciones.parquet": relaciones,
        "inferencia.parquet": inferencia,
        "evidence_claim.parquet": claims,
        # Barrido exploratorio completo: se guarda entero para poder auditar cuántas
        # combinaciones se probaron, no solo las que sobrevivieron.
        "matriz_relaciones.parquet": matriz_relaciones,
        # Bloque de packing: calibre real al grano de módulo.
        "relaciones_packing.parquet": relaciones_packing,
        # Evidencia de que las uniones conservaron la granularidad agronómica.
        "auditoria_ensamblaje.parquet": auditoria_ensamblaje,
        "evidencia_features_modelo.parquet": evidencia_features,
        "decisiones.parquet": decisiones,
        "calidad.parquet": calidad,
    }
    for nombre, tabla in tablas.items():
        _guardar_tabla(tabla, trabajo / nombre)
    for nombre, tabla in (explicaciones or {}).items():
        _guardar_tabla(tabla, trabajo / f"explicacion_{nombre}.parquet")
    (trabajo / "snapshot.json").write_text(
        json.dumps(
            {
                "fuente": datos.fuente.nombre,
                "firma": datos.fuente.firma,
                "corte": datos.fuente.corte,
                "fallback": datos.fuente.fallback,
                "conteos": datos.fuente.conteos,
                "advertencias": datos.fuente.advertencias,
            },
            ensure_ascii=False,
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )
    (trabajo / "dag_agronomico.json").write_text(
        json.dumps(DAG_AGRONOMICO, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (trabajo / "regla_promocion.json").write_text(
        json.dumps(REGLA_PROMOCION, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    catalogo = settings._RAIZ_REPOSITORIO / "docs" / "cientifico" / "catalogo_evidencia.json"
    if catalogo.is_file():
        shutil.copy2(catalogo, trabajo / "referencias_cientificas.json")
    (trabajo / "model_card.md").write_text(
        generar_model_card(tipo, datos.fuente, metricas, decisiones), encoding="utf-8"
    )
    entorno = {
        "python": sys.version,
        "plataforma": platform.platform(),
        "commit": commit_actual(),
    }
    try:
        entorno["pip_freeze"] = subprocess.check_output(
            [sys.executable, "-m", "pip", "freeze"], text=True, timeout=30
        ).splitlines()
    except (OSError, subprocess.SubprocessError):
        entorno["pip_freeze"] = []
    (trabajo / "entorno.json").write_text(
        json.dumps(entorno, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    firma = {
        "inputs": {k: str(v) for k, v in datos.fuente.conteos.items()},
        "outputs": list(predicciones.columns) if predicciones is not None else [],
        "nota": "Firma de contrato; MLflow registra la firma nativa cuando está disponible.",
    }
    (trabajo / "firma_modelo.json").write_text(
        json.dumps(firma, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (trabajo / "mlflow_modelos.json").write_text(
        json.dumps(
            registro_mlflow or {"estado": "no_aplica", "modelos": []},
            ensure_ascii=False,
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )
    archivos = [p for p in trabajo.iterdir() if p.is_file()]
    manifiesto = {
        "version": "1.0.0",
        "tipo": tipo,
        "creado_en": datetime.now(UTC).isoformat(),
        "snapshot": datos.fuente.firma,
        "archivos": [
            {"ruta": p.name, "bytes": p.stat().st_size, "sha256": sha256_archivo(p)}
            for p in sorted(archivos)
        ],
    }
    (trabajo / "manifest.json").write_text(
        json.dumps(manifiesto, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    zip_ruta = raiz / f"{trabajo.name}.zip"
    with zipfile.ZipFile(zip_ruta, "w", compression=zipfile.ZIP_DEFLATED) as zipf:
        for archivo in sorted(trabajo.iterdir()):
            if archivo.is_file():
                zipf.write(archivo, arcname=archivo.name)
    return zip_ruta, sha256_archivo(zip_ruta)

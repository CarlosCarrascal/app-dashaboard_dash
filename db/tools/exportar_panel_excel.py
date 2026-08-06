"""Exporta reporting.v_analitica_modulo_semana a Excel para el análisis de variables.

Genera un libro con tres hojas: el panel filtrado a la campaña pedida, el diccionario de
columnas (para que nadie tenga que adivinar qué mide cada una ni qué advertencias tiene) y
la cobertura por módulo.

Uso:
    python db/tools/exportar_panel_excel.py                # C2025 por defecto
    python db/tools/exportar_panel_excel.py C2024
    python db/tools/exportar_panel_excel.py TODAS

Requiere el entorno `aquanqa` (pandas, openpyxl, psycopg) y las credenciales de .env.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pandas as pd
import psycopg

RAIZ = Path(__file__).resolve().parents[2]
SALIDA = RAIZ / "data" / "salida"

# Advertencias que viajan CON el dato. El panel se va a abrir en Excel y en Python por gente
# que no leyó el DDL, y tres de estas columnas se malinterpretan solas.
DICCIONARIO = [
    ("modulo_id", "LA CLAVE REAL del módulo. Úsala para agrupar o para entrenar un modelo.",
     "`modulo` (M01, M02...) NO es única globalmente: hay un M01 en Aqu Anqa 1 y OTRO M01 "
     "distinto en Aqu Anqa 2, con historias de poda y cosecha diferentes. Agrupar por "
     "`modulo` a solas los mezcla sin ningún error visible."),
    ("campania", "Campaña productiva.", ""),
    ("modulo", "Código del módulo tal como lo usa Agronomía (M01, M02...). Para LEER, no para agrupar.",
     "Se repite entre fundos — ver la advertencia de modulo_id."),
    ("fundo", "Fundo físico (Aqu Anqa 1..6).", ""),
    ("empresa", "Razón social.", ""),
    ("anio_semana", "Semana ISO en formato AAAA-SS. Clave temporal del panel.",
     "Usa el AÑO ISO, no el calendario: el par (año, semana) del calendario mezcla enero "
     "con diciembre en la misma celda."),
    ("semana_desde", "Primer día de la semana.", ""),
    ("semana_hasta", "Último día de la semana.", ""),
    ("kg", "Kilos cosechados en el módulo esa semana.",
     "Excluye los lotes ficticios L000, que son totales de módulo disfrazados de lote."),
    ("area_ha", "Área productiva del módulo (hectáreas).",
     "Suma de lotes reales con área > 0. Si se incluyeran los L000 subiría 37,6%."),
    ("kg_ha", "OBJETIVO. kg / area_ha.", ""),
    ("n_plantas", "Plantas del módulo.", ""),
    ("kg_planta", "kg / n_plantas.", ""),
    ("poda_ref", "Fecha de poda de referencia del módulo, media ponderada por área.", ""),
    ("edad_dias", "Días desde la poda hasta el fin de esa semana. Edad del fruto.",
     "VARÍA entre módulos: es una de las variables con poder explicativo transversal."),
    ("poda_dispersion_dias", "Días entre la poda más temprana y la más tardía del módulo.",
     "Si es alto, poda_ref representa mal al módulo y edad_dias es menos fiable."),
    ("temp_media", "Temperatura media de la semana (°C).",
     "IDÉNTICA para todos los módulos: una sola estación en todo el fundo."),
    ("temp_max", "Máxima de la semana (°C).", "Idéntica para todos los módulos."),
    ("temp_min", "Mínima de la semana (°C).", "Idéntica para todos los módulos."),
    ("gdd_semana", "Grados-día de crecimiento acumulados en la semana.",
     "Idéntica para todos los módulos. Calculada como max((Tmax+Tmin)/2 - base, 0) con "
     "base 10 °C (provisional, la decide Agronomía). NO es la columna dg_calentamiento "
     "del origen, que mide climatización y va en sentido inverso a la temperatura."),
    ("eto_semana_mm", "Evapotranspiración de la semana (mm).",
     "Idéntica para todos los módulos."),
    ("lluvia_semana_mm", "Lluvia de la semana (mm).", "Idéntica para todos los módulos."),
    ("humedad_media", "Humedad relativa media (%).", "Idéntica para todos los módulos."),
    ("gdd_acum_poda", "Grados-día acumulados DESDE LA PODA de este módulo.",
     "VARÍA entre módulos (rango medio 1.514 GDD en C2025) porque cada módulo se podó en "
     "otra fecha. Es la forma en que una estación única se vuelve una variable que "
     "discrimina por módulo: úsala en lugar de gdd_semana para explicar diferencias "
     "entre módulos."),
    ("eto_acum_poda_mm", "ETO acumulada desde la poda de este módulo (mm).",
     "VARÍA entre módulos. Es el mejor proxy disponible de demanda hídrica acumulada "
     "mientras no exista el dato de riego aplicado."),
    ("lluvia_acum_poda_mm", "Lluvia acumulada desde la poda (mm).", "VARÍA entre módulos."),
    ("registros_cosecha", "Filas de cosecha agregadas en esta celda.", ""),
    ("lotes_cosechados", "Lotes distintos cosechados esa semana.", ""),
    ("lotes_modulo", "Lotes productivos del módulo.", ""),
    ("pana_max", "Paña más alta registrada esa semana.", "Solo viene de H01."),
    ("peso_baya_medio", "Peso medio de baya (g) declarado en cosecha.", ""),
    ("dias_con_clima", "Días de la semana con registro climático.",
     "Si es < 7 el agregado semanal del clima está incompleto."),
    ("dias_incompletos", "Días con menos de 90 de las 96 lecturas esperadas.",
     "En esos días la máxima y la mínima son poco fiables, y con ellas el GDD."),
    ("dias_en_semana", "Días de calendario en la semana. Debe ser 7.", ""),
    ("riego_m3", "Agua total aplicada en la semana (m3). Suma de todos los turnos del módulo.",
     "Fuente: 4 Excel de Riego/Operaciones 2025, ajenos a Access, cargados 2026-08-06. "
     "Solo cubre Aqu Anqa 1-4 y M11 (de Aqu Anqa 5): en M16-M18 y Aqu Anqa 6 esta columna "
     "queda NULL, no 0 — 0 significaría 'se midió y no se regó'."),
    ("riego_mm", "LÁMINA de riego aplicada en la semana (mm). VARÍA entre módulos.",
     "Es la variable de riego que Access nunca tuvo. Junto con gdd_acum_poda, es de las "
     "pocas variables ambientales que sí discriminan entre módulos en la misma semana."),
    ("riego_dias_con_registro", "Días de la semana con registro de riego (de 7).", ""),
    ("riego_estimado", "true si la semana incluye el reparto M10A/M10B (decisión D-7).",
     "El origen no separa esos dos módulos; se reparte agua_m3 proporcional al área real "
     "de cada uno. lamina_mm NO se reparte (es una medida intensiva, no un volumen)."),
]


def env() -> dict[str, str]:
    """Lee .env sin depender de python-dotenv, que no está en todos los entornos."""
    valores = {}
    ruta = RAIZ / ".env"
    if ruta.exists():
        for linea in ruta.read_text(encoding="utf-8").splitlines():
            linea = linea.strip()
            if not linea or linea.startswith("#") or "=" not in linea:
                continue
            clave, _, valor = linea.partition("=")
            valores[clave.strip()] = valor.strip()
    # process.env gana, igual que en scripts/run.mjs
    for clave in ("PGHOST", "PGPORT", "PGDATABASE", "PGUSER", "PGPASSWORD"):
        if os.environ.get(clave):
            valores[clave] = os.environ[clave]
    return valores


def main() -> int:
    campania = (sys.argv[1] if len(sys.argv) > 1 else "C2025").upper()
    cfg = env()

    conn_str = (
        f"host={cfg.get('PGHOST', 'localhost')} port={cfg.get('PGPORT', '5432')} "
        f"dbname={cfg.get('PGDATABASE', 'aquanqa')} user={cfg.get('PGUSER', 'postgres')} "
        f"password={cfg.get('PGPASSWORD', '')}"
    )

    if campania == "TODAS":
        sql = "SELECT * FROM reporting.v_analitica_modulo_semana ORDER BY campania, anio_semana, modulo"
        params: tuple = ()
        etiqueta = "todas"
    else:
        sql = (
            "SELECT * FROM reporting.v_analitica_modulo_semana WHERE campania = %s "
            "ORDER BY anio_semana, modulo"
        )
        params = (campania,)
        etiqueta = campania

    # No se usa pd.read_sql_query: pandas advierte que solo da soporte a SQLAlchemy y que
    # otras conexiones DBAPI2 "no están probadas". Con el cursor el resultado es explícito.
    def consultar(cur, consulta: str, valores: tuple) -> pd.DataFrame:
        cur.execute(consulta, valores or None)
        columnas = [d.name for d in cur.description]
        return pd.DataFrame(cur.fetchall(), columns=columnas)

    with psycopg.connect(conn_str) as conn, conn.cursor() as cur:
        panel = consultar(cur, sql, params)
        cobertura = consultar(
            cur,
            """
            SELECT modulo, fundo,
                   count(*)                        AS semanas,
                   min(anio_semana)                AS primera_semana,
                   max(anio_semana)                AS ultima_semana,
                   round(sum(kg)/1000, 2)          AS toneladas,
                   max(area_ha)                    AS area_ha,
                   round(avg(kg_ha), 2)            AS kg_ha_medio,
                   round(max(kg_ha), 2)            AS kg_ha_max,
                   min(edad_dias)                  AS edad_min_dias,
                   max(edad_dias)                  AS edad_max_dias,
                   round(max(gdd_acum_poda), 1)    AS gdd_acum_final
            FROM reporting.v_analitica_modulo_semana
            WHERE (%s = 'todas' OR campania = %s)
            GROUP BY modulo, fundo
            ORDER BY toneladas DESC NULLS LAST
            """,
            (etiqueta, campania),
        )

    if panel.empty:
        print(f"ERROR: no hay filas para la campaña {campania}.", file=sys.stderr)
        return 1

    diccionario = pd.DataFrame(
        DICCIONARIO, columns=["columna", "que_mide", "advertencia"]
    )

    SALIDA.mkdir(parents=True, exist_ok=True)
    destino = SALIDA / f"panel_modulo_semana_{etiqueta}.xlsx"

    with pd.ExcelWriter(destino, engine="openpyxl") as xls:
        panel.to_excel(xls, sheet_name="panel", index=False)
        diccionario.to_excel(xls, sheet_name="diccionario", index=False)
        cobertura.to_excel(xls, sheet_name="cobertura_modulo", index=False)

        for hoja, df in (
            ("panel", panel),
            ("diccionario", diccionario),
            ("cobertura_modulo", cobertura),
        ):
            ws = xls.sheets[hoja]
            ws.freeze_panes = "A2"
            for i, col in enumerate(df.columns, start=1):
                ancho = max(len(str(col)), *(len(str(v)) for v in df[col].head(200))) + 2
                ws.column_dimensions[ws.cell(row=1, column=i).column_letter].width = min(ancho, 60)

    print(f"OK  {destino}")
    print(f"    panel            {len(panel):>6} filas x {len(panel.columns)} columnas")
    print(f"    diccionario      {len(diccionario):>6} columnas documentadas")
    print(f"    cobertura_modulo {len(cobertura):>6} módulos")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

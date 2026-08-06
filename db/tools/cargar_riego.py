"""Carga los 4 Excel de riego 2025 a raw.riego_diario.

Fuente: hoja "BASE DATOS" de cada libro, columnas 2-19 (AÑO..l/planta). Las columnas
20-55 (fertilizantes y su concentración iónica) no se leen — son la dimensión de
nutrición, fuera del alcance de este análisis de riego.

Idempotente: TRUNCATE + recarga completa, igual que el resto de las dimensiones del
modelo (ver el patrón en scripts/run.mjs).

Uso:
    python db/tools/cargar_riego.py [carpeta_con_los_4_xlsx]

Requiere el entorno `aquanqa` (openpyxl, psycopg) y las credenciales de .env.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import openpyxl
import psycopg

RAIZ = Path(__file__).resolve().parents[2]
CARPETA_DEFAULT = Path(r"C:\Users\CCARRASCAL\Downloads\OneDrive_1_6-8-2026")

# Fila 6 de cada archivo es el encabezado real; los datos empiezan en la fila 7.
FILA_ENCABEZADO = 6
FILA_INICIO_DATOS = 7

# Índice 0-based dentro de la tupla que devuelve openpyxl (columna 1 = índice 0).
COL_ANIO, COL_MES, COL_SEMANA, COL_FECHA, COL_MODULO, COL_TURNO = 1, 2, 3, 4, 5, 6
COL_AREA, COL_AGUA = 7, 8
COL_LAMINA, COL_REPOSICION, COL_M3HA, COL_LPLANTA = 15, 16, 17, 18


def env() -> dict[str, str]:
    valores = {}
    ruta = RAIZ / ".env"
    if ruta.exists():
        for linea in ruta.read_text(encoding="utf-8").splitlines():
            linea = linea.strip()
            if not linea or linea.startswith("#") or "=" not in linea:
                continue
            clave, _, valor = linea.partition("=")
            valores[clave.strip()] = valor.strip()
    for clave in ("PGHOST", "PGPORT", "PGDATABASE", "PGUSER", "PGPASSWORD"):
        if os.environ.get(clave):
            valores[clave] = os.environ[clave]
    return valores


def filas_de(archivo: Path, numero_archivo: int):
    wb = openpyxl.load_workbook(archivo, read_only=True, data_only=True)
    ws = wb["BASE DATOS"]
    for r in ws.iter_rows(min_row=FILA_INICIO_DATOS, values_only=True):
        if r[COL_FECHA] is None and r[COL_MODULO] is None:
            continue
        yield (
            numero_archivo,
            str(r[COL_ANIO]) if r[COL_ANIO] is not None else None,
            str(r[COL_MES]) if r[COL_MES] is not None else None,
            str(r[COL_SEMANA]) if r[COL_SEMANA] is not None else None,
            r[COL_FECHA].date().isoformat() if hasattr(r[COL_FECHA], "date") else r[COL_FECHA],
            str(r[COL_MODULO]) if r[COL_MODULO] is not None else None,
            str(r[COL_TURNO]) if r[COL_TURNO] is not None else None,
            str(r[COL_AREA]) if r[COL_AREA] is not None else None,
            str(r[COL_AGUA]) if r[COL_AGUA] is not None else None,
            str(r[COL_LAMINA]) if r[COL_LAMINA] is not None else None,
            str(r[COL_REPOSICION]) if r[COL_REPOSICION] is not None else None,
            str(r[COL_M3HA]) if r[COL_M3HA] is not None else None,
            str(r[COL_LPLANTA]) if r[COL_LPLANTA] is not None else None,
        )


def main() -> int:
    carpeta = Path(sys.argv[1]) if len(sys.argv) > 1 else CARPETA_DEFAULT
    archivos = sorted(
        f for f in carpeta.glob("*.xlsx") if not f.name.startswith("~$")
    )
    if len(archivos) != 4:
        print(
            f"ERROR: esperaba 4 archivos .xlsx en {carpeta}, encontré {len(archivos)}: "
            f"{[a.name for a in archivos]}",
            file=sys.stderr,
        )
        return 1

    cfg = env()
    conn_str = (
        f"host={cfg.get('PGHOST', 'localhost')} port={cfg.get('PGPORT', '5432')} "
        f"dbname={cfg.get('PGDATABASE', 'aquanqa')} user={cfg.get('PGUSER', 'postgres')} "
        f"password={cfg.get('PGPASSWORD', '')}"
    )

    total = 0
    with psycopg.connect(conn_str) as conn:
        with conn.cursor() as cur:
            cur.execute("TRUNCATE raw.riego_diario")
            for numero, archivo in enumerate(archivos, start=1):
                filas = list(filas_de(archivo, numero))
                with cur.copy(
                    "COPY raw.riego_diario (archivo, anio, mes, semana_origen, fecha, "
                    "modulo_local, turno_local, area_ha, agua_m3, lamina_mm, "
                    "reposicion_pct, m3_ha, l_planta) FROM STDIN"
                ) as copy:
                    for fila in filas:
                        copy.write_row(fila)
                print(f"  archivo {numero} ({archivo.name}): {len(filas)} filas")
                total += len(filas)
        conn.commit()

    print(f"OK  raw.riego_diario: {total} filas cargadas")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

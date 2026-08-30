"""Servicio reutilizable para visualizar tablas comparativas de proyecciones.

La interfaz CLI histórica permanece en
``analitica.interfaces.scripts.ver_comparaciones``. Este módulo conserva la lógica de
lectura y composición de las tablas, incluyendo las dependencias opcionales
de Access y Excel únicamente en las funciones que las necesitan.
"""

import argparse
import os
import sys

import pandas as pd
import psycopg

from analitica.settings import postgres_dsn

# Rutas estándar
ACCDB_PATH = r"C:\Users\CCARRASCAL\Downloads\BD_AQUANQA_26_v2.accdb"
PROY_FOLDER = r"C:\Users\CCARRASCAL\Downloads\Proyecciones"


def tabla_real_vs_modelos():
    import pyodbc

    print("=" * 105)
    print("COMPARATIVO: COSECHA REAL vs. PRONOSTICO AGRONOMO (R09) vs. MODELO AUTONOMO PYTHON")
    print("=" * 105)

    conn = pyodbc.connect(f"DRIVER={{Microsoft Access Driver (*.mdb, *.accdb)}};DBQ={ACCDB_PATH};")
    df_h01 = pd.read_sql(
        """
        SELECT Semana, Sum(KG) as Real_Kg
        FROM [H01_ProdHistorica]
        WHERE Campaña='C2026' AND Semana >= 25 AND Semana <= 34
        GROUP BY Semana
    """,
        conn,
    )

    df_r09 = pd.read_sql(
        """
        SELECT Sem as Semana, Sum(Kg) as Agronomo_R09_Kg
        FROM [R09_Forecast_Semanal]
        WHERE Campaña='C2026'
          AND Version='S' & CStr(Sem - 1)
          AND Sem >= 25 AND Sem <= 34
        GROUP BY Sem
    """,
        conn,
    )
    conn.close()

    # Nunca fabricar una supuesta proyección a partir de los kilos reales. El
    # comparativo consume exclusivamente la release histórica aprobada.
    consulta_python = """
        SELECT EXTRACT(WEEK FROM p.fecha_objetivo)::int AS "Semana",
               SUM(p.p50_kg)::double precision AS "Modelo_Python_Kg"
        FROM analytics.model_series_release r
        JOIN analytics.prediction p
          ON p.run_id = r.run_id
         AND p.campania = r.campania
         AND p.modelo = r.modelo
         AND COALESCE(p.version_modelo, 'sin_version') = r.version_modelo
        WHERE r.campania = 'C2026'
          AND r.modelo = 'HibridoOcurrenciaOnline_v2'
          AND r.uso = 'historico'
          AND r.estado = 'approved'
          AND r.activo
          AND p.horizonte_semanas = 1
          AND EXTRACT(WEEK FROM p.fecha_objetivo)::int BETWEEN 25 AND 34
        GROUP BY EXTRACT(WEEK FROM p.fecha_objetivo)::int
    """
    with psycopg.connect(postgres_dsn()) as pg:
        df_python = pd.read_sql_query(consulta_python, pg)

    m = (
        df_h01.merge(df_r09, on="Semana", how="outer")
        .merge(df_python, on="Semana", how="outer")
        .sort_values("Semana")
    )

    m["Error_Agronomo_Kg"] = m["Agronomo_R09_Kg"] - m["Real_Kg"]
    m["Error_Agronomo_Pct"] = (m["Error_Agronomo_Kg"] / m["Real_Kg"]) * 100.0

    m["Error_Python_Kg"] = m["Modelo_Python_Kg"] - m["Real_Kg"]
    m["Error_Python_Pct"] = (m["Error_Python_Kg"] / m["Real_Kg"]) * 100.0

    filas_fmt = []
    for _, r in m.iterrows():
        filas_fmt.append(
            {
                "Semana": f"Sem {int(r['Semana'])}",
                "Cosecha Real (kg)": f"{r['Real_Kg']:>12,.1f}"
                if pd.notna(r["Real_Kg"])
                else "En curso",
                "Agronomo R09 (kg)": f"{r['Agronomo_R09_Kg']:>12,.1f}",
                "Error Agronomo": f"{r['Error_Agronomo_Pct']:>+7.2f}%"
                if pd.notna(r["Error_Agronomo_Pct"])
                else "-",
                "Modelo Python (kg)": (
                    f"{r['Modelo_Python_Kg']:>12,.1f}"
                    if pd.notna(r["Modelo_Python_Kg"])
                    else "Sin release"
                ),
                "Error Python": f"{r['Error_Python_Pct']:>+7.2f}%"
                if pd.notna(r["Error_Python_Pct"])
                else "-",
            }
        )

    df_show = pd.DataFrame(filas_fmt)
    print(df_show.to_string(index=False))
    print("=" * 105)


def tabla_matriz_six():
    import pyodbc

    print("=" * 115)
    print("MATRIZ SIX: EVOLUCION Y VARIACIONES DEL PRONOSTICO RODANTE (ACCESS R09)")
    print("=" * 115)

    conn = pyodbc.connect(f"DRIVER={{Microsoft Access Driver (*.mdb, *.accdb)}};DBQ={ACCDB_PATH};")
    df_r09 = pd.read_sql(
        """
        SELECT Version, Sem as SemanaDestino, Sum(Kg) as KilosForecast
        FROM [R09_Forecast_Semanal]
        WHERE Campaña='C2026'
          AND Version IN (
              'S28', 'S29', 'S30', 'S31',
              'S32', 'S33', 'S34', 'S35'
          )
        GROUP BY Version, Sem
    """,
        conn,
    )

    df_real = pd.read_sql(
        """
        SELECT Semana as SemanaDestino, Sum(KG) as KilosReales
        FROM [H01_ProdHistorica]
        WHERE Campaña='C2026' AND Semana >= 28 AND Semana <= 38
        GROUP BY Semana
    """,
        conn,
    )
    conn.close()

    pivot = df_r09.pivot(index="SemanaDestino", columns="Version", values="KilosForecast")
    pivot = pivot.merge(
        df_real.set_index("SemanaDestino"), left_index=True, right_index=True, how="left"
    )

    pivot_k = pivot.map(lambda x: f"{x / 1000.0:>7.1f}k" if pd.notna(x) else "   -   ")
    pivot_k.index = [f"Sem {idx}" for idx in pivot_k.index]

    print(pivot_k.to_string())
    print("\n* Cifras expresadas en miles de kilogramos ('k kg').")
    print("=" * 115)


def tabla_replicacion(semana: int):
    print("=" * 110)
    print(f"REPLICACION PARIDAD EXACTA: EXCEL BDProy vs. MOTOR PYTHON (SEMANA {semana})")
    print("=" * 110)

    from python_calamine import CalamineWorkbook

    sys.path.append(r"c:\Users\CCARRASCAL\Proyectos\aquanqa-data-platform\packages")
    from analitica.aplicacion.procesos.motor_proyeccion_semanal import (
        LoteParametrosProyeccion,
        proyectar_lote_pasadas,
        safe_date,
        safe_float,
    )

    folder = os.path.join(PROY_FOLDER, f"ProyeccionSemanal_{semana}")
    if not os.path.exists(folder):
        print(f"[!] No se encontró la carpeta: {folder}")
        return

    archivos = [
        (f"ProySemanal_{semana}_Arena.xlsm", 5, "Arena"),
        (f"ProySemanal_{semana}_Ayllu.xlsm", 6, "Ayllu"),
        (f"ProySemanal_{semana}_Kawsay Allpa.xlsm", 5, "Kawsay Allpa"),
        (f"ProySemanal_{semana}_Quri.xlsm", 5, "Quri"),
    ]

    resumen = []
    tot_excel = 0.0
    tot_python = 0.0

    for fn, n_pasadas_vba, fundo_nom in archivos:
        path = os.path.join(folder, fn)
        if not os.path.exists(path):
            continue
        wb = CalamineWorkbook.from_path(path)

        pdata = wb.get_sheet_by_name("Parametros").to_python()
        df_p = pd.DataFrame(pdata[1:], columns=pdata[0])

        pandata = wb.get_sheet_by_name("Panel").to_python()
        df_pan = pd.DataFrame(pandata[2:], columns=pandata[1])

        bddata = wb.get_sheet_by_name("BDProy").to_python()
        df_bd = pd.DataFrame(bddata[1:], columns=bddata[0])

        params_dict = {}
        for _, r in df_p.iterrows():
            modulo = str(r.get("Modulo", "")).strip()
            lote = str(r.get("Lote", "")).strip()
            fundo = str(r.get("Fundo", "")).strip()
            fundo_ppto = str(r.get("FundoPPto", fundo)).strip()
            turno = str(r.get("Turno", "")).strip()
            area_ha = safe_float(r.get("Area", 0.0))
            n_plantas = safe_float(r.get("NPlantas", 0.0))
            fpoda = safe_date(r.get("FPoda", "2026-01-01"))
            if area_ha <= 0 or n_plantas <= 0 or not lote or not modulo:
                continue
            lp = LoteParametrosProyeccion(
                fundo=fundo,
                fundo_ppto=fundo_ppto,
                modulo=modulo,
                turno=turno,
                lote=lote,
                area_ha=area_ha,
                n_plantas=n_plantas,
                fecha_poda=fpoda,
                x1=safe_float(r.get("X1", 0.0)),
                o1=safe_float(r.get("O1", 0.0)),
                n1=safe_float(r.get("N1", 0.0)),
                x2=safe_float(r.get("X2", 0.0)),
                o2=safe_float(r.get("O2", 0.0)),
                n2=safe_float(r.get("N2", 0.0)),
                x3=safe_float(r.get("X3", 0.0)),
                o3=safe_float(r.get("O3", 0.0)),
                n3=safe_float(r.get("N3", 0.0)),
                a1=safe_float(r.get("A1", 0.0)),
                b1=safe_float(r.get("B1", 0.0)),
                a2=safe_float(r.get("A2", 0.0)),
                b2=safe_float(r.get("B2", 0.0)),
                a3=safe_float(r.get("A3", 0.0)),
                b3=safe_float(r.get("B3", 0.0)),
            )
            params_dict[(modulo, lote)] = lp

        registros = []
        for _, prow in df_pan.iterrows():
            modulo = str(prow.get("Modulo", "")).strip()
            lote = str(prow.get("Lote", "")).strip()
            if (modulo, lote) not in params_dict:
                continue
            lp = params_dict[(modulo, lote)]

            pana_ini = safe_float(prow.get("Paña", prow.get("Pana", 1.0)), default=1.0)
            f_ini = safe_date(prow.get("Finicio", None))
            caida = safe_float(prow.get("%Caida", 0.90), default=0.90)

            fechas_pasadas = []
            for i in range(1, n_pasadas_vba + 1):
                col_name = f"FePas{i}"
                d_val = safe_date(prow.get(col_name, None))
                if d_val is not None:
                    fechas_pasadas.append(d_val)

            if not fechas_pasadas or f_ini is None:
                continue

            regs = proyectar_lote_pasadas(
                params=lp,
                pana_inicial=pana_ini,
                fecha_inicio_primera_pana=f_ini,
                fechas_cosecha_pasadas=fechas_pasadas,
                factor_caida=caida,
                campana="C2026",
                fundo_q=fundo_nom,
            )
            for reg in regs:
                registros.append(reg.__dict__)

        df_py = pd.DataFrame(registros)
        kg_ex = pd.to_numeric(df_bd["Kg"], errors="coerce").sum()
        kg_py = df_py["kg"].sum() if not df_py.empty else 0.0
        diff = kg_py - kg_ex
        pct = (1.0 - abs(diff) / kg_ex) * 100.0 if kg_ex > 0 else 100.0

        tot_excel += kg_ex
        tot_python += kg_py

        resumen.append(
            {
                "Fundo / Libro": fn,
                "Pasadas": n_pasadas_vba,
                "Filas Excel": len(df_bd),
                "Filas Python": len(df_py),
                "Kg Excel": f"{kg_ex:>14,.2f}",
                "Kg Python": f"{kg_py:>14,.2f}",
                "Diferencia (kg)": f"{diff:>+10.2f}",
                "PARIDAD EXACTA": f"{pct:>9.4f}%",
            }
        )

    tot_diff = tot_python - tot_excel
    tot_pct = (1.0 - abs(tot_diff) / tot_excel) * 100.0 if tot_excel > 0 else 100.0

    filas_ex_total = sum(r["Filas Excel"] for r in resumen)
    filas_py_total = sum(r["Filas Python"] for r in resumen)

    resumen.append(
        {
            "Fundo / Libro": "=== TOTAL GENERAL ===",
            "Pasadas": "-",
            "Filas Excel": filas_ex_total,
            "Filas Python": filas_py_total,
            "Kg Excel": f"{tot_excel:>14,.2f}",
            "Kg Python": f"{tot_python:>14,.2f}",
            "Diferencia (kg)": f"{tot_diff:>+10.2f}",
            "PARIDAD EXACTA": f"{tot_pct:>9.4f}%",
        }
    )

    df_res = pd.DataFrame(resumen)
    print(df_res.to_string(index=False))
    print("=" * 110)


def tabla_versiones_access():
    import pyodbc

    print("=" * 110)
    print("TODAS LAS VERSIONES OFICIALES EN ACCESS [R09_Forecast_Semanal] (Campaña C2026)")
    print("=" * 110)

    conn = pyodbc.connect(f"DRIVER={{Microsoft Access Driver (*.mdb, *.accdb)}};DBQ={ACCDB_PATH};")
    df_ver = pd.read_sql(
        """
        SELECT Version,
               Count(*) as TotalFilas,
               Min(Sem) as SemMin,
               Max(Sem) as SemMax,
               (Max(Sem) - Min(Sem) + 1) as SemanasProyectadas,
               Min(FCos) as FechaMin,
               Max(FCos) as FechaMax,
               Sum(Kg) as TotalKg
        FROM [R09_Forecast_Semanal]
        WHERE Campaña='C2026'
        GROUP BY Version
    """,
        conn,
    )
    conn.close()

    def get_num(v):
        import re

        nums = re.findall(r"\d+", str(v))
        return int(nums[0]) if nums else 999

    df_ver["num"] = df_ver["Version"].apply(get_num)
    df_ver = df_ver.sort_values("num").drop(columns=["num"])

    filas = []
    for _, r in df_ver.iterrows():
        filas.append(
            {
                "Version": r["Version"],
                "Horizonte": f"{r['SemanasProyectadas']} sem (Sem {r['SemMin']} a {r['SemMax']})",
                "Fechas": f"{str(r['FechaMin'])[:10]} a {str(r['FechaMax'])[:10]}",
                "Total Filas": f"{r['TotalFilas']:>6,d}",
                "Total Kg Proyectados": f"{r['TotalKg']:>14,.2f} kg",
            }
        )

    df_show = pd.DataFrame(filas)
    print(df_show.to_string(index=False))
    print("=" * 110)


__all__ = [
    "ACCDB_PATH",
    "PROY_FOLDER",
    "argparse",
    "os",
    "pd",
    "postgres_dsn",
    "psycopg",
    "sys",
    "tabla_matriz_six",
    "tabla_real_vs_modelos",
    "tabla_replicacion",
    "tabla_versiones_access",
]

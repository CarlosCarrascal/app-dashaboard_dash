"""Integración auditable de M_Poda con el panel módulo × semana.

M_Poda está a nivel de lote y usa el vocabulario presupuestal de fundo. El panel de
IA.final.xlsx está a nivel de módulo y usa los nombres de fundo de campo. Esta capa hace
esa traducción explícita y conserva la dispersión de poda para no convertir un promedio
de lotes en una fecha exacta que el dato no tiene.
"""

from __future__ import annotations

import io

import numpy as np
import pandas as pd


MAPA_FUNDO_PODA: dict[str, str] = {
    "Arena Azul": "Aqu Anqa",
    "Quri Allpa": "Aqu Anqa II",
    "Kawsay Allpa": "Aqu Anqa II",
    "Ayllu Allpa": "Aqu Anqa II",
}

_COLUMNAS = [
    "Campania", "FundoPoda", "Variedad", "Modulo", "Turno", "Lote",
    "AreaPoda", "FSiembra", "FInicio",
]


def _fecha_ponderada(grupo: pd.DataFrame, columna: str) -> pd.Timestamp | pd.NaT:
    """Promedio de fecha ponderado por área, sin perder la precisión temporal."""
    valido = grupo.dropna(subset=[columna, "AreaPoda"]).copy()
    if valido.empty:
        return pd.NaT
    fechas = pd.to_datetime(valido[columna], errors="coerce").dropna()
    valido = valido.loc[fechas.index]
    if valido.empty:
        return pd.NaT
    ns = fechas.astype("datetime64[ns]").astype("int64").to_numpy(dtype=float)
    pesos = pd.to_numeric(valido["AreaPoda"], errors="coerce").fillna(0).to_numpy(dtype=float)
    if pesos.sum() <= 0:
        return pd.to_datetime(int(ns.mean()))
    return pd.to_datetime(int(np.average(ns, weights=pesos)))


def _moda_ponderada(grupo: pd.DataFrame, columna: str) -> str | pd.NA:
    valido = grupo.dropna(subset=[columna]).copy()
    if valido.empty:
        return pd.NA
    pesos = pd.to_numeric(valido["AreaPoda"], errors="coerce").fillna(0)
    suma = valido.assign(_peso=pesos).groupby(columna, dropna=True)["_peso"].sum()
    return str(suma.sort_values(ascending=False).index[0]) if not suma.empty else pd.NA


def _agregar_por_modulo(poda: pd.DataFrame) -> pd.DataFrame:
    filas: list[dict[str, object]] = []
    for (fundo, modulo), grupo in poda.groupby(["FundoPoda", "Modulo"], dropna=False):
        fechas = pd.to_datetime(grupo["FInicio"], errors="coerce").dropna()
        filas.append({
            "_fundo_poda": fundo,
            "Modulo": modulo,
            "poda_fecha": _fecha_ponderada(grupo, "FInicio"),
            "poda_fecha_min": fechas.min() if not fechas.empty else pd.NaT,
            "poda_fecha_max": fechas.max() if not fechas.empty else pd.NaT,
            "poda_dispersion_dias": (
                int((fechas.max() - fechas.min()).days) if not fechas.empty else pd.NA
            ),
            "poda_n_lotes": int(len(grupo)),
            "poda_area_ha": float(pd.to_numeric(grupo["AreaPoda"], errors="coerce").sum()),
            "Variedad": _moda_ponderada(grupo, "Variedad"),
            "FSiembra": _fecha_ponderada(grupo, "FSiembra"),
            "poda_n_fechas": int(fechas.nunique()),
            "poda_nulos_fecha": int(grupo["FInicio"].isna().sum()),
            "poda_campania": str(grupo["Campania"].iloc[0]),
        })
    return pd.DataFrame(filas)


def _gdd_observado_desde_poda(tabla: pd.DataFrame) -> pd.DataFrame:
    """Acumulado de GDD de semanas observadas después de la poda.

    No se presenta como acumulado fisiológico completo: el clima disponible empieza en
    2025 y el panel solo conserva semanas con cosecha. Las columnas de cobertura hacen
    explícita esa limitación.
    """
    tabla = tabla.copy()
    tabla["gdd_acum_poda_obs"] = np.nan
    tabla["gdd_semanas_poda_obs"] = 0
    for _, grupo in tabla.sort_values("nsem").groupby("celda"):
        acumulado = 0.0
        cuenta = 0
        for indice, fila in grupo.iterrows():
            if pd.notna(fila.get("dias_desde_poda")) and fila.dias_desde_poda >= 0:
                gdd = fila.get("gdd_semana")
                if pd.notna(gdd):
                    acumulado += float(gdd)
                    cuenta += 1
                tabla.loc[indice, "gdd_acum_poda_obs"] = acumulado
                tabla.loc[indice, "gdd_semanas_poda_obs"] = cuenta
    return tabla


def integrar_poda(
    tabla: pd.DataFrame,
    contenido: bytes | None,
    hallazgos: list,
    anio: int = 2025,
) -> pd.DataFrame:
    """Añade poda, edad y tiempo biológico proxy al panel existente."""
    if not contenido:
        hallazgos.append(_hallazgo(
            "poda_no_cargada", "No se cargó M_Poda.xlsx", "media",
            "El panel no tiene fecha de poda ni días desde poda.",
            "El control temporal queda limitado a la semana calendario; no se puede leer "
            "la relación clima–resultado en tiempo biológico.",
        ))
        return tabla

    try:
        crudo = pd.read_excel(io.BytesIO(contenido), sheet_name=0)
    except Exception as exc:  # noqa: BLE001 — el panel debe degradar sin romperse
        hallazgos.append(_hallazgo(
            "poda_formato", "No se pudo leer M_Poda.xlsx", "media",
            f"La lectura del archivo de poda falló: {exc}.",
            "El panel continúa, pero no incorpora el reloj biológico.",
        ))
        return tabla

    if crudo.shape[1] < len(_COLUMNAS):
        hallazgos.append(_hallazgo(
            "poda_formato", "M_Poda.xlsx no tiene el formato esperado", "media",
            f"El archivo trae {crudo.shape[1]} columnas y se esperaban al menos "
            f"{len(_COLUMNAS)}.",
            "No se incorporan las variables de poda.",
        ))
        return tabla

    poda = crudo.iloc[:, :len(_COLUMNAS)].copy()
    poda.columns = _COLUMNAS
    poda["Campania"] = poda["Campania"].astype(str).str.strip()
    poda["FundoPoda"] = poda["FundoPoda"].astype(str).str.strip()
    poda["Modulo"] = poda["Modulo"].astype(str).str.strip().replace(
        {"M10A": "M10", "M10B": "M10"}
    )
    poda["AreaPoda"] = pd.to_numeric(poda["AreaPoda"], errors="coerce")
    for columna in ("FSiembra", "FInicio"):
        poda[columna] = pd.to_datetime(poda[columna], errors="coerce")

    if f"C{anio}" in set(poda["Campania"]):
        poda = poda[poda["Campania"] == f"C{anio}"].copy()
    else:
        disponible = sorted(poda["Campania"].dropna().unique().tolist())
        hallazgos.append(_hallazgo(
            "poda_campania", "M_Poda no contiene la campaña del panel", "media",
            f"Se buscó C{anio}; el archivo trae {disponible}.",
            "No se cruzan campañas distintas para evitar una fecha de poda falsa.",
        ))
        return tabla

    agregado = _agregar_por_modulo(poda)
    base = tabla.copy()
    base["_fundo_poda"] = base["Fundo"].map(MAPA_FUNDO_PODA)
    sin_alias = int(base["_fundo_poda"].isna().sum())
    if sin_alias:
        hallazgos.append(_hallazgo(
            "poda_alias_fundo", "Fundo sin equivalencia para M_Poda", "media",
            f"{sin_alias} filas del panel no tienen una equivalencia documentada entre "
            "el nombre de campo y el nombre presupuestal de M_Poda.",
            "Esas filas quedan sin poda en vez de asignarse por aproximación textual.",
        ))

    base = base.merge(
        agregado, on=["_fundo_poda", "Modulo"], how="left", validate="many_to_one"
    )
    base = base.drop(columns=["_fundo_poda"])

    base_date = pd.Timestamp(f"{anio}-01-01")
    base["fecha_semana_aprox"] = base_date + pd.to_timedelta(
        (base["nsem"].astype(int) - 1) * 7 + 3, unit="D"
    )
    base["dias_desde_poda"] = (
        base["fecha_semana_aprox"] - pd.to_datetime(base["poda_fecha"])
    ).dt.days.astype("float")
    base["edad_planta_anos"] = (
        base["fecha_semana_aprox"] - pd.to_datetime(base["FSiembra"])
    ).dt.days / 365.25
    base["poda_previa_ventana_clima"] = (
        pd.to_datetime(base["poda_fecha"]) < base_date
    )
    base = _gdd_observado_desde_poda(base)

    n_match = int(base["poda_fecha"].notna().sum())
    n_modulos = int(base.loc[base["poda_fecha"].notna(), "celda"].nunique())
    hallazgos.append(_hallazgo(
        "poda_integrada", "Poda integrada al panel", "baja",
        f"Se cruzaron {n_match} de {len(base)} celdas y {n_modulos} módulos con "
        f"M_Poda C{anio}. La fecha del módulo es un promedio ponderado por área de sus lotes.",
        "Ahora se pueden ordenar las curvas por días desde poda y no solo por semana calendario.",
    ))

    dispersos = agregado[agregado["poda_dispersion_dias"].fillna(0) > 30]
    if not dispersos.empty:
        nombres = ", ".join(
            f"{fundo}·{modulo} ({int(dispersion)} d)"
            for fundo, modulo, dispersion in dispersos[
                ["_fundo_poda", "Modulo", "poda_dispersion_dias"]
            ].itertuples(index=False, name=None)
        )
        hallazgos.append(_hallazgo(
            "poda_dispersa_modulo", "La fecha de poda no es homogénea dentro del módulo", "alta",
            f"{len(dispersos)} módulos tienen más de 30 días entre la primera y la última "
            f"poda de sus lotes: {nombres}.",
            "Días desde poda es un proxy de módulo. Para impacto agronómico fino hace falta "
            "bajar la cosecha y el clima al lote o usar una fase ponderada por área.",
        ))

    pre = int((base["dias_desde_poda"] < 0).sum())
    if pre:
        hallazgos.append(_hallazgo(
            "poda_antes_de_cosecha", "Hay cosecha antes de la poda promedio del módulo", "media",
            f"{pre} celdas quedan con días desde poda negativos al usar la fecha ponderada "
            "por lote.",
            "No se eliminan: señalan que el módulo contiene lotes con calendarios distintos "
            "o que la semana es una fecha aproximada. No deben interpretarse como una fase "
            "fenológica exacta.",
        ))

    if bool(base["poda_previa_ventana_clima"].any()):
        n_incompleto = int(base["poda_previa_ventana_clima"].sum())
        hallazgos.append(_hallazgo(
            "gdd_poda_incompleto", "El clima no cubre todo el ciclo desde la poda", "media",
            f"{n_incompleto} celdas tienen poda antes del 1 de enero de {anio}; el clima "
            "disponible empieza en S01.",
            "El GDD desde poda se etiqueta como observado desde la ventana disponible; no "
            "se presenta como acumulado fisiológico completo.",
        ))
    return base


def _hallazgo(clave: str, titulo: str, gravedad: str, detalle: str, efecto: str):
    """Evita importar Hallazgo al cargar el módulo y crear una dependencia circular."""
    from nucleo.datos import Hallazgo

    return Hallazgo(clave, titulo, gravedad, detalle, efecto)

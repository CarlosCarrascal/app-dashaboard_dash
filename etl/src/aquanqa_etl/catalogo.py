"""Catálogo de objetos a migrar: qué se extrae, de dónde, a dónde y cuántas filas se esperan.

Es el único sitio donde vive el mapeo nombre-de-origen → nombre-de-destino. Los nombres de
origen se escriben **exactamente** como están en Access, con sus espacios, acentos y eñes
(`[Ramas <5]`, `[# Ramas]`, `[Campaña]`, `[Paña]`, `[ET-mm]`): el extractor los entrecomilla
con corchetes al construir el SELECT.

`filas_esperadas` viene de `docs/auditoria/evidencia/04_metricas_validacion.txt` §1. No es
decorativo: si la extracción trae otra cifra, la carga lo marca como desviación y hay que
repetirla antes de seguir.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Tabla:
    """Una tabla de origen y su destino en `raw`."""

    origen: str
    destino: str
    columnas: tuple[tuple[str, str], ...]
    """Pares (nombre en el origen, nombre en raw), en el orden del origen."""
    filas_esperadas: int | None = None
    nota: str = ""

    @property
    def cols_origen(self) -> tuple[str, ...]:
        return tuple(o for o, _ in self.columnas)

    @property
    def cols_destino(self) -> tuple[str, ...]:
        return tuple(d for _, d in self.columnas)

    def select(self) -> str:
        """SELECT con los nombres de origen entre corchetes, como exige Jet/ACE."""
        cols = ", ".join(f"[{c}]" for c in self.cols_origen)
        return f"SELECT {cols} FROM [{self.origen}]"


# ── Evaluaciones fenológicas ────────────────────────────────────────────────────

E01_RAMAS = Tabla(
    origen="E01_Ramas",
    destino="e01_ramas",
    filas_esperadas=94_236,
    nota="El grano es la rama, no la planta: [# Ramas] es el índice de rama 1-33 (N-1).",
    columnas=(
        ("Id", "id_origen"),
        ("Actividad", "actividad"),
        ("Evaluador", "evaluador"),
        ("Fecha", "fecha"),
        ("Fundo", "fundo"),
        ("Modulo", "modulo"),
        ("Lote", "lote"),
        ("Cortina", "cortina"),
        ("Hilera", "hilera"),
        ("Planta", "planta"),
        ("Ramas <5", "ramas_lt5"),
        ("Ramas >5", "ramas_gt5"),
        ("# Ramas", "num_ramas"),
        ("Diametro", "diametro"),
    ),
)

E02_CONTEO_FLORES = Tabla(
    origen="E02_ConteoFlores",
    destino="e02_conteo_flores",
    filas_esperadas=43_490,
    columnas=(
        ("Item", "item"),
        ("Fecha", "fecha"),
        ("Evaluador", "evaluador"),
        ("Fundo", "fundo"),
        ("Modulo", "modulo"),
        ("Lote", "lote"),
        ("Cortina", "cortina"),
        ("Hilera", "hilera"),
        ("Planta", "planta"),
        ("nFlores", "n_flores"),
        ("Cuajo", "cuajo"),
        ("YA", "ya"),
        ("YP", "yp"),
        ("Hora", "hora"),
    ),
)

E03_CONTEO_ESTADOS = Tabla(
    origen="E03_ConteoEstados",
    destino="e03_conteo_estados",
    filas_esperadas=18_714,
    columnas=(
        ("Item", "item"),
        ("Fecha", "fecha"),
        ("Evaluador", "evaluador"),
        ("Fundo", "fundo"),
        ("Modulo", "modulo"),
        ("Lote", "lote"),
        ("Cortina", "cortina"),
        ("Hilera", "hilera"),
        ("Planta", "planta"),
        ("E1", "e1"),
        ("E2", "e2"),
        ("E3", "e3"),
        ("E4", "e4"),
        ("E5", "e5"),
        ("Total", "total"),
        ("F16", "f16"),
    ),
)

E04_BROTES = Tabla(
    origen="E04_Brotes",
    destino="e04_brotes",
    filas_esperadas=3_385,
    nota="Solo 3.385 filas porque la PK del origen no incluye Fecha y rechaza la segunda "
    "evaluación de la misma planta (H-02).",
    columnas=(
        ("Piso", "piso"),
        ("Fecha", "fecha"),
        ("Evaluador", "evaluador"),
        ("Fundo", "fundo"),
        ("Modulo", "modulo"),
        ("Lote", "lote"),
        ("Cortina", "cortina"),
        ("Hilera", "hilera"),
        ("Planta", "planta"),
        ("Brotes", "brotes"),
        ("Des1", "des1"),
        ("Des2", "des2"),
        ("Des3", "des3"),
        ("Des4", "des4"),
        ("Des5", "des5"),
        ("Hora", "hora"),
    ),
)

E05_DIAMETROS_BAYAS = Tabla(
    origen="E05_DiametrosBayas",
    destino="e05_diametros_bayas",
    filas_esperadas=4_193,
    nota="Una fila = una baya medida, ~97 por hilera y fecha (N-7).",
    columnas=(
        ("Modulo", "modulo"),
        ("Turno", "turno"),
        ("Lote", "lote"),
        ("Cortina", "cortina"),
        ("Hilera", "hilera"),
        ("Diametro", "diametro"),
        ("Fecha", "fecha"),
    ),
)

# ── Cosecha y packing ───────────────────────────────────────────────────────────

H00_VOLUMEN_CAMPO = Tabla(
    origen="H00_VolumenCampo",
    destino="h00_volumen_campo",
    filas_esperadas=30_812,
    nota="Incluye 1 fila de subtotal de Excel con 930.662,06 kg (H-06).",
    columnas=(
        ("Campaña", "campania"),
        ("Fecha", "fecha"),
        ("Fundo", "fundo"),
        ("Variedad", "variedad"),
        ("Modulo", "modulo"),
        ("Lote", "lote"),
        ("KG", "kg"),
    ),
)

H01_PROD_HISTORICA = Tabla(
    origen="H01_ProdHistorica",
    destino="h01_prod_historica",
    filas_esperadas=30_626,
    nota="Incluye 2 filas de subtotal (H-06) y tiene 187 filas menos que H00 (H-07).",
    columnas=(
        ("Fundo", "fundo"),
        ("Campaña", "campania"),
        ("Modulo", "modulo"),
        ("Turno", "turno"),
        ("Lote", "lote"),
        ("nPlantas", "n_plantas"),
        ("Fecha", "fecha"),
        ("Semana", "semana"),
        ("KG", "kg"),
        ("Paña", "pana"),
        ("Peso", "peso"),
    ),
)

H02_BD_ELIFAB = Tabla(
    origen="H02_BDElifab",
    destino="h02_bd_elifab",
    filas_esperadas=117_536,
    nota="Su grano no baja a lote: [Lote] es una nota de packing (N-2).",
    columnas=(
        ("Clases", "clases"),
        ("Recuento", "recuento"),
        ("Peso total (kg)", "peso_total_kg"),
        ("%", "porcentaje"),
        ("Lote", "lote"),
        ("Programa de clasificación", "programa_clasificacion"),
        ("Contenedores esperados", "contenedores_esperados"),
        ("Contenedores volcados", "contenedores_volcados"),
        ("Peso total (kg)2", "peso_total_kg2"),
        ("Hora de inicio", "hora_inicio"),
        ("Hora de finalización", "hora_finalizacion"),
        ("Fecha Cosecha", "fecha_cosecha"),
        ("Fecha Proceso", "fecha_proceso"),
        ("Productor1", "productor1"),
        ("Variedad", "variedad"),
        ("Modulo", "modulo"),
        ("Turno", "turno"),
        ("Calibrador", "calibrador"),
        ("ACDT", "acdt"),
        ("Calibre", "calibre"),
        ("ACDT 2", "acdt2"),
        ("ENSAYO", "ensayo"),
        ("Mercado", "mercado"),
        ("Semana", "semana"),
        ("S26", "s26"),
        ("S271", "s271"),
        ("Módulo", "modulo_acento"),
        ("Productor", "productor"),
        ("Acidez", "acidez"),
        ("Defecto", "defecto"),
        ("Packet", "packet"),
        ("Clasificación", "clasificacion"),
        ("Año", "anio"),
        ("Calibres", "calibres"),
        ("Mes", "mes"),
    ),
)

H05_CLIMA = Tabla(
    origen="H05_Clima",
    destino="h05_clima",
    filas_esperadas=155_588,
    nota="153.413 timestamps distintos: 2.079 grupos duplicados por recarga (H-08).",
    columnas=(
        ("Fecha", "fecha"),
        ("Barometro", "barometro"),
        ("Temp", "temp"),
        ("TembAlta", "temp_alta"),  # typo del origen, se corrige al nombrar el destino
        ("TempBaja", "temp_baja"),
        ("Humedad", "humedad"),
        ("PuntoRocio", "punto_rocio"),
        ("BulboHumedo", "bulbo_humedo"),
        ("VelViento", "vel_viento"),
        ("DirecViento", "direc_viento"),
        ("VientoCorriente", "viento_corriente"),
        ("AltaVelViento", "alta_vel_viento"),
        ("AltaDirecViento", "alta_direc_viento"),
        ("VientoFrio", "viento_frio"),
        ("IndiceCalor", "indice_calor"),
        ("THWIndex", "thw_index"),
        ("TSHWIndex", "tshw_index"),
        ("Lluvia", "lluvia"),
        ("TasaLluvia", "tasa_lluvia"),
        ("RadSol", "rad_sol"),
        ("EnerSolar", "ener_solar"),
        ("RadSolAlta", "rad_sol_alta"),
        ("ET-mm", "et_mm"),
        ("DGCalentamiento", "dg_calentamiento"),
        ("DGEnfriamiento", "dg_enfriamiento"),
    ),
)

# ── Maestros ────────────────────────────────────────────────────────────────────

M_LOTES = Tabla(
    origen="M_Lotes",
    destino="m_lotes",
    filas_esperadas=860,
    nota="Se migra por trazabilidad histórica; el maestro vigente es M_Lotes.xlsx (ADR-0003).",
    columnas=(
        ("Fundo", "fundo"),
        ("FundoPPto", "fundo_ppto"),
        ("Variedad", "variedad"),
        ("Modulo", "modulo"),
        ("Turno", "turno"),
        ("Lote", "lote"),
        ("Area", "area"),
        ("NPlantas", "n_plantas"),
        ("FSiembra", "fecha_siembra"),
        ("Maceta", "maceta"),
        ("TipoFibra", "tipo_fibra"),
        ("KeyMap", "key_map"),
        ("Fundo_pptom5", "fundo_pptom5"),
        ("Moduloo", "moduloo"),
        ("kk", "kk"),
    ),
)

M_TIME = Tabla(
    origen="M_Time",
    destino="m_time",
    filas_esperadas=2_189,
    columnas=(
        ("Fecha", "fecha"),
        ("Sem", "sem"),
        ("Mes", "mes"),
        ("Año", "anio"),
        ("SEvConteo", "sev_conteo"),
        ("AQII", "aqii"),
        ("MesSem", "mes_sem"),
    ),
)

M_PODA = Tabla(
    origen="M_Poda",
    destino="m_poda",
    filas_esperadas=2_159,
    columnas=(
        ("Campaña", "campania"),
        ("Fundo", "fundo"),
        ("Variedad", "variedad"),
        ("Modulo", "modulo"),
        ("Turno", "turno"),
        ("Lote", "lote"),
        ("Area", "area"),
        ("FSiembra", "fecha_siembra"),
        ("FInicio", "fecha_inicio"),
    ),
)

M_EVALUADORES = Tabla(
    origen="M_Evaluadores",
    destino="m_evaluadores",
    filas_esperadas=31,
    columnas=(
        ("DNI", "dni"),
        ("Nombres", "nombres"),
        ("Apellidos", "apellidos"),
        ("Cod", "cod"),
        ("InicioLabores", "inicio_labores"),
        ("Nacimiento", "nacimiento"),
        ("Zona", "zona"),
        ("Celular", "celular"),
        ("Estado", "estado"),
    ),
)

M_N_MUESTRA = Tabla(
    origen="M_nMuestra",
    destino="m_n_muestra",
    filas_esperadas=681,
    columnas=(
        ("Evaluacion", "evaluacion"),
        ("Fundo", "fundo"),
        ("Modulo", "modulo"),
        ("Turno", "turno"),
        ("Lote", "lote"),
        ("Cortina", "cortina"),
        ("Hilera", "hilera"),
        ("Planta", "planta"),
        ("Muestras", "muestras"),
    ),
)

M_EQUIVALENCIA_ELIFAB = Tabla(
    origen="M_EquivalenciaElifab",
    destino="m_equivalencia_elifab",
    filas_esperadas=15,
    columnas=(
        ("Productor", "productor"),
        ("Empresa", "empresa"),
    ),
)

# ── Forecast ────────────────────────────────────────────────────────────────────

R08_FORECAST_CAMPANIA = Tabla(
    origen="R08_Forecast_Campaña",
    destino="r08_forecast_campania",
    filas_esperadas=101_715,
    nota="[Fundo] trae la empresa y [FundoPPto] el fundo físico: semántica invertida (N-5).",
    columnas=(
        ("Version", "version"),
        ("Fundo", "fundo"),
        ("FundoPPto", "fundo_ppto"),
        ("Modulo", "modulo"),
        ("Turno", "turno"),
        ("Año", "anio"),
        ("Semana", "semana"),
        ("KG Exp", "kg_exp"),
        ("Kg Des", "kg_des"),
        ("Kg Con", "kg_con"),
        ("FrtTotal_Exp", "frt_total_exp"),
        ("Campaña", "campania"),
        ("C12", "c12"),
        ("C14", "c14"),
        ("C16", "c16"),
        ("C18", "c18"),
        ("C19", "c19"),
        ("C20", "c20"),
        ("C22", "c22"),
        ("C24", "c24"),
        ("C26", "c26"),
    ),
)

R09_FORECAST_SEMANAL = Tabla(
    origen="R09_Forecast_Semanal",
    destino="r09_forecast_semanal",
    filas_esperadas=48_368,
    columnas=(
        ("Campaña", "campania"),
        ("Pasada", "pasada"),
        ("Mod", "modulo"),
        ("Turno", "turno"),
        ("Lote", "lote"),
        ("Area", "area"),
        ("FCosAnt", "fecha_cos_ant"),
        ("FCos", "fecha_cos"),
        ("Sem", "sem"),
        ("FrtCos", "frt_cos"),
        ("Peso", "peso"),
        ("FrutosTotal", "frutos_total"),
        ("Rend", "rend"),
        ("Kg", "kg"),
        ("Dr", "dr"),
        ("Version", "version"),
        ("FundPPTo", "fund_ppto"),
        ("Fundo", "fundo"),
    ),
)


TOTAL_FILAS_ORIGEN = 654_598
"""Suma verificada de las 18 tablas del origen.

Los cuatro documentos de auditoría publican 683.180. Los recuentos tabla por tabla que dan
son correctos, pero la suma no: el total real es 654.598, con 28.582 filas de diferencia
(4,4%). Verificado contra la base el 2026-08-03 (hallazgo N-10).
"""

CATALOGO_ACCESS: tuple[Tabla, ...] = (
    E01_RAMAS,
    E02_CONTEO_FLORES,
    E03_CONTEO_ESTADOS,
    E04_BROTES,
    E05_DIAMETROS_BAYAS,
    H00_VOLUMEN_CAMPO,
    H01_PROD_HISTORICA,
    H02_BD_ELIFAB,
    H05_CLIMA,
    M_EQUIVALENCIA_ELIFAB,
    M_EVALUADORES,
    M_LOTES,
    M_N_MUESTRA,
    M_PODA,
    M_TIME,
    R08_FORECAST_CAMPANIA,
    R09_FORECAST_SEMANAL,
)
"""Las 17 tablas que se migran. Suman TOTAL_FILAS_ORIGEN (654.598) filas."""

DESCARTADAS: dict[str, str] = {
    "Errores de pegado": (
        "0 filas. La genera Access automáticamente cuando falla un pegado masivo; 16 columnas "
        "genéricas F1..F16. Basura del motor, no dato de negocio (H-12)."
    ),
    "E": (
        "Consulta rota y de un solo carácter: un borrador para analizar productividad de "
        "evaluadores que quedó guardado. Pide [Actividad], que solo existe en E01_Ramas "
        "(H-04 caso 4). Se descarta la consulta, no la intención: el enlace por DNI la "
        "responde."
    ),
    "~TMPCLP151491": "Consulta temporal del portapapeles de Access. El prefijo ~ la delata.",
}
"""Objetos del origen que NO se migran, con el motivo. Se registran en el informe de
extracción para que la decisión quede a la vista y no parezca un olvido."""


# ── Maestro vigente (Excel, fuera de Access) ────────────────────────────────────

MAESTRO_LOTES_COLUMNAS: tuple[tuple[str, str], ...] = (
    ("Fundo", "fundo"),
    ("FundoPPto", "fundo_ppto"),
    ("Variedad", "variedad"),
    ("Modulo", "modulo"),
    ("Turno", "turno"),
    ("Lote", "lote"),
    ("Area", "area"),
    ("NPlantas", "n_plantas"),
    ("FSiembra", "fecha_siembra"),
    ("Maceta", "maceta"),
    ("TipoFibra", "tipo_fibra"),
    ("KeyMap", "key_map"),
    ("Fundo_pptom5", "fundo_pptom5"),
)
MAESTRO_LOTES_DESTINO = "m_lotes_maestro"
MAESTRO_LOTES_FILAS_ESPERADAS = 879


def total_filas_esperadas() -> int:
    return sum(t.filas_esperadas or 0 for t in CATALOGO_ACCESS)


def por_destino(nombre: str) -> Tabla:
    for tabla in CATALOGO_ACCESS:
        if tabla.destino == nombre:
            return tabla
    raise KeyError(f"No hay ninguna tabla con destino {nombre!r} en el catálogo")

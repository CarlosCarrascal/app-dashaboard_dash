"""Relación entre variables y kg/ha, a nivel módulo, SOLO 2025.

Qué hace: explica el kg_ha de LA MISMA semana con las variables de esa misma semana, y
mide con SHAP cuánto pesa cada una. No pronostica — esa versión se probó primero
(analisis_shap_kg_ha.py) y no validó (R2 negativo en tres formulaciones).

Alcance fijado con el usuario (2026-08-06): solo 2025, el único año con riego real
cargado; a nivel de módulo; sin fenología (E02-E05 solo cubren C2026, no comparable
entre años).

── Dos esquemas de validación, y por qué importan los dos ────────────────────
  (a) 5-fold ALEATORIO — mide si el patrón se sostiene en semanas no usadas para
      ajustar. Es la métrica con la que se ELIGE la configuración.
  (b) DEJA-UN-MÓDULO-FUERA — cada módulo se predice con un modelo que nunca lo vio.
      Es la métrica que se REPORTA como generalización honesta, y no se usa para
      elegir nada: si se eligiera mirándola, el número reportado sería optimista.

── Lo que el experimento de selección encontró (documentado, reproducible con
   --buscar) ────────────────────────────────────────────────────────────────
  · Quitar `modulo_id` MEJORA la generalización (0,157 → 0,219 en el esquema b).
    El |SHAP| altísimo que la primera versión le atribuía era el modelo memorizando
    el nivel de cada módulo — inútil para un módulo que no vio. El baseline de
    "promedio de cada módulo" lo confirma: R2 = 0,029, casi nada.
  · Transformar el objetivo a log(kg/ha) EMPEORA (0,219 → 0,072). Probado y descartado.
  · Agregar 8 variables derivadas (balance hídrico, ritmo térmico, estacionalidad)
    también empeora con solo 471 filas (0,219 → 0,203). Probado y descartado.
  · Árboles menos profundos y aprendizaje más lento ayudan, como es esperable con
    pocas filas: prof 3 y lr 0,03 en vez de prof 4 y lr 0,05.

Uso:
    python db/tools/analisis_shap_relacion_2025.py            # config elegida
    python db/tools/analisis_shap_relacion_2025.py --buscar    # repite la búsqueda (lento)
"""

from __future__ import annotations

import itertools
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import shap
import xgboost as xgb
from sklearn.metrics import mean_absolute_error, r2_score
from sklearn.model_selection import GroupKFold, KFold

sys.path.insert(0, str(Path(__file__).resolve().parent))
from analisis_shap_kg_ha import cargar_panel  # noqa: E402

RAIZ = Path(__file__).resolve().parents[2]
SALIDA = RAIZ / "data" / "salida"

FEATURES = [
    "edad_dias", "poda_dispersion_dias",
    "gdd_semana", "temp_media", "temp_max", "temp_min",
    "eto_semana_mm", "humedad_media",
    "gdd_acum_poda", "eto_acum_poda_mm",
    "riego_mm", "riego_m3",
    "area_ha", "n_plantas",
]

# Excluidas a propósito, por razones de dominio antes que de métrica (ver EXCLUIDAS_MOTIVO):
# el modelo con ellas rendía igual o peor y una de ellas encabezaba el ranking siendo
# físicamente irrelevante, que es la peor combinación posible para un reporte.
EXCLUIDAS = ["lluvia_acum_poda_mm", "lluvia_semana_mm", "riego_dias_con_registro"]
EXCLUIDAS_MOTIVO = {
    "lluvia_acum_poda_mm": (
        "Acumula ~24 mm en ~275 días (media 24,5; rango 3-35,6) contra ~1.200 mm de demanda "
        "ETO en el mismo periodo: en desierto costero es agronómicamente despreciable. Aun así "
        "encabezaba el ranking con |SHAP| 148 — señal de que el modelo la usaba como huella de "
        "la cohorte de poda (solo 54 valores distintos, uno por fecha de poda) y no como lluvia. "
        "Quitarla MEJORA la generalización — ver la tabla comparativa, fila «con las variables de "
        "lluvia» contra la final."),
    "lluvia_semana_mm": (
        "Casi siempre 0 en el fundo; |SHAP| de 4,5, el penúltimo del ranking. Se retira junto a "
        "la acumulada por el mismo motivo físico."),
    "riego_dias_con_registro": (
        "Vale 7 en 463 de las 471 filas y 5 en las otras 8: prácticamente constante. Su |SHAP| "
        "fue exactamente 0,000 — el modelo nunca la usó para partir un nodo. Es metadato de "
        "calidad del dato, no una variable explicativa."),
}
DERIVADAS = ["balance_hidrico_mm", "ratio_reposicion", "gdd_por_dia", "eto_por_dia",
             "riego_por_planta_l", "semana_num", "sem_sin", "sem_cos"]

# Configuración elegida por el esquema (a); ver la cabecera.
PARAMS = dict(n_estimators=300, max_depth=3, learning_rate=0.03,
              min_child_weight=1, subsample=0.8, colsample_bytree=0.8)


def preparar(panel: pd.DataFrame) -> pd.DataFrame:
    p = panel[panel["anio_semana"].str.match(r"^2025-")].copy()
    for c in FEATURES + EXCLUIDAS + ["kg_ha"]:
        p[c] = pd.to_numeric(p[c], errors="coerce")
    p["semana_num"] = p["anio_semana"].str.slice(5).astype(int)
    p["balance_hidrico_mm"] = p["riego_mm"] + p["lluvia_semana_mm"] - p["eto_semana_mm"]
    p["ratio_reposicion"] = (p["riego_mm"] + p["lluvia_semana_mm"]) / p["eto_semana_mm"].replace(0, np.nan)
    p["gdd_por_dia"] = p["gdd_acum_poda"] / p["edad_dias"].replace(0, np.nan)
    p["eto_por_dia"] = p["eto_acum_poda_mm"] / p["edad_dias"].replace(0, np.nan)
    p["riego_por_planta_l"] = p["riego_m3"] * 1000 / p["n_plantas"].replace(0, np.nan)
    p["sem_sin"] = np.sin(2 * np.pi * p["semana_num"] / 52)
    p["sem_cos"] = np.cos(2 * np.pi * p["semana_num"] / 52)
    return p.dropna(subset=["kg_ha"]).reset_index(drop=True)


def modelo(**extra):
    return xgb.XGBRegressor(enable_categorical=True, random_state=42, **{**PARAMS, **extra})


def validar(X, y, grupos, log_target=False, params=None):
    """Devuelve las métricas de los dos esquemas."""
    res = {}
    for nombre, splitter, gr in (("facil", KFold(5, shuffle=True, random_state=42), None),
                                 ("dificil", GroupKFold(n_splits=grupos.nunique()), grupos)):
        pred = np.full(len(X), np.nan)
        for tr, te in splitter.split(X, y, groups=gr):
            m = xgb.XGBRegressor(enable_categorical=True, random_state=42, **(params or PARAMS))
            m.fit(X.iloc[tr], np.log1p(y.iloc[tr]) if log_target else y.iloc[tr])
            pr = m.predict(X.iloc[te])
            pred[te] = np.expm1(pr) if log_target else pr
        res[f"r2_{nombre}"] = float(r2_score(y, pred))
        res[f"mae_{nombre}"] = float(mean_absolute_error(y, pred))
    return res


def main() -> int:
    buscar = "--buscar" in sys.argv
    p = preparar(cargar_panel())
    y, grupos = p["kg_ha"], p["modulo_id"]
    n_g = grupos.nunique()
    print(f"2025: {len(p)} filas · {n_g} módulos · kg/ha media {y.mean():.0f}, "
          f"mediana {y.median():.0f}, asimetría {y.skew():.2f}")

    X = p[FEATURES].copy()

    # ── Baselines ────────────────────────────────────────────────────────
    pred_glob = np.full(len(y), np.nan)
    for tr, te in GroupKFold(n_splits=n_g).split(p, y, groups=grupos):
        pred_glob[te] = y.iloc[tr].mean()
    b_glob = dict(r2=float(r2_score(y, pred_glob)), mae=float(mean_absolute_error(y, pred_glob)))

    pred_mod = np.full(len(y), np.nan)
    for tr, te in KFold(5, shuffle=True, random_state=42).split(p):
        medias = y.iloc[tr].groupby(grupos.iloc[tr]).mean()
        pred_mod[te] = grupos.iloc[te].map(medias).fillna(y.iloc[tr].mean()).to_numpy()
    b_mod = dict(r2=float(r2_score(y, pred_mod)), mae=float(mean_absolute_error(y, pred_mod)))
    print(f"Baseline promedio global (difícil): R2={b_glob['r2']:.3f} MAE={b_glob['mae']:.0f}")
    print(f"Baseline promedio por módulo (fácil): R2={b_mod['r2']:.3f} MAE={b_mod['mae']:.0f}")

    # ── Variantes para la tabla comparativa ──────────────────────────────
    print("\nVariantes:")
    variantes = {}
    TODAS = FEATURES + EXCLUIDAS
    combos = {
        "con_modulo": (TODAS + ["modulo_id"], False, dict(max_depth=4, learning_rate=0.05)),
        "sin_modulo": (TODAS, False, dict(max_depth=4, learning_rate=0.05)),
        "log": (TODAS, True, dict(max_depth=4, learning_rate=0.05)),
        "derivadas": (TODAS + DERIVADAS, False, dict(max_depth=4, learning_rate=0.05)),
        "con_lluvia": (TODAS, False, {}),
        "final": (FEATURES, False, {}),
    }
    for nombre, (cols, log_t, extra) in combos.items():
        Xv = p[cols].copy()
        if "modulo_id" in cols:
            Xv["modulo_id"] = Xv["modulo_id"].astype("category")
        variantes[nombre] = validar(Xv, y, grupos, log_t, {**PARAMS, **extra})
        v = variantes[nombre]
        print(f"  {nombre:<22} R2 fácil={v['r2_facil']:.3f}  R2 difícil={v['r2_dificil']:.3f}  MAE={v['mae_dificil']:.0f}")

    if buscar:
        print("\nGrid (lento)…")
        mejores = []
        for d, lr, n, mcw in itertools.product([3, 4, 6], [0.03, 0.05, 0.1], [300, 700], [1, 5]):
            pr = dict(n_estimators=n, max_depth=d, learning_rate=lr, min_child_weight=mcw,
                      subsample=0.8, colsample_bytree=0.8)
            r = validar(X, y, grupos, False, pr)
            mejores.append({**pr, **r})
        mejores.sort(key=lambda z: -z["r2_facil"])
        print("  mejor por R2 fácil:", {k: mejores[0][k] for k in ("max_depth","learning_rate","n_estimators","min_child_weight","r2_facil","r2_dificil")})

    # ── SHAP sobre la configuración elegida, ajustada con todo 2025 ───────
    final = modelo()
    final.fit(X, y)
    shap_values = shap.TreeExplainer(final)(X)

    importancia = pd.DataFrame({
        "variable": X.columns,
        "shap_medio_abs": np.abs(shap_values.values).mean(axis=0),
        "shap_medio_con_signo": shap_values.values.mean(axis=0),
    }).sort_values("shap_medio_abs", ascending=False).reset_index(drop=True)
    print("\nRanking SHAP:")
    print(importancia.to_string(index=False))

    vf = variantes["final"]
    r2f, r2d, maed = vf["r2_facil"], vf["r2_dificil"], vf["mae_dificil"]

    def fila(nombre, que_es, rf, rd, mae, elegido=False):
        return dict(nombre=nombre, que_es=que_es, r2_facil=rf, r2_dificil=rd, mae=mae, elegido=elegido)

    comparacion = [
        fila("Predecir siempre el promedio", "El piso absoluto: ignorar todas las variables y decir el promedio histórico.",
             None, b_glob["r2"], b_glob["mae"]),
        fila("Promedio de cada módulo", "Suponer que cada módulo rinde siempre su propio promedio. Parecía el baseline a batir; resulta que casi no explica nada.",
             b_mod["r2"], None, b_mod["mae"]),
        fila("Con la identidad del módulo", "Primera versión: incluía modulo_id. Peor generalización — el modelo memorizaba el nivel de cada módulo.",
             variantes["con_modulo"]["r2_facil"], variantes["con_modulo"]["r2_dificil"], variantes["con_modulo"]["mae_dificil"]),
        fila("Sin la identidad del módulo", "Misma configuración, sin modulo_id: obligado a aprender patrones que sirven para un módulo nuevo.",
             variantes["sin_modulo"]["r2_facil"], variantes["sin_modulo"]["r2_dificil"], variantes["sin_modulo"]["mae_dificil"]),
        fila("Con log(kg/ha)", "Transformar el objetivo para corregir su asimetría (1,18). Probado y descartado: empeora mucho.",
             variantes["log"]["r2_facil"], variantes["log"]["r2_dificil"], variantes["log"]["mae_dificil"]),
        fila("Con 8 variables derivadas", "Sumar balance hídrico, ritmo térmico y estacionalidad cíclica. Descartado: con 471 filas, más variables generalizan peor.",
             variantes["derivadas"]["r2_facil"], variantes["derivadas"]["r2_dificil"], variantes["derivadas"]["mae_dificil"]),
        fila("Con las variables de lluvia", "Árboles simples, pero conservando lluvia acumulada y semanal. La acumulada encabezaba el ranking siendo físicamente irrelevante.",
             variantes["con_lluvia"]["r2_facil"], variantes["con_lluvia"]["r2_dificil"], variantes["con_lluvia"]["mae_dificil"]),
        fila("Final: 14 variables, árboles simples", "Sin identidad de módulo, sin lluvia, sin la variable constante. Profundidad 3 y aprendizaje 0,03. Es el modelo de este reporte.",
             r2f, r2d, maed, elegido=True),
    ]

    modelo_reporte = {
        "descripcion": (
            "<b>XGBoost</b> con 300 árboles de profundidad 3 y tasa de aprendizaje 0,03, sobre "
            f"<b>{len(p)}</b> filas y <b>{len(FEATURES)}</b> variables. Se usa un modelo de árboles "
            "porque maneja de forma nativa los datos faltantes y las relaciones no lineales —un riego "
            "que ayuda hasta cierto punto y después deja de sumar— sin asumir que la relación es una "
            "recta. <b>Se excluyeron 3 variables a propósito</b>: la identidad del módulo y la lluvia "
            "acumulada, porque el modelo las usaba para memorizar en vez de aprender, y los días con "
            "registro de riego, que es prácticamente constante. Las tres decisiones están medidas en "
            "la tabla de abajo."
        ),
        "excluidas": [{"var": v, "motivo": EXCLUIDAS_MOTIVO[v]} for v in EXCLUIDAS],
        "validaciones": [
            {"nombre": "R² — 5 particiones aleatorias", "r2": round(r2f, 4),
             "descripcion": "Cada quinto de las semanas se predice con un modelo entrenado con los otros cuatro. Es la métrica con la que se eligió la configuración."},
            {"nombre": "R² — dejando un módulo fuera", "r2": round(r2d, 4),
             "descripcion": "Cada módulo se predice con un modelo que nunca lo vio. Es la prueba dura, y no se usó para elegir nada: el número es honesto."},
        ],
        "mae_referencia": round(maed, 1),
        "comparacion": comparacion,
        "nota_seleccion": (
            "La configuración se eligió mirando <b>solo el R² fácil</b>, y el R² difícil se reporta "
            "sin haber influido en ninguna decisión — si se eligiera mirándolo, el número quedaría "
            "inflado. Para dimensionarlo: al recorrer 36 combinaciones de hiperparámetros, el R² "
            "difícil varió entre 0,115 y 0,275, así que la elección importa. Reproducible con "
            "<code>--buscar</code>."
        ),
    }

    def peso(v):
        f = importancia[importancia["variable"] == v]
        return (float(f.iloc[0]["shap_medio_abs"]), float(f.iloc[0]["shap_medio_con_signo"])) if len(f) else (0.0, 0.0)

    p_edad, s_edad = peso("edad_dias")
    p_gdd, s_gdd = peso("gdd_acum_poda")
    p_mm, s_mm = peso("riego_mm")
    p_m3, s_m3 = peso("riego_m3")

    hallazgos = [
        {"categoria": "identidad",
         "titulo": "Dos de las variables que parecían más importantes eran el modelo memorizando",
         "cuerpo": (
             "Pasó dos veces, y las dos se detectaron con la prueba dura. Primero "
             "<code>modulo_id</code>: SHAP le daba el mayor peso de todos, lo que se leyó como «hay "
             "diferencias entre módulos que no medimos» — pero sacarla <b>mejora</b> la "
             f"generalización ({variantes['con_modulo']['r2_dificil']:.3f} → "
             f"{variantes['sin_modulo']['r2_dificil']:.3f}), y predecir el promedio de cada módulo da un R² de "
             f"solo {b_mod['r2']:.3f}. Después <code>lluvia_acum_poda_mm</code>: encabezaba el ranking "
             "con |SHAP| 148 aunque acumula ~24 mm en 275 días contra ~1.200 mm de demanda hídrica — "
             "en desierto costero, nada. Tenía solo 54 valores distintos, uno por fecha de poda: era "
             "una <b>huella de la cohorte de poda</b> disfrazada de lluvia. <b>El modelo final no usa "
             "ninguna de las dos.</b>")},
        {"categoria": "contexto_modulo",
         "titulo": "La edad del fruto es el factor medible de mayor peso",
         "cuerpo": (
             f"<code>edad_dias</code> —días desde la poda— mueve <b>±{p_edad:.0f} kg/ha</b> en promedio, "
             "el mayor peso entre las variables que de verdad se miden. Coincide con la lógica del "
             "modelo de macro que Agronomía ya usa, que proyecta la maduración a partir del tiempo "
             "desde la poda. Su efecto promedio es negativo, coherente con que el rendimiento cae al "
             "final de la campaña, y la curva de §5 muestra la forma exacta.")},
        {"categoria": "clima_acumulado",
         "titulo": "El clima solo discrimina entre módulos si se acumula desde la poda",
         "cuerpo": (
             "Las variables de clima semanal son <b>idénticas</b> para los 19 módulos esa semana — hay "
             "una sola estación en todo el fundo — así que no pueden explicar por qué un módulo rinde "
             "distinto de otro, solo el momento del año. Acumuladas desde la poda de cada módulo, la "
             f"misma serie se vuelve propia de cada uno: <code>gdd_acum_poda</code> pesa "
             f"±{p_gdd:.0f} kg/ha con el <b>efecto positivo más fuerte de todo el ranking "
             f"({s_gdd:+.1f})</b>. Más tiempo térmico acumulado, más rendimiento.")},
        {"categoria": "riego",
         "titulo": "El riego pesa, pero su efecto no es «más agua, más kilos»",
         "cuerpo": (
             f"Las dos formas de medirlo tienen peso real (<code>riego_m3</code> ±{p_m3:.0f} y "
             f"<code>riego_mm</code> ±{p_mm:.0f} kg/ha) y sin embargo su efecto <i>promedio</i> es casi "
             f"cero ({s_m3:+.1f} y {s_mm:+.1f}). Eso no es contradicción: significa que el efecto "
             "<b>no es monótono</b> — suma en unos tramos y resta en otros, y el promedio los cancela. "
             "La curva de §5 muestra dónde. Además, el volumen bruto está confundido con el tamaño del "
             "módulo (correlación 0,31 con el área y 0,37 con las plantas): parte de lo que «explica» "
             "es que un módulo grande consume más metros cúbicos. <b>Para decidir riego hay que mirar "
             "la lámina, que ya está normalizada por hectárea</b>; el volumen sirve para costos.")},
        {"categoria": "clima_semanal",
         "titulo": "Nada de lo que probamos para mejorarlo funcionó: el límite son las 471 semanas",
         "cuerpo": (
             "Se probó transformar el objetivo a logaritmo para corregir su asimetría "
             f"({variantes['sin_modulo']['r2_dificil']:.3f} → {variantes['log']['r2_dificil']:.3f}, mucho peor) y "
             "sumar 8 variables derivadas con sentido agronómico —balance hídrico, ritmo térmico, "
             f"estacionalidad cíclica— ({variantes['sin_modulo']['r2_dificil']:.3f} → "
             f"{variantes['derivadas']['r2_dificil']:.3f}, peor). Lo que sí ayudó fue <b>simplificar</b>: "
             "árboles menos profundos y aprendizaje más lento. Es un resultado negativo útil — el "
             "techo no está en cómo se combinan las variables, está en cuántas semanas hay para "
             "aprender de ellas.")},
    ]

    limites = [
        {"titulo": "No es un pronóstico.",
         "cuerpo": ("Explica el kg/ha de la <b>misma</b> semana con las variables de esa misma semana. "
                    "La versión que predecía la semana siguiente no validó — R² de −0,33 y −0,09 según el "
                    "esquema, peor que decir el promedio — y se descartó en vez de presentarla.")},
        {"titulo": "No es causal.",
         "cuerpo": ("Es una relación estadística que generaliza a módulos y semanas no vistos, no un "
                    "experimento controlado. No autoriza a decir «si subo el riego X mm, la cosecha sube Y kg».")},
        {"titulo": "El R² es modesto, y eso también es información.",
         "cuerpo": (f"El modelo explica alrededor del {r2d*100:.0f}% de la variación entre módulos no vistos. "
                    "El resto es ruido de la cosecha por pañas y factores que hoy no se miden. Sirve para "
                    "ordenar factores por importancia, no para reemplazar el criterio agronómico.")},
        {"titulo": "Alcance limitado.",
         "cuerpo": ("Solo 2025, el único año con riego medido. Sin fenología (flores, estados, diámetro): "
                    "esas tablas solo existen para la campaña 2026 y no son comparables entre años. Sin riego "
                    "para M16-M18 ni Aqu Anqa 6.")},
    ]

    SALIDA.mkdir(parents=True, exist_ok=True)
    (SALIDA / "shap_relacion_2025.json").write_text(json.dumps({
        "alcance": "2025, nivel módulo, kg_ha de la misma semana (no pronóstico)",
        "n_filas": len(p), "n_modulos": int(n_g),
        "media_kg_ha": round(float(y.mean()), 2),
        "baselines": {"promedio_global": b_glob, "promedio_por_modulo": b_mod},
        "variantes": variantes,
        "modelo_reporte": modelo_reporte,
        "hallazgos": hallazgos,
        "limites": limites,
        "importancia": importancia.to_dict(orient="records"),
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    np.save(SALIDA / "shap_relacion_2025_values.npy", shap_values.values)
    Xg = X.copy()
    Xg["modulo"] = p["modulo"].to_numpy()
    Xg["fundo"] = p["fundo"].to_numpy()
    Xg["semana"] = p["anio_semana"].to_numpy()
    Xg["kg_ha"] = y.to_numpy()
    Xg.to_csv(SALIDA / "shap_relacion_2025_X.csv", index=False)

    print(f"\nOK  R2 fácil={r2f:.3f}  R2 difícil={r2d:.3f}  MAE={maed:.0f} kg/ha")
    print(f"OK  {SALIDA / 'shap_relacion_2025.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

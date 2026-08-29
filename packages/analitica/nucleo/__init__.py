"""Fachada ligera del núcleo analítico.

Los módulos concretos siguen siendo independientes de cualquier interfaz. Esta fachada
conserva los nombres históricos, pero solo carga pandas, scikit-learn o XGBoost cuando el
consumidor solicita una función que realmente los necesita.
"""

from importlib import import_module

_LAZY_ATTRS = {
    "clima": (".clima", None),
    "Hallazgo": (".contratos", "Hallazgo"),
    "Panel": (".contratos", "Panel"),
    "cargar_panel": (".datos", "cargar_panel"),
    "diagnostico_ventanas": (".datos", "diagnostico_ventanas"),
    "CONJUNTOS": (".evaluacion", "CONJUNTOS"),
    "PARTICIONES": (".evaluacion", "PARTICIONES"),
    "PLAN_VALIDACION": (".evaluacion", "PLAN_VALIDACION"),
    "REFERENCIAS": (".evaluacion", "REFERENCIAS"),
    "Conjunto": (".evaluacion", "Conjunto"),
    "Medicion": (".evaluacion", "Medicion"),
    "Particion": (".evaluacion", "Particion"),
    "Paso": (".evaluacion", "Paso"),
    "Referencia": (".evaluacion", "Referencia"),
    "aporte_por_grupo": (".evaluacion", "aporte_por_grupo"),
    "aporte_por_variable": (".evaluacion", "aporte_por_variable"),
    "comparar_familias": (".evaluacion", "comparar_familias"),
    "correlaciones_con_objetivo": (".evaluacion", "correlaciones_con_objetivo"),
    "descomposicion_varianza": (".evaluacion", "descomposicion_varianza"),
    "medir": (".evaluacion", "medir"),
    "tabla_validacion": (".evaluacion", "tabla_validacion"),
    "construir_informe": (".informe", "construir"),
    "Ajuste": (".modelo", "Ajuste"),
    "Consistencia": (".modelo", "Consistencia"),
    "entrenar": (".modelo", "entrenar"),
    "verificar_consistencia": (".modelo", "verificar_consistencia"),
}

__all__ = list(_LAZY_ATTRS)


def __getattr__(nombre: str):
    try:
        modulo, atributo = _LAZY_ATTRS[nombre]
    except KeyError as exc:
        raise AttributeError(f"module {__name__!r} has no attribute {nombre!r}") from exc
    modulo_cargado = import_module(modulo, __name__)
    valor = modulo_cargado if atributo is None else getattr(modulo_cargado, atributo)
    globals()[nombre] = valor
    return valor


def __dir__():
    return sorted(set(globals()) | set(__all__))

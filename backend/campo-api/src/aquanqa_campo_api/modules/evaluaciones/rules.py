"""Validación y normalización de los seis módulos de evaluación de campo."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import time
from decimal import Decimal, InvalidOperation
from typing import Any

from .schemas import EvaluationCreate

_ESTADOS_BAYA = {"E1", "E2", "E3", "E4", "E5", "DESH", "X"}


class EvaluationValidationError(ValueError):
    """Dato de evaluación que no puede convertirse al modelo core."""


@dataclass(frozen=True)
class NormalizedEvaluation:
    """Representación tipada que el adaptador PostgreSQL puede persistir."""

    source: EvaluationCreate
    data: dict[str, Any]

    @property
    def module_key(self) -> str:
        return self.source.module_key


def _decimal(value: Any, field: str) -> Decimal | None:
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    if isinstance(value, bool):
        raise EvaluationValidationError(f"{field} debe ser numérico")
    try:
        number = Decimal(str(value).strip())
    except (InvalidOperation, ValueError):
        raise EvaluationValidationError(f"{field} debe ser numérico") from None
    if not number.is_finite():
        raise EvaluationValidationError(f"{field} debe ser finito")
    return number


def _count(values: dict[str, Any], key: str, *, default: int | None = 0) -> int | None:
    number = _decimal(values.get(key), key)
    if number is None:
        return default
    if number != number.to_integral_value():
        raise EvaluationValidationError(f"{key} debe ser un entero")
    if number < 0:
        raise EvaluationValidationError(f"{key} no puede ser negativo")
    if number > 32767:
        raise EvaluationValidationError(f"{key} supera el máximo permitido")
    return int(number)


def _measure(value: Any, field: str) -> Decimal | None:
    number = _decimal(value, field)
    if number is None or number == 0:
        return None
    if number <= 0:
        raise EvaluationValidationError(f"{field} debe ser mayor que cero")
    return number


def _text(value: Any) -> str | None:
    if value is None:
        return None
    result = str(value).strip()
    return result or None


def _hora(source: EvaluationCreate, values: dict[str, Any]) -> time | None:
    if source.hora is not None:
        return source.hora
    value = _text(values.get("hora"))
    if not value:
        return None
    try:
        return time.fromisoformat(value)
    except ValueError:
        raise EvaluationValidationError("hora debe tener formato HH:MM[:SS]") from None


def _item(
    source: EvaluationCreate,
    values: dict[str, Any],
    default: str | None = None,
) -> str | None:
    return _text(source.item) or _text(values.get("item")) or default


def _observaciones_baya(values: dict[str, Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for number in range(1, 51):
        suffix = f"{number:02d}"
        diameter = _measure(values.get(f"m4_diam{suffix}"), f"m4_diam{suffix}")
        state = _text(values.get(f"m4_est{suffix}"))
        if state:
            state = state.upper()
            if state not in _ESTADOS_BAYA:
                raise EvaluationValidationError(f"m4_est{suffix} no es un estado válido: {state}")
        if diameter is None and state is None:
            continue
        result.append(
            {"numero_muestra": number, "estado_codigo": state, "diametro_mm": diameter}
        )
    if not result:
        raise EvaluationValidationError("baya requiere al menos una observación")
    return result


def _observaciones_peso(values: dict[str, Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for number in range(1, 26):
        suffix = f"{number:02d}"
        weight = _measure(values.get(f"m5_peso{suffix}"), f"m5_peso{suffix}")
        diameter = _measure(values.get(f"m5_diam{suffix}"), f"m5_diam{suffix}")
        if weight is None and diameter is None:
            continue
        result.append(
            {"numero_muestra": number, "peso_g": weight, "diametro_mm": diameter}
        )
    if not result:
        raise EvaluationValidationError("pesos requiere al menos una muestra")
    return result


def normalize_evaluation(source: EvaluationCreate) -> NormalizedEvaluation:
    """Valida los valores de Flutter y los transforma al grano de core."""

    values = source.valores
    if source.module_key == "estadios":
        counts = {f"e{i}": _count(values, f"m1_e{i}") for i in range(1, 6)}
        return NormalizedEvaluation(
            source,
            {
                **counts,
                "total_origen": _count(values, "m1_total", default=None),
                "item": _item(source, values, "mobile"),
                "hora": _hora(source, values),
            },
        )
    if source.module_key == "flores":
        return NormalizedEvaluation(
            source,
            {
                "n_flores": _count(values, "m2_flores"),
                "cuajo": _count(values, "m2_cuajos"),
                "yemas_por_abrir": _count(values, "m2_yp"),
                "yemas_abiertas": _count(values, "m2_ya"),
                "yemas_muertas": _count(values, "m2_ymuerta"),
                "hora": _hora(source, values),
                "item": _item(source, values),
            },
        )
    if source.module_key == "baya":
        return NormalizedEvaluation(
            source,
            {"tipo": "madurez", "observaciones": _observaciones_baya(values)},
        )
    if source.module_key == "pesos":
        return NormalizedEvaluation(
            source,
            {"tipo": "peso", "observaciones": _observaciones_peso(values)},
        )
    if source.module_key == "brotes":
        piso = _text(source.piso) or _text(values.get("m6_piso"))
        if not piso:
            raise EvaluationValidationError(
                "brotes requiere piso; envíelo como piso o valores.m6_piso"
            )
        return NormalizedEvaluation(
            source,
            {
                "piso": piso.upper(),
                "brotes": _count(values, "m6_brotes"),
                "des1": _text(values.get("m6_des1")),
                "des2": _text(values.get("m6_des2")),
                "des3": _text(values.get("m6_des3")),
                "hora": _hora(source, values),
            },
        )
    if source.module_key == "ramas":
        mediciones: list[dict[str, Any]] = []
        for number in range(1, 26):
            suffix = f"{number:02d}"
            diameter = _measure(values.get(f"m7_diam{suffix}"), f"m7_diam{suffix}")
            if diameter is not None:
                mediciones.append({"nro_rama": number, "diametro": diameter})
        if not mediciones:
            raise EvaluationValidationError("ramas requiere al menos una medición de diámetro")
        return NormalizedEvaluation(
            source,
            {
                "ramas_menor5": _count(values, "m7_ram_lt5"),
                "ramas_mayor5": _count(values, "m7_ram_gt5"),
                "mediciones": mediciones,
            },
        )
    raise EvaluationValidationError(f"módulo no soportado: {source.module_key}")


__all__ = ["EvaluationValidationError", "NormalizedEvaluation", "normalize_evaluation"]

"""Validación y normalización de los seis módulos de evaluación de campo."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import time
from decimal import Decimal, InvalidOperation
from typing import Any

from .schemas import EvaluationCreate

_ESTADOS_BAYA = {"FLOR", "CUAJO", "E1", "E2", "E3", "E4", "E5", "DESH", "CAIDO", "X"}


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


def _count(values: dict[str, Any], key: str, *, default: int | None = None) -> int | None:
    number = _decimal(values.get(key), key)
    if number is None:
        return default
    if number != number.to_integral_value():
        raise EvaluationValidationError(f"{key} debe ser un entero")
    if number < 0:
        raise EvaluationValidationError(f"{key} no puede ser negativo")
    if number > 2147483647:
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
    values = _sample_values(values, "baya")
    for number in _sample_numbers(values, ("m4_diam", "m4_est")):
        suffix = f"{number:02d}"
        diameter = _measure(values.get(f"m4_diam{suffix}"), f"m4_diam{suffix}")
        state = _text(values.get(f"m4_est{suffix}"))
        if state:
            state = state.upper()
            if state == "CAÍDO":
                state = "CAIDO"
            if state not in _ESTADOS_BAYA:
                raise EvaluationValidationError(f"m4_est{suffix} no es un estado válido: {state}")
        if diameter is None and state is None:
            continue
        result.append({"numero_muestra": number, "estado_codigo": state, "diametro_mm": diameter})
    if not result:
        raise EvaluationValidationError("baya requiere al menos una observación")
    return result


def _observaciones_peso(values: dict[str, Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    values = _sample_values(values, "pesos")
    for number in _sample_numbers(values, ("m5_peso", "m5_diam")):
        suffix = f"{number:02d}"
        weight = _measure(values.get(f"m5_peso{suffix}"), f"m5_peso{suffix}")
        diameter = _measure(values.get(f"m5_diam{suffix}"), f"m5_diam{suffix}")
        if weight is None and diameter is None:
            continue
        if weight is None or diameter is None:
            raise EvaluationValidationError(f"muestra {number} requiere peso y diámetro")
        result.append({"numero_muestra": number, "peso_g": weight, "diametro_mm": diameter})
    if not result:
        raise EvaluationValidationError("pesos requiere al menos una muestra")
    return result


def _sample_numbers(values, prefixes):
    numbers = set()
    for key in values:
        for prefix in prefixes:
            if key.startswith(prefix):
                suffix = key[len(prefix) :]
                if not re.fullmatch(r"[0-9]+", suffix):
                    raise EvaluationValidationError(f"{key}: ordinal inválido")
                number = int(suffix)
                if not 1 <= number <= 2147483647 or suffix != f"{number:02d}":
                    raise EvaluationValidationError(f"{key}: ordinal inválido")
                numbers.add(number)
    return sorted(numbers)


def _sample_values(values, module):
    """Acepta listas sin columnas numeradas; no mezcla dos representaciones."""
    if "muestras" not in values:
        return values
    prefixes = ("m4_diam", "m4_est") if module == "baya" else ("m5_peso", "m5_diam")
    if any(key.startswith(prefixes) for key in values if key != "muestras"):
        raise EvaluationValidationError("no mezcle muestras con campos numerados")
    rows = values["muestras"]
    if not isinstance(rows, list) or not rows:
        raise EvaluationValidationError("muestras debe ser una lista no vacía")
    result, seen = {}, set()
    for row in rows:
        allowed = {
            "numero_muestra",
            "diametro_mm",
            "estado_codigo" if module == "baya" else "peso_g",
        }
        if not isinstance(row, dict) or set(row) - allowed:
            raise EvaluationValidationError("campos de muestra no válidos")
        number = row.get("numero_muestra")
        if type(number) is not int or not 1 <= number <= 2147483647 or number in seen:
            raise EvaluationValidationError("numero_muestra debe ser positivo y único")
        seen.add(number)
        prefix = "m4" if module == "baya" else "m5"
        result[f"{prefix}_diam{number:02d}"] = row.get("diametro_mm")
        metric, field = ("est", "estado_codigo") if module == "baya" else ("peso", "peso_g")
        result[f"{prefix}_{metric}{number:02d}"] = row.get(field)
    return result


def normalize_evaluation(source: EvaluationCreate) -> NormalizedEvaluation:
    """Valida los valores de Flutter y los transforma al grano de core."""

    values = source.valores
    required_counts = {
        "estadios": [f"m1_e{i}" for i in range(1, 6)],
        "flores": ["m2_flores", "m2_cuajos", "m2_yp", "m2_ya", "m2_ymuerta", "m2_brotes_tiernos"],
        "brotes": ["m6_brotes"],
    }.get(source.module_key)
    if required_counts and all(values.get(key) in (None, "") for key in required_counts):
        raise EvaluationValidationError("se requiere al menos un conteo explícito; cero es válido")
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
                "brotes_tiernos": _count(values, "m2_brotes_tiernos"),
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
        for number in _sample_numbers(values, ("m7_diam",)):
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

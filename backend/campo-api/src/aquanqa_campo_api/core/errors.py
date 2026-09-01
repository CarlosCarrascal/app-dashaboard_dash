"""Contratos de error compartidos por la fachada HTTP."""

from pydantic import BaseModel, ConfigDict, Field


class ApiError(BaseModel):
    """Error legible para la app y para Swagger."""

    model_config = ConfigDict(json_schema_extra={"example": {"detail": "Descripción del error"}})

    detail: str = Field(description="Motivo por el que la operación no pudo completarse")


def error_response(description: str, example: str) -> dict[str, object]:
    return {
        "model": ApiError,
        "description": description,
        "content": {"application/json": {"example": {"detail": example}}},
    }


def validation_error_response(description: str, example: str) -> dict[str, object]:
    """Documenta tanto errores de negocio como validación estructural de FastAPI."""

    return {
        "description": description,
        "content": {
            "application/json": {
                "schema": {
                    "oneOf": [
                        {"$ref": "#/components/schemas/ApiError"},
                        {"$ref": "#/components/schemas/HTTPValidationError"},
                    ]
                },
                "examples": {
                    "regla_negocio": {"value": {"detail": example}},
                    "payload_invalido": {
                        "value": {
                            "detail": [
                                {
                                    "type": "missing",
                                    "loc": ["body", "module_key"],
                                    "msg": "Field required",
                                    "input": {},
                                }
                            ]
                        }
                    },
                },
            }
        },
    }


__all__ = ["ApiError", "error_response", "validation_error_response"]

"""Reexport histórico; la implementación vive en ``analitica.infraestructura``."""

from analitica.infraestructura.postgres import conexion_postgres, obtener_conexion_pg

__all__ = ["conexion_postgres", "obtener_conexion_pg"]

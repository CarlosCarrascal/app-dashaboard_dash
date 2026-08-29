"""Adaptadores para recursos externos usados por los servicios analíticos."""

from .postgres import conexion_postgres, obtener_conexion_pg

__all__ = ["conexion_postgres", "obtener_conexion_pg"]

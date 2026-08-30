"""Compatibilidad histórica para el adaptador PostgreSQL."""

from analitica.infraestructura.postgres import conexion_postgres, obtener_conexion_pg

__all__ = ["conexion_postgres", "obtener_conexion_pg"]

"""Configuración: rutas y conexiones, leídas de `.env` en la raíz del monorepo."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import cache
from pathlib import Path

from dotenv import load_dotenv


@cache
def raiz_repo() -> Path:
    """Raíz del monorepo, buscando hacia arriba el package.json del workspace."""
    actual = Path(__file__).resolve()
    for padre in actual.parents:
        if (padre / "package.json").exists() and (padre / "packages").is_dir():
            return padre
    # Ejecutado fuera del repo (por ejemplo instalado como paquete): dos niveles arriba de src.
    return actual.parents[3]


@cache
def _cargar_env() -> None:
    raiz = raiz_repo()
    for nombre in (".env", ".env.local"):
        archivo = raiz / nombre
        if archivo.exists():
            load_dotenv(archivo, override=False)


def _env(clave: str, defecto: str | None = None) -> str | None:
    _cargar_env()
    valor = os.environ.get(clave, defecto)
    return valor.strip() if isinstance(valor, str) else valor


@dataclass(frozen=True)
class Config:
    # Orígenes
    access_db: Path
    maestro_lotes: Path
    tareo: Path
    # Destino de los CSV intermedios
    dir_extraccion: Path
    # PostgreSQL
    pg_host: str
    pg_port: int
    pg_database: str
    pg_user: str
    pg_password: str

    @property
    def dsn(self) -> str:
        return (
            f"host={self.pg_host} port={self.pg_port} dbname={self.pg_database} "
            f"user={self.pg_user} password={self.pg_password} client_encoding=UTF8"
        )

    def csv_de(self, tabla_destino: str) -> Path:
        return self.dir_extraccion / f"{tabla_destino}.csv"


def _ruta(valor: str | None, defecto: str) -> Path:
    """Resuelve una ruta que puede venir absoluta o relativa a la raíz del repo."""
    bruta = Path(valor or defecto)
    return bruta if bruta.is_absolute() else (raiz_repo() / bruta)


@cache
def cargar_config() -> Config:
    _cargar_env()
    return Config(
        access_db=_ruta(_env("ACCESS_DB_PATH"), "data/entrada/BD_AQUANQA_26.accdb"),
        maestro_lotes=_ruta(_env("MAESTRO_LOTES_PATH"), "data/entrada/M_Lotes.xlsx"),
        tareo=_ruta(_env("TAREO_PATH"), "data/entrada/Query Tareo 2026.xlsx"),
        dir_extraccion=_ruta(_env("EXTRACT_DIR"), "data/salida"),
        pg_host=_env("PGHOST", "localhost") or "localhost",
        pg_port=int(_env("PGPORT", "5432") or 5432),
        pg_database=_env("PGDATABASE", "aquanqa") or "aquanqa",
        pg_user=_env("PGUSER", "postgres") or "postgres",
        pg_password=_env("PGPASSWORD", "") or "",
    )

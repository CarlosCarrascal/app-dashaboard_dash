"""Crea o actualiza un usuario local de la aplicación administrativa.

Uso desde la raíz del monolito:
    python backend/campo-api/scripts/provision_user.py --email admin@empresa.local \
        --nombre "Administrador" --rol admin

Para un rol acotado, agrega por lo menos un alcance: --scope-empresa-id, --scope-fundo-id,
--scope-modulo-id o --scope-lote-id.
"""

from __future__ import annotations

import argparse
import getpass
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from aquanqa_campo_api.core.security import hash_password  # noqa: E402
from aquanqa_campo_api.infrastructure.postgres.connection import (  # noqa: E402
    PostgresConnectionFactory,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--email", required=True)
    parser.add_argument("--nombre", required=True)
    parser.add_argument(
        "--rol",
        choices=("admin", "agronomo", "evaluador", "lectura"),
        default="lectura",
    )
    parser.add_argument("--password")
    for scope in ("empresa", "fundo", "modulo", "lote"):
        parser.add_argument(f"--scope-{scope}-id", type=int)
    parser.add_argument(
        "--database-url",
        help=(
            "DSN privilegiado para escribir en core.m_usuario. También puede venir de "
            "AQUANQA_PROVISION_DATABASE_URL."
        ),
    )
    args = parser.parse_args()
    scope = {
        "empresa_id": args.scope_empresa_id,
        "fundo_id": args.scope_fundo_id,
        "modulo_id": args.scope_modulo_id,
        "lote_id": args.scope_lote_id,
    }
    if any(value is not None and value <= 0 for value in scope.values()):
        raise SystemExit("Los IDs de alcance deben ser enteros positivos")
    if args.rol != "admin" and not any(value is not None for value in scope.values()):
        raise SystemExit("Un usuario que no es admin necesita al menos un alcance de datos")
    if args.password:
        password = args.password
    else:
        password = getpass.getpass("Contraseña: ")
        confirmation = getpass.getpass("Repita la contraseña: ")
        if password != confirmation:
            raise SystemExit("Las contraseñas no coinciden")
    database_url = args.database_url or os.getenv("AQUANQA_PROVISION_DATABASE_URL")
    if not database_url:
        raise SystemExit(
            "Indica --database-url o AQUANQA_PROVISION_DATABASE_URL con una conexión "
            "privilegiada; la conexión de la API es de solo lectura para usuarios."
        )
    connections = PostgresConnectionFactory(database_url)
    try:
        with connections.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO core.m_usuario (email, nombre, hash_password, rol_id)
                SELECT lower(%s), %s, %s, rol_id
                FROM core.m_rol WHERE codigo = %s
                ON CONFLICT (email) DO UPDATE
                SET nombre = excluded.nombre,
                    hash_password = excluded.hash_password,
                    rol_id = excluded.rol_id,
                    activo = true
                """,
                (args.email, args.nombre, hash_password(password), args.rol),
            )
            if cursor.rowcount != 1:
                raise SystemExit(f"No existe el rol {args.rol}")
            cursor.execute(
                "SELECT usuario_id FROM core.m_usuario WHERE email = lower(%s)",
                (args.email,),
            )
            user = cursor.fetchone()
            if user is None:
                raise SystemExit("No se pudo recuperar el usuario provisionado")
            cursor.execute(
                "DELETE FROM core.m_usuario_alcance WHERE usuario_id = %s",
                (user["usuario_id"],),
            )
            if any(value is not None for value in scope.values()):
                cursor.execute(
                    """
                    INSERT INTO core.m_usuario_alcance
                        (usuario_id, empresa_id, fundo_id, modulo_id, lote_id)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (
                        user["usuario_id"],
                        scope["empresa_id"],
                        scope["fundo_id"],
                        scope["modulo_id"],
                        scope["lote_id"],
                    ),
                )
        print(f"Usuario provisionado: {args.email.lower()} ({args.rol})")
    finally:
        connections.close()


if __name__ == "__main__":
    main()

import os

import pytest

from aquanqa_campo_api.core.settings import get_settings
from aquanqa_campo_api.infrastructure.postgres.admin_repository import PostgresAdminRepository
from aquanqa_campo_api.infrastructure.postgres.catalogos_repository import (
    PostgresCatalogRepository,
)
from aquanqa_campo_api.infrastructure.postgres.connection import (
    PostgresConnectionFactory,
    PostgresHealthRepository,
)
from aquanqa_campo_api.infrastructure.postgres.evaluaciones_repository import (
    PostgresEvaluationRepository,
)
from aquanqa_campo_api.infrastructure.postgres.identidad_repository import (
    PostgresIdentityRepository,
)
from aquanqa_campo_api.modules.admin.schemas import (
    AdminEvaluationQuery,
    AdminLoadQuery,
    AdminMasterQuery,
    AdminQAQuery,
)

pytestmark = pytest.mark.db


@pytest.mark.skipif(
    os.getenv("AQUANQA_RUN_DB_TESTS") != "1",
    reason="defina AQUANQA_RUN_DB_TESTS=1 para usar PostgreSQL real",
)
def test_postgres_esta_disponible_y_expone_fundos():
    connections = PostgresConnectionFactory(get_settings().database_url)
    PostgresHealthRepository(connections).ping()
    assert PostgresCatalogRepository(connections).list_fundos()


@pytest.mark.skipif(
    os.getenv("AQUANQA_RUN_DB_TESTS") != "1",
    reason="defina AQUANQA_RUN_DB_TESTS=1 para usar PostgreSQL real",
)
def test_historial_incluye_evaluaciones_historicas_del_evaluador():
    connections = PostgresConnectionFactory(get_settings().database_url)
    evaluator = PostgresIdentityRepository(connections).find_evaluador_by_dni("10616663")
    assert evaluator is not None
    evaluator_id = int(evaluator["evaluador_id"])
    page = PostgresEvaluationRepository(connections).list_history(
        evaluador_id=evaluator_id,
        evaluador_dni="10616663",
        module_key=None,
        limit=20,
        offset=0,
    )

    assert len(page.items) == 20
    assert page.has_more
    assert all(item.evaluador_id == evaluator_id for item in page.items)


@pytest.mark.skipif(
    os.getenv("AQUANQA_RUN_DB_TESTS") != "1",
    reason="defina AQUANQA_RUN_DB_TESTS=1 para usar PostgreSQL real",
)
def test_panel_admin_consulta_evaluaciones_roles_y_qa():
    connections = PostgresConnectionFactory(get_settings().database_url)
    repository = PostgresAdminRepository(connections, usuario_id=1, unrestricted=True)
    evaluations = repository.list_evaluations(AdminEvaluationQuery(page_size=5))
    summary = repository.evaluation_summary(AdminEvaluationQuery())
    roles = repository.list_roles(AdminMasterQuery(page_size=20))
    loads = repository.list_imports(AdminLoadQuery(page_size=5))
    quality = repository.list_qa(AdminQAQuery(page_size=5))

    assert summary.total > 0
    assert [item.module_key for item in summary.por_modulo] == [
        "estadios",
        "flores",
        "baya",
        "pesos",
        "brotes",
        "ramas",
    ]
    baya = next(item for item in summary.por_modulo if item.module_key == "baya")
    assert baya.muestras >= baya.total
    assert baya.indicadores.diametro_promedio_mm is not None
    assert evaluations.items
    assert any(item["codigo"] == "admin" for item in roles.items)
    assert loads.meta.total >= 0
    assert quality.meta.total > 0


@pytest.mark.skipif(
    os.getenv("AQUANQA_RUN_DB_TESTS") != "1",
    reason="defina AQUANQA_RUN_DB_TESTS=1 para usar PostgreSQL real",
)
def test_panel_admin_no_expone_datos_a_un_usuario_sin_alcance():
    connections = PostgresConnectionFactory(get_settings().database_url)
    repository = PostgresAdminRepository(connections, usuario_id=999999, unrestricted=False)
    page = repository.list_evaluations(AdminEvaluationQuery(page_size=5))
    summary = repository.evaluation_summary(AdminEvaluationQuery())

    assert page.items == []
    assert summary.total == 0


@pytest.mark.skipif(
    os.getenv("AQUANQA_RUN_DB_TESTS") != "1",
    reason="defina AQUANQA_RUN_DB_TESTS=1 para usar PostgreSQL real",
)
def test_rol_api_conserva_solo_privilegios_necesarios():
    connections = PostgresConnectionFactory(get_settings().database_url)
    with connections.connect() as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT current_user,
                       has_table_privilege(current_user, 'core.ev_estados', 'INSERT') AS captura,
                       has_table_privilege(current_user, 'core.m_empresa', 'INSERT') AS maestros,
                       has_table_privilege(
                           current_user, 'qua.rechazo_revision_evento', 'INSERT'
                       ) AS qa_revision_direct,
                       has_function_privilege(
                           current_user, 'stg.fn_resolver_lote(text,text,text)', 'EXECUTE'
                       ) AS resolver,
                   (
                       SELECT count(*)
                       FROM pg_proc p
                       JOIN pg_namespace n ON n.oid = p.pronamespace
                       WHERE n.nspname IN ('raw', 'stg', 'qua', 'core')
                         AND has_function_privilege(current_user, p.oid, 'EXECUTE')
                   ) AS funciones
            """
        )
        privileges = cursor.fetchone()

    assert privileges["current_user"] == "aquanqa_app"
    assert privileges["captura"] is True
    assert privileges["maestros"] is False
    assert privileges["qa_revision_direct"] is False
    assert privileges["resolver"] is True
    # Resolver de lotes + las cinco funciones administrativas allowlisted.
    assert privileges["funciones"] == 6

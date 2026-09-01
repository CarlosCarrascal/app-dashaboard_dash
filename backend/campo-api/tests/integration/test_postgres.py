import os

import pytest

from aquanqa_campo_api.core.settings import get_settings
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
    page = PostgresEvaluationRepository(connections).list_history(
        evaluador_id=200,
        evaluador_dni="10616663",
        module_key=None,
        limit=20,
        offset=0,
    )

    assert len(page.items) == 20
    assert page.has_more
    assert all(item.evaluador_id == 200 for item in page.items)

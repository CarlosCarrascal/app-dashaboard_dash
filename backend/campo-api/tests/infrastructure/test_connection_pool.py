from __future__ import annotations

from contextlib import contextmanager

from aquanqa_campo_api.infrastructure.postgres.connection import PostgresConnectionFactory


class FakePool:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.open_calls = 0
        self.close_calls = 0
        self.connection_calls = 0

    def open(self, *, wait: bool) -> None:
        assert wait is True
        self.open_calls += 1

    def close(self) -> None:
        self.close_calls += 1

    @contextmanager
    def connection(self):
        self.connection_calls += 1
        yield object()


def test_el_pool_se_abre_una_vez_reutiliza_conexiones_y_se_cierra(monkeypatch):
    created: list[FakePool] = []

    def make_pool(**kwargs):
        pool = FakePool(**kwargs)
        created.append(pool)
        return pool

    monkeypatch.setattr(
        "aquanqa_campo_api.infrastructure.postgres.connection.ConnectionPool",
        make_pool,
    )
    factory = PostgresConnectionFactory(
        "postgresql://user:pass@db/aquanqa_migracion",
        min_size=1,
        max_size=10,
        timeout=5,
    )

    with factory.connect():
        pass
    with factory.connect():
        pass
    factory.close()

    pool = created[0]
    assert pool.kwargs["min_size"] == 1
    assert pool.kwargs["max_size"] == 10
    assert pool.open_calls == 1
    assert pool.connection_calls == 2
    assert pool.close_calls == 1


def test_independent_reads_restore_transaction_mode_even_on_error(monkeypatch):
    from types import SimpleNamespace
    import pytest

    connection = SimpleNamespace(autocommit=False, closed=False)

    class Pool(FakePool):
        @contextmanager
        def connection(self):
            yield connection

    monkeypatch.setattr(
        "aquanqa_campo_api.infrastructure.postgres.connection.ConnectionPool", Pool
    )
    factory = PostgresConnectionFactory("postgresql://unused")
    with factory.read() as read:
        assert read.autocommit is True
    assert connection.autocommit is False
    with pytest.raises(ValueError):
        with factory.read():
            raise ValueError("failed SELECT")
    assert connection.autocommit is False
    with factory.connect() as transaction:
        assert transaction.autocommit is False

from unittest.mock import patch

from analitica.servicios.infraestructura.postgres import (
    conexion_postgres,
    obtener_conexion_pg,
)


def test_obtener_conexion_pg_concentra_configuracion_sin_conectar_a_una_db_real(monkeypatch):
    monkeypatch.setenv("PGDATABASE", "prueba_db")
    monkeypatch.setenv("PGUSER", "usuario_prueba")
    monkeypatch.setenv("PGPASSWORD", "secreto_prueba")
    monkeypatch.setenv("PGHOST", "servidor_prueba")
    monkeypatch.setenv("PGPORT", "5544")

    with (
        patch("dotenv.load_dotenv") as load_dotenv,
        patch("psycopg.connect", return_value="conexion_falsa") as connect,
    ):
        resultado = obtener_conexion_pg()

    assert resultado == "conexion_falsa"
    load_dotenv.assert_called_once()
    connect.assert_called_once_with(
        dbname="prueba_db",
        user="usuario_prueba",
        password="secreto_prueba",
        host="servidor_prueba",
        port="5544",
    )


def test_fachada_historica_del_servicio_delega_en_infraestructura():
    with patch(
        "analitica.servicios.servicio_bhattacharya.obtener_conexion_pg",
        return_value="conexion_falsa",
    ) as obtener:
        from analitica.servicios.servicio_bhattacharya import _obtener_conexion_pg

        assert _obtener_conexion_pg() == "conexion_falsa"

    obtener.assert_called_once_with()


def test_conexion_postgres_usa_dsn_y_cierra_el_contexto():
    with patch("psycopg.connect") as connect:
        connect.return_value.__enter__.return_value = "conexion_falsa"

        with conexion_postgres("postgresql://prueba", connect_timeout=3) as resultado:
            assert resultado == "conexion_falsa"

    connect.assert_called_once_with("postgresql://prueba", connect_timeout=3)
    connect.return_value.__exit__.assert_called_once()

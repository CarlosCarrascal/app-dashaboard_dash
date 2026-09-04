from __future__ import annotations

from fastapi.testclient import TestClient

from aquanqa_campo_api.api.dependencies import get_auth_repository, get_current_user
from aquanqa_campo_api.core.security import hash_password
from aquanqa_campo_api.main import app
from aquanqa_campo_api.modules.seguridad.schemas import AuthUser


class FakeAuthRepository:
    def __init__(self):
        self.row = {
            "usuario_id": 41,
            "email": "admin@aquanqa.local",
            "nombre": "Administrador Aqu Anqa",
            "hash_password": hash_password("Clave segura 2026!"),
            "activo": True,
            "rol": "admin",
            "permisos": [
                "admin:panel:leer",
                "admin:evaluaciones:leer",
                "admin:evaluaciones:cargar",
                "admin:maestros:leer",
                "admin:usuarios:gestionar",
                "admin:qa:leer",
            ],
        }
        self.touched = []

    def find_by_email(self, email):
        return self.row if email.casefold() == self.row["email"] else None

    def find_by_id(self, usuario_id):
        return self.row if usuario_id == self.row["usuario_id"] else None

    def touch_login(self, usuario_id):
        self.touched.append(usuario_id)


def test_login_me_y_refresh_conservan_la_identidad():
    repository = FakeAuthRepository()
    app.dependency_overrides[get_auth_repository] = lambda: repository
    client = TestClient(app)
    try:
        login = client.post(
            "/v1/auth/login",
            json={"email": " ADMIN@AQUANQA.LOCAL ", "password": "Clave segura 2026!"},
        )
        assert login.status_code == 200, login.text
        tokens = login.json()
        assert tokens["token_type"] == "bearer"
        assert tokens["user"]["rol"] == "admin"
        assert repository.touched == [41]

        me = client.get(
            "/v1/auth/me",
            headers={"Authorization": f"Bearer {tokens['access_token']}"},
        )
        assert me.status_code == 200
        assert me.json()["email"] == "admin@aquanqa.local"

        refreshed = client.post(
            "/v1/auth/refresh",
            json={"refresh_token": tokens["refresh_token"]},
        )
        assert refreshed.status_code == 200, refreshed.text
        assert refreshed.json()["user"]["usuario_id"] == 41
    finally:
        app.dependency_overrides.clear()


def test_login_rechaza_credencial_incorrecta():
    app.dependency_overrides[get_auth_repository] = lambda: FakeAuthRepository()
    client = TestClient(app)
    try:
        response = client.post(
            "/v1/auth/login",
            json={"email": "admin@aquanqa.local", "password": "incorrecta"},
        )
        assert response.status_code == 401
        assert response.json()["detail"] == "Email o contraseña incorrectos"
    finally:
        app.dependency_overrides.clear()


def test_admin_requiere_bearer_y_permiso_de_modulo():
    client = TestClient(app)
    assert client.get("/v1/admin/evaluaciones").status_code == 401

    app.dependency_overrides[get_current_user] = lambda: AuthUser(
        usuario_id=41,
        email="lectura@aquanqa.local",
        nombre="Solo lectura",
        rol="lectura",
        permisos=["admin:panel:leer"],
    )
    try:
        response = client.get("/v1/admin/roles")
        assert response.status_code == 403
        assert "admin:usuarios:gestionar" in response.json()["detail"]
    finally:
        app.dependency_overrides.clear()

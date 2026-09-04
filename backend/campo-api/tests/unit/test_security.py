from __future__ import annotations

import time

import pytest

from aquanqa_campo_api.core.security import (
    TokenError,
    decode_token,
    encode_token,
    hash_password,
    verify_password,
)


def test_hash_de_password_no_expone_la_clave_y_verifica():
    encoded = hash_password("Clave segura 2026!")

    assert encoded != "Clave segura 2026!"
    assert verify_password("Clave segura 2026!", encoded)
    assert not verify_password("otra clave", encoded)
    assert not verify_password("Clave segura 2026!", None)


def test_token_firmado_se_decodifica_con_el_tipo_correcto():
    token = encode_token(
        {"sub": "41", "typ": "access", "exp": int(time.time()) + 60},
        "test-secret",
    )

    claims = decode_token(token, "test-secret", expected_type="access")

    assert claims["sub"] == "41"
    with pytest.raises(TokenError, match="Tipo de token"):
        decode_token(token, "test-secret", expected_type="refresh")


def test_token_vencido_o_manipulado_se_rechaza():
    expired = encode_token(
        {"sub": "41", "typ": "access", "exp": int(time.time()) - 1},
        "test-secret",
    )
    with pytest.raises(TokenError, match="vencido"):
        decode_token(expired, "test-secret", expected_type="access")

    with pytest.raises(TokenError):
        decode_token("no.es.un.jwt", "test-secret", expected_type="access")


def test_token_con_segmento_no_ascii_se_rechaza_sin_excepcion_de_unicode():
    with pytest.raises(TokenError, match="mal formado"):
        decode_token("é.é.é", "test-secret", expected_type="access")

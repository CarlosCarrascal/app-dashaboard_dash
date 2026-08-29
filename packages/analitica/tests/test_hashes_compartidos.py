from hashlib import sha256

import pytest

from analitica.proyeccion.compartido import sha256_archivo
from analitica.proyeccion.exportacion import sha256_archivo as hash_de_exportacion
from analitica.proyeccion.hibrido_parametros_asof import (
    sha256_archivo as hash_de_parametros,
)
from analitica.proyeccion.validacion_operativa import sha256_archivo as hash_de_validacion


def test_las_fachadas_de_hash_comparten_la_misma_implementacion(tmp_path):
    archivo = tmp_path / "muestra.bin"
    archivo.write_bytes(b"Aqu Anqa\x00" * 257)

    esperado = sha256(archivo.read_bytes()).hexdigest()

    assert sha256_archivo(archivo) == esperado
    assert hash_de_exportacion is sha256_archivo
    assert hash_de_parametros is sha256_archivo
    assert hash_de_validacion is sha256_archivo
    assert sha256_archivo(str(archivo)) == esperado


def test_hash_compartido_conserva_el_error_de_archivo_inexistente(tmp_path):
    with pytest.raises(FileNotFoundError):
        sha256_archivo(tmp_path / "no-existe.bin")

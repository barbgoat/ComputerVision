import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from leitor.validador import Resultado, digito_controlo, normalizar, validar  # noqa: E402

EAN13 = "8720182643124"   # código esperado das imagens de teste
EAN12 = "872018264312"    # mesmo código como o MCM o guarda (sem controlo)
OUTRO = "4006381333931"


def test_digito_controlo():
    assert digito_controlo(EAN12) == 4
    assert digito_controlo(OUTRO[:12]) == 1


@pytest.mark.parametrize("entrada", [EAN13, EAN12, f" {EAN12[:4]}-{EAN12[4:]} ", f"{EAN13}\n"])
def test_normalizar_validos(entrada):
    assert normalizar(entrada) == EAN13


@pytest.mark.parametrize("entrada", [
    None, "", "abc", "123", "8720182643125", "87201826431240", "8720182643", "12345678",
])
def test_normalizar_invalidos(entrada):
    assert normalizar(entrada) is None


def test_ok_13_vs_13():
    assert validar(EAN13, EAN13) is Resultado.OK


def test_ok_12_vs_13():
    assert validar(EAN13, EAN12) is Resultado.OK   # lido pela câmara, esperado do MCM
    assert validar(EAN12, EAN13) is Resultado.OK


def test_nok():
    assert validar(OUTRO, EAN12) is Resultado.NOK


def test_sem_leitura():
    assert validar(None, EAN13) is Resultado.SEM_LEITURA
    assert validar("8720182643125", EAN13) is Resultado.SEM_LEITURA  # controlo errado


def test_esperado_invalido():
    with pytest.raises(ValueError):
        validar(EAN13, "123")

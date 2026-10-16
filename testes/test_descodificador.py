"""Testes da cascata.

NOTA: o gerador de códigos do zxing-cpp 3.1.1 (write_barcode / to_image) dá "access
violation" nesta máquina, por isso os EAN-13 sintéticos são gerados aqui à mão e os
2D vêm das imagens reais em img/.
"""
import sys
from pathlib import Path

import cv2
import numpy as np
import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from leitor.config import ConfigDescodificacao, ConfigROI  # noqa: E402
from leitor.descodificador import Descodificador, Leitura, localizar_tipado  # noqa: E402
from leitor.produtos import Produtos  # noqa: E402
from leitor.resultado import Estado, classificar  # noqa: E402

EAN = "8720182643124"

_L = ["0001101", "0011001", "0010011", "0111101", "0100011", "0110001", "0101111", "0111011", "0110111", "0001011"]
_G = ["0100111", "0110011", "0011011", "0100001", "0011101", "0111001", "0000101", "0010001", "0001001", "0010111"]
_R = ["1110010", "1100110", "1101100", "1000010", "1011100", "1001110", "1010000", "1000100", "1001000", "1110100"]
_PRIMEIRO = ["LLLLLL", "LLGLGG", "LLGGLG", "LLGGGL", "LGLLGG", "LGGLLG", "LGGGLL", "LGLGLG", "LGLGGL", "LGGLGL"]


def _ean13(codigo: str, modulo: int = 3, altura: int = 150, quiet: int = 12) -> np.ndarray:
    d = [int(c) for c in codigo]
    bits = "101"
    for i, dig in enumerate(d[1:7]):
        bits += (_L if _PRIMEIRO[d[0]][i] == "L" else _G)[dig]
    bits += "01010"
    bits += "".join(_R[dig] for dig in d[7:])
    bits += "101"
    linha = np.full((len(bits) + 2 * quiet) * modulo, 255, np.uint8)
    for i, b in enumerate(bits):
        if b == "1":
            linha[(quiet + i) * modulo:(quiet + i + 1) * modulo] = 0
    return np.tile(linha, (altura, 1))


def _cena(codigo: np.ndarray, x: int = 200, y: int = 150, fundo: int = 120) -> np.ndarray:
    cena = np.full((600, 800), fundo, np.uint8)
    h, w = codigo.shape
    cena[y:y + h, x:x + w] = codigo
    return cena


def _imagem_real(nome: str) -> np.ndarray:
    im = cv2.imread(str(RAIZ / "img" / nome), cv2.IMREAD_GRAYSCALE)
    assert im is not None, nome
    return im


@pytest.fixture
def desc():
    return Descodificador(ConfigDescodificacao(), ConfigROI())


def test_ean_sintetico_lido_no_nivel_1(desc):
    r = desc.ler(_cena(_ean13(EAN)))
    assert r.texto == EAN and r.formato == "EAN13" and r.tentativa == "N1:direta"


def test_ean_real_lido(desc):
    r = desc.ler(_imagem_real("Image__2026-10-15__13-51-05.bmp"))
    assert r.texto == EAN


def test_datamatrix_real_lido_qualquer_formato(desc):
    r = desc.ler(_imagem_real("Image__2026-10-15__13-51-17.bmp"))
    assert r.texto == "65711835" and r.formato == "DataMatrix"


def test_localiza_barras_1d_rodadas():
    rodado = np.ascontiguousarray(np.rot90(_ean13(EAN, modulo=4)))
    tipadas = localizar_tipado(_cena(rodado, x=300, y=40))
    assert any(tipo == "1D" for _, tipo in tipadas)


def test_codigo_cortado_nunca_inventa(desc):
    img = _ean13(EAN, modulo=4)
    cortado = np.ascontiguousarray(img[:, : img.shape[1] * 6 // 10])     # só 60 % das barras
    r = desc.ler(_cena(cortado, x=100))
    assert r.texto is None                                  # nunca completa o código em falta
    det = classificar(r, Produtos())
    assert det.estado in (Estado.PARCIAL, Estado.NAO_ENCONTRADO)
    assert det.codigo is None and det.produto is None


def test_imagem_real_cortada_na_margem_e_parcial(desc):
    r = desc.ler(_imagem_real("Image__2026-10-15__13-51-34.bmp"))   # barras cortadas pelo bordo
    det = classificar(r, Produtos())
    assert det.estado is Estado.PARCIAL and det.roi is not None and det.codigo is None


def test_imagem_vazia_nao_encontrado(desc):
    r = desc.ler(np.full((480, 640), 90, np.uint8))
    assert r.texto is None and r.roi is None
    assert classificar(r, Produtos()).estado is Estado.NAO_ENCONTRADO


def test_parcial_quando_ha_roi_sem_leitura():
    d = classificar(Leitura(None, roi=(10, 20, 100, 50)), Produtos())
    assert d.estado is Estado.PARCIAL and d.roi == (10, 20, 100, 50) and d.codigo is None

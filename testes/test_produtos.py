import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from leitor.descodificador import Leitura  # noqa: E402
from leitor.produtos import PRODUTO_DESCONHECIDO, Produtos  # noqa: E402
from leitor.resultado import Estado, classificar  # noqa: E402
from leitor.validador import Resultado  # noqa: E402

RAIZ = Path(__file__).resolve().parent.parent


@pytest.fixture
def produtos(tmp_path):
    f = tmp_path / "p.csv"
    f.write_text("codigo;produto\n872018264312;Sopa\nABC-123;Peça interna\n", encoding="utf-8")
    return Produtos.carregar(f)


def test_procura_por_12_ou_13_digitos(produtos):
    assert produtos.procurar("8720182643124") == "Sopa"
    assert produtos.procurar("872018264312") == "Sopa"


def test_codigo_nao_ean(produtos):
    assert produtos.procurar("ABC-123") == "Peça interna"


def test_desconhecido(produtos):
    assert produtos.procurar("4006381333931") == PRODUTO_DESCONHECIDO
    assert produtos.procurar(None) == PRODUTO_DESCONHECIDO


def test_ficheiro_em_falta_nao_rebenta(tmp_path):
    assert len(Produtos.carregar(tmp_path / "nao_existe.csv")) == 0


def test_duplicado_conflituoso(tmp_path):
    f = tmp_path / "p.csv"
    f.write_text("codigo;produto\n8720182643124;A\n872018264312;B\n", encoding="utf-8")
    with pytest.raises(ValueError):
        Produtos.carregar(f)


def test_produtos_csv_de_exemplo():
    assert Produtos.carregar(RAIZ / "produtos.csv").procurar("8720182643124") != PRODUTO_DESCONHECIDO


def test_classificar_lido_ok(produtos):
    d = classificar(Leitura("8720182643124", "EAN13", "x1", 5.0), produtos, "872018264312")
    assert d.estado is Estado.LIDO and d.produto == "Sopa" and d.conformidade is Resultado.OK


def test_classificar_lido_nok_produto_desconhecido(produtos):
    d = classificar(Leitura("4006381333931", "EAN13", "x1", 5.0), produtos, "8720182643124")
    assert d.produto == PRODUTO_DESCONHECIDO and d.conformidade is Resultado.NOK


def test_classificar_sem_esperado(produtos):
    d = classificar(Leitura("8720182643124", "EAN13", "x1", 5.0), produtos)
    assert d.conformidade is None


def test_classificar_nao_encontrado_nunca_inventa(produtos):
    d = classificar(Leitura(None, tempo_ms=9.0), produtos, "8720182643124")
    assert d.estado is Estado.NAO_ENCONTRADO
    assert d.codigo is None and d.produto is None and d.conformidade is None

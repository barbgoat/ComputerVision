"""Tabela de produtos (produtos.csv: codigo;produto) → nome do produto."""
from __future__ import annotations

import csv
from pathlib import Path

from .validador import normalizar

PRODUTO_DESCONHECIDO = "produto desconhecido"


def chave(codigo: str) -> str:
    """EAN/UPC (12 ou 13 dígitos) → EAN-13; qualquer outro código fica como está."""
    codigo = codigo.strip()
    return normalizar(codigo) or codigo


class Produtos:
    def __init__(self, tabela: dict[str, str] | None = None):
        self._tabela = tabela or {}

    def __len__(self) -> int:
        return len(self._tabela)

    def procurar(self, codigo: str | None) -> str:
        if not codigo:
            return PRODUTO_DESCONHECIDO
        return self._tabela.get(chave(codigo), PRODUTO_DESCONHECIDO)

    @classmethod
    def carregar(cls, caminho: str | Path) -> "Produtos":
        caminho = Path(caminho)
        if not caminho.exists():
            return cls()
        tabela: dict[str, str] = {}
        with open(caminho, newline="", encoding="utf-8-sig") as f:
            for n, linha in enumerate(csv.DictReader(f, delimiter=";"), start=2):
                codigo = (linha.get("codigo") or "").strip()
                produto = (linha.get("produto") or "").strip()
                if not codigo or not produto:
                    continue
                k = chave(codigo)
                if k in tabela and tabela[k] != produto:
                    raise ValueError(f"{caminho.name} linha {n}: código {codigo} repetido com outro produto")
                tabela[k] = produto
        return cls(tabela)

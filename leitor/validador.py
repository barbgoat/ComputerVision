"""Normaliza o EAN (12/13 dígitos) e compara com o esperado → OK / NOK / SEM_LEITURA.

O MCM guarda códigos de 12 dígitos SEM dígito de controlo; o leitor devolve 13.
Por isso 12 dígitos → calcula-se e acrescenta-se o dígito de controlo;
13 dígitos → verifica-se o dígito de controlo.
"""
from __future__ import annotations

from enum import Enum


class Resultado(str, Enum):
    OK = "OK"
    NOK = "NOK"
    SEM_LEITURA = "SEM_LEITURA"


def digito_controlo(corpo: str) -> int:
    """Dígito de controlo EAN-13 para os 12 dígitos do corpo."""
    soma = sum(int(d) * (3 if i % 2 == 0 else 1) for i, d in enumerate(reversed(corpo)))
    return (10 - soma % 10) % 10


def normalizar(codigo: str | None) -> str | None:
    """Devolve o EAN-13 normalizado, ou None se inválido.

    Aceita 12 dígitos (sem controlo) ou 13 (com controlo, que é verificado).
    """
    if codigo is None:
        return None
    digitos = "".join(c for c in str(codigo) if not c.isspace() and c != "-")
    if not digitos.isdigit():
        return None
    if len(digitos) == 12:
        return digitos + str(digito_controlo(digitos))
    if len(digitos) == 13 and digito_controlo(digitos[:12]) == int(digitos[12]):
        return digitos
    return None


def comparar(lido: str, esperado: str) -> Resultado:
    """OK/NOK sobre um código já LIDO (de qualquer formato).

    EAN/UPC compara-se normalizado (12 ≙ 13 dígitos); outros códigos, por igualdade exata.
    """
    n_lido, n_esperado = normalizar(lido), normalizar(esperado)
    if n_lido is not None and n_esperado is not None:
        return Resultado.OK if n_lido == n_esperado else Resultado.NOK
    return Resultado.OK if lido.strip() == esperado.strip() else Resultado.NOK


def validar(lido: str | None, esperado: str) -> Resultado:
    ean_esperado = normalizar(esperado)
    if ean_esperado is None:
        raise ValueError(f"Código esperado inválido: {esperado!r}")
    ean_lido = normalizar(lido)
    if ean_lido is None:
        return Resultado.SEM_LEITURA
    return Resultado.OK if ean_lido == ean_esperado else Resultado.NOK

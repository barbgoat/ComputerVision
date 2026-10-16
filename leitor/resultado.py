"""Resultado de uma deteção: LIDO / PARCIAL / NAO_ENCONTRADO (+ OK/NOK se houver esperado)."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .descodificador import Leitura
from .produtos import PRODUTO_DESCONHECIDO, Produtos
from .validador import Resultado, comparar


class Estado(str, Enum):
    LIDO = "LIDO"                        # descodificado de facto
    PARCIAL = "PARCIAL"                  # ROI encontrada, mas não descodificada
    NAO_ENCONTRADO = "NAO_ENCONTRADO"    # nenhuma ROI nem código


@dataclass
class Deteccao:
    estado: Estado
    codigo: str | None = None
    formato: str = ""
    nivel: str = ""                      # nível da cascata que leu (ou "")
    produto: str | None = None           # só preenchido quando LIDO
    tempo_ms: float = 0.0
    roi: tuple[int, int, int, int] | None = None   # x, y, largura, altura (PARCIAL)
    conformidade: Resultado | None = None          # OK/NOK só se houver esperado


def classificar(leitura: Leitura, produtos: Produtos, esperado: str = "") -> Deteccao:
    """Converte a saída do descodificador num resultado explícito.

    Nunca inventa o código: sem leitura → PARCIAL (ROI encontrada) ou NAO_ENCONTRADO.
    """
    if leitura.texto is None:
        if leitura.roi is not None:
            return Deteccao(Estado.PARCIAL, nivel="N2:roi", tempo_ms=leitura.tempo_ms, roi=leitura.roi)
        return Deteccao(Estado.NAO_ENCONTRADO, tempo_ms=leitura.tempo_ms)
    det = Deteccao(
        Estado.LIDO,
        codigo=leitura.texto,
        formato=leitura.formato,
        nivel=leitura.tentativa,
        produto=produtos.procurar(leitura.texto),
        tempo_ms=leitura.tempo_ms,
        roi=leitura.roi,
    )
    if esperado:
        det.conformidade = comparar(det.codigo, esperado)
    return det


__all__ = ["Estado", "Deteccao", "classificar", "PRODUTO_DESCONHECIDO"]

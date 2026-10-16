"""Calibração da ROI fixa: mede onde os códigos aparecem nas imagens reais.

Não é aprendizagem automática: para cada imagem lê-se o código (cascata completa, sem ROI
fixa) e guarda-se a caixa onde ele esteve; a ROI proposta é o envelope dessas caixas com
folga. Quanto mais variadas as imagens (posições/rotações reais da linha), melhor.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import zxingcpp

from .descodificador import Caixa, Descodificador, para_cinzento
from .produtos import chave


@dataclass
class Observacao:
    imagem: str
    codigo: str
    formato: str
    caixa: Caixa
    exata: bool        # True: posição devolvida pelo zxing; False: caixa da ROI que o leu (aprox.)


def caixa_de(codigo) -> Caixa:
    p = codigo.position
    xs = [p.top_left.x, p.top_right.x, p.bottom_left.x, p.bottom_right.x]
    ys = [p.top_left.y, p.top_right.y, p.bottom_left.y, p.bottom_right.y]
    x, y = min(xs), min(ys)
    return (x, y, max(xs) - x, max(ys) - y)


def observar(nome: str, imagem: np.ndarray, desc: Descodificador,
             formatos: set[str] | None = None) -> list[Observacao]:
    """Códigos encontrados na imagem inteira. `desc` deve ter a ROI fixa desativada."""
    cinzento = np.ascontiguousarray(para_cinzento(imagem))
    codigos = zxingcpp.read_barcodes(cinzento, formats=desc.formatos, try_rotate=True)
    obs = [Observacao(nome, c.text, c.format.name, caixa_de(c), True) for c in codigos]
    if not obs:                                   # N1 falhou: usar a cascata (N2) e a sua ROI
        leitura = desc.ler(imagem)
        if leitura.texto is not None and leitura.roi is not None:
            obs.append(Observacao(nome, leitura.texto, leitura.formato, leitura.roi, False))
    if formatos is not None:
        obs = [o for o in obs if o.formato in formatos]
    return obs


def agrupar(observacoes: list[Observacao]) -> dict[str, list[Observacao]]:
    """Agrupa por código (EAN de 12/13 dígitos equivalem-se)."""
    grupos: dict[str, list[Observacao]] = {}
    for o in observacoes:
        grupos.setdefault(chave(o.codigo), []).append(o)
    return grupos


def envolvente(caixas: list[Caixa], margem: float, largura: int, altura: int,
               margem_min: int = 16) -> Caixa:
    """Menor caixa que contém todas, com folga (`margem` × tamanho da envolvente), ao limite da imagem."""
    x0 = min(c[0] for c in caixas)
    y0 = min(c[1] for c in caixas)
    x1 = max(c[0] + c[2] for c in caixas)
    y1 = max(c[1] + c[3] for c in caixas)
    mx = max(margem_min, int((x1 - x0) * margem))
    my = max(margem_min, int((y1 - y0) * margem))
    x0, y0 = max(0, x0 - mx), max(0, y0 - my)
    x1, y1 = min(largura, x1 + mx), min(altura, y1 + my)
    return (x0, y0, x1 - x0, y1 - y0)


def contem(roi: Caixa, caixa: Caixa) -> bool:
    return (caixa[0] >= roi[0] and caixa[1] >= roi[1]
            and caixa[0] + caixa[2] <= roi[0] + roi[2] and caixa[1] + caixa[3] <= roi[1] + roi[3])

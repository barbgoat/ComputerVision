"""Leitura em cascata (para no primeiro nível que dá uma leitura válida).

  N1  descodificação direta da imagem inteira, com todos os formatos ativos;
  N2  localizar a ROI do código (gradientes + morfologia), recortar e tentar
      variações: ampliar, rodar, CLAHE, binarizar, aumentar a nitidez.

Nunca completa nem adivinha barras ou dígitos: só devolve o que o zxing-cpp
descodifica (e valida, p. ex. o dígito de controlo do EAN).
"""
from __future__ import annotations

import time
from dataclasses import dataclass

import cv2
import numpy as np
import zxingcpp

from .config import ConfigDescodificacao, ConfigROI

_LINEARES = ("EAN13", "UPCA", "EAN8", "UPCE")   # preferidos quando há vários códigos
Caixa = tuple[int, int, int, int]               # x, y, largura, altura


@dataclass
class Leitura:
    texto: str | None         # código lido (None = nada descodificado)
    formato: str = ""
    tentativa: str = ""       # nível da cascata, p. ex. "N1:direta" ou "N2:roi1:clahe"
    tempo_ms: float = 0.0
    datamatrix: str | None = None
    roi: Caixa | None = None  # ROI encontrada (em coordenadas da imagem original)
    candidatos: int = 0       # n.º de ROI candidatas encontradas no N2


def recortar_roi(imagem: np.ndarray, roi: ConfigROI) -> np.ndarray:
    if roi.largura <= 0 or roi.altura <= 0:
        return imagem
    h, w = imagem.shape[:2]
    x0, y0 = max(0, roi.x), max(0, roi.y)
    x1, y1 = min(w, roi.x + roi.largura), min(h, roi.y + roi.altura)
    return imagem[y0:y1, x0:x1]


def para_cinzento(imagem: np.ndarray) -> np.ndarray:
    if imagem.ndim == 2:
        return imagem
    if imagem.shape[2] == 4:
        return cv2.cvtColor(imagem, cv2.COLOR_BGRA2GRAY)
    return cv2.cvtColor(imagem, cv2.COLOR_BGR2GRAY)


# --- localização da ROI ---------------------------------------------------
def _caixas_de_mapa(mapa: np.ndarray, kernel: tuple[int, int], area_min: float,
                    area_max: float, forma_max: float) -> list[tuple[float, Caixa]]:
    mapa = cv2.GaussianBlur(mapa, (5, 5), 0)
    _, bin_ = cv2.threshold(mapa, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    k = cv2.getStructuringElement(cv2.MORPH_RECT, kernel)
    bin_ = cv2.morphologyEx(bin_, cv2.MORPH_CLOSE, k)
    bin_ = cv2.erode(bin_, None, iterations=2)
    bin_ = cv2.dilate(bin_, None, iterations=2)
    contornos, _ = cv2.findContours(bin_, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    saida = []
    for c in contornos:
        x, y, w, h = cv2.boundingRect(c)
        area = w * h
        if not (area_min <= area <= area_max) or min(w, h) < 12:
            continue
        if max(w / h, h / w) > forma_max:
            continue
        preenchimento = cv2.contourArea(c) / area
        if preenchimento < 0.35:
            continue
        saida.append((area * preenchimento * float(mapa[y:y + h, x:x + w].mean()), (x, y, w, h)))
    return saida


def _iou(a: Caixa, b: Caixa) -> float:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    iw = max(0, min(ax + aw, bx + bw) - max(ax, bx))
    ih = max(0, min(ay + ah, by + bh) - max(ay, by))
    inter = iw * ih
    return inter / (aw * ah + bw * bh - inter) if inter else 0.0


def _coerencia(cinzento: np.ndarray, caixa: Caixa) -> float:
    """Coerência da orientação dos gradientes (0..1). Barras paralelas ≈ 0,9+; texto, bem menos."""
    x, y, w, h = caixa
    c = cinzento[y:y + h, x:x + w].astype(np.float32)
    gx = cv2.Sobel(c, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(c, cv2.CV_32F, 0, 1, ksize=3)
    jxx, jyy, jxy = float((gx * gx).sum()), float((gy * gy).sum()), float((gx * gy).sum())
    return float(np.sqrt((jxx - jyy) ** 2 + 4 * jxy ** 2) / (jxx + jyy + 1e-9))


COERENCIA_1D = 0.85       # barras reais isoladas ≥ 0,90; texto ≤ 0,83 → prova uma ROI 1D (PARCIAL)
COERENCIA_TENTAR = 0.60   # caixa de barras + vizinhança (texto, reflexos) desce a ~0,77: só se tenta ler


_detetor_cv = None


def _caixas_cv(cinzento: np.ndarray) -> list[Caixa]:
    """Candidatas 1D do detetor de código de barras do OpenCV (caixas mais justas e rápido)."""
    global _detetor_cv
    try:
        if _detetor_cv is None:
            _detetor_cv = cv2.barcode.BarcodeDetector()
        ok, pontos = _detetor_cv.detect(cinzento)
    except (AttributeError, cv2.error):
        return []
    if not ok or pontos is None:
        return []
    h, w = cinzento.shape[:2]
    caixas = []
    for p in pontos:
        p = np.asarray(p).reshape(-1, 2)
        x0, y0 = np.floor(p.min(0)).astype(int)
        x1, y1 = np.ceil(p.max(0)).astype(int)
        x0, y0, x1, y1 = max(0, x0), max(0, y0), min(w, x1), min(h, y1)
        if (x1 - x0) * (y1 - y0) >= 0.002 * w * h and min(x1 - x0, y1 - y0) >= 12:
            caixas.append((int(x0), int(y0), int(x1 - x0), int(y1 - y0)))
    return caixas


def localizar(cinzento: np.ndarray, max_candidatos: int = 4, margem: float = 0.15,
              usar_cv: bool = True) -> list[Caixa]:
    """Caixas candidatas a conter um código (1D ou 2D), da mais à menos provável."""
    return [c for c, _ in localizar_tipado(cinzento, max_candidatos, margem, usar_cv)]


def localizar_tipado(cinzento: np.ndarray, max_candidatos: int = 4, margem: float = 0.15,
                     usar_cv: bool = True) -> list[tuple[Caixa, str]]:
    """Como `localizar`, mas devolve também o tipo de cada candidata:

    "1D"   barras muito paralelas (coerência ≥ COERENCIA_1D): prova uma ROI (dá PARCIAL);
    "1D?"  parcialmente paralelas (≥ COERENCIA_TENTAR): só se tenta descodificar — a
           caixa apanhou barras e vizinhança, e o descodificador é quem confirma;
    "2D"   DataMatrix/QR: localização pouco específica, só serve para tentar descodificar.
    """
    h, w = cinzento.shape[:2]
    g = cv2.GaussianBlur(cinzento, (3, 3), 0)
    gx = np.abs(cv2.Scharr(g, cv2.CV_32F, 1, 0))
    gy = np.abs(cv2.Scharr(g, cv2.CV_32F, 0, 1))

    def norm(m: np.ndarray) -> np.ndarray:
        return cv2.normalize(m, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)

    area_img = float(w * h)
    area_min, area_max = area_img * 0.002, area_img * 0.6
    candidatos: list[tuple[float, Caixa, str]] = []
    if usar_cv:   # detetor do OpenCV: caixas mais justas, vão à frente (score muito alto)
        for caixa in _caixas_cv(cinzento):
            coer = _coerencia(cinzento, caixa)
            if coer >= COERENCIA_TENTAR:
                candidatos.append((1e12 + caixa[2] * caixa[3], caixa,
                                   "1D" if coer >= COERENCIA_1D else "1D?"))
    # 1D com barras verticais / horizontais (código rodado) e 2D (gradiente nos dois eixos)
    for mapa, kernel in ((norm(np.clip(gx - gy, 0, None)), (21, 7)),
                         (norm(np.clip(gy - gx, 0, None)), (7, 21))):
        for score, caixa in _caixas_de_mapa(mapa, kernel, area_min, area_max, 6.0):
            coer = _coerencia(cinzento, caixa)
            if coer >= COERENCIA_1D:
                candidatos.append((score, caixa, "1D"))
            elif coer >= COERENCIA_TENTAR:
                candidatos.append((score, caixa, "1D?"))
    for score, caixa in _caixas_de_mapa(norm(np.minimum(gx, gy)), (15, 15), area_min, area_max / 6, 2.0):
        candidatos.append((score, caixa, "2D"))

    escolhidas: list[tuple[Caixa, str]] = []
    for _, caixa, tipo in sorted(candidatos, key=lambda t: t[0], reverse=True):
        if all(_iou(caixa, e) < 0.3 for e, _ in escolhidas):
            escolhidas.append((caixa, tipo))
        if len(escolhidas) >= max_candidatos:
            break

    saida = []
    for (x, y, bw, bh), tipo in escolhidas:
        mx, my = int(bw * margem), int(bh * margem)
        x0, y0 = max(0, x - mx), max(0, y - my)
        x1, y1 = min(w, x + bw + mx), min(h, y + bh + my)
        saida.append(((x0, y0, x1 - x0, y1 - y0), tipo))
    return saida


# --- descodificador -------------------------------------------------------
class Descodificador:
    def __init__(self, cfg: ConfigDescodificacao, roi: ConfigROI):
        self.cfg = cfg
        self.roi = roi
        self.formatos = zxingcpp.barcode_formats_from_str(cfg.formatos)
        self._clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(4, 4))

    def _decodificar(self, imagem: np.ndarray):
        return zxingcpp.read_barcodes(
            np.ascontiguousarray(imagem), formats=self.formatos, try_rotate=self.cfg.tentar_rodar)

    def _variantes(self, crop: np.ndarray):
        """(nome, imagem) por ordem de custo crescente."""
        yield "orig", crop
        for f in self.cfg.ampliar:
            yield f"x{f:g}", cv2.resize(crop, None, fx=f, fy=f, interpolation=cv2.INTER_CUBIC)
        yield "clahe", self._clahe.apply(crop)
        yield "otsu", cv2.threshold(crop, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]
        bloco = max(15, (min(crop.shape[:2]) // 4) | 1)
        yield "adaptativo", cv2.adaptiveThreshold(
            crop, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, bloco, 8)
        desfocada = cv2.GaussianBlur(crop, (0, 0), 2.0)
        nitido = cv2.addWeighted(crop, 2.0, desfocada, -1.0, 0)
        yield "nitidez", nitido
        if self.cfg.ampliar:
            f = self.cfg.ampliar[0]
            grande = cv2.resize(crop, None, fx=f, fy=f, interpolation=cv2.INTER_CUBIC)
            yield f"x{f:g}+clahe", self._clahe.apply(grande)
            yield f"x{f:g}+nitidez", cv2.addWeighted(grande, 2.0, cv2.GaussianBlur(grande, (0, 0), 2.0), -1.0, 0)
        if self.cfg.tentar_rodar:
            for nome, cod in (("rot90", cv2.ROTATE_90_CLOCKWISE), ("rot180", cv2.ROTATE_180),
                              ("rot270", cv2.ROTATE_90_COUNTERCLOCKWISE)):
                yield nome, cv2.rotate(crop, cod)

    @staticmethod
    def _preencher(leitura: Leitura, codigos, tentativa: str) -> None:
        escolhido = next((c for c in codigos if c.format.name in _LINEARES), codigos[0])
        leitura.texto, leitura.formato, leitura.tentativa = escolhido.text, escolhido.format.name, tentativa
        leitura.datamatrix = next(
            (c.text for c in codigos if c.format.name == "DataMatrix" and c is not escolhido), None)

    def ler(self, imagem: np.ndarray) -> Leitura:
        t0 = time.perf_counter()
        leitura = Leitura(None)
        cinzento = para_cinzento(recortar_roi(imagem, self.roi))
        ox = max(0, self.roi.x) if self.roi.largura > 0 and self.roi.altura > 0 else 0
        oy = max(0, self.roi.y) if self.roi.largura > 0 and self.roi.altura > 0 else 0

        # N1: imagem inteira, todos os formatos
        codigos = self._decodificar(cinzento)
        if codigos:
            self._preencher(leitura, codigos, "N1:direta")
        elif self.cfg.localizar_roi:
            # N2: localizar a ROI e tentar variações
            tipadas = localizar_tipado(cinzento, self.cfg.max_candidatos, self.cfg.margem,
                                       self.cfg.usar_cv_barcode)
            caixas = [c for c, _ in tipadas]
            leitura.candidatos = len(caixas)
            for i, (x, y, w, h) in enumerate(caixas, start=1):
                crop = np.ascontiguousarray(cinzento[y:y + h, x:x + w])
                for nome, variante in self._variantes(crop):
                    codigos = self._decodificar(variante)
                    if codigos:
                        self._preencher(leitura, codigos, f"N2:roi{i}:{nome}")
                        leitura.roi = (x + ox, y + oy, w, h)
                        break
                if leitura.texto is not None:
                    break
            # PARCIAL só com uma ROI 1D (barras paralelas); candidatas 2D não provam um código
            primeira_1d = next((c for c, tipo in tipadas if tipo == "1D"), None)
            if leitura.texto is None and primeira_1d is not None:
                x, y, w, h = primeira_1d
                leitura.roi = (x + ox, y + oy, w, h)

        leitura.tempo_ms = (time.perf_counter() - t0) * 1000
        return leitura

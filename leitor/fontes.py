"""Fontes de imagem com a mesma interface: iterar devolve (nome, imagem)."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Iterator, Protocol

import cv2
import numpy as np

from .config import ConfigCamara

EXTENSOES = {".bmp", ".png", ".jpg", ".jpeg", ".tif", ".tiff"}


class Fonte(Protocol):
    def __enter__(self) -> "Fonte": ...
    def __exit__(self, *exc) -> None: ...
    def __iter__(self) -> Iterator[tuple[str, np.ndarray]]: ...


class FontePasta:
    """Percorre as imagens de uma pasta por ordem alfabética."""

    def __init__(self, pasta: str | Path):
        self.pasta = Path(pasta)

    def __enter__(self) -> "FontePasta":
        if not self.pasta.is_dir():
            raise FileNotFoundError(f"Pasta não encontrada: {self.pasta}")
        return self

    def __exit__(self, *exc) -> None:
        pass

    def ficheiros(self) -> list[Path]:
        return sorted(p for p in self.pasta.iterdir() if p.suffix.lower() in EXTENSOES)

    def __iter__(self) -> Iterator[tuple[str, np.ndarray]]:
        for p in self.ficheiros():
            imagem = cv2.imread(str(p), cv2.IMREAD_UNCHANGED)
            if imagem is None:
                continue
            yield p.name, imagem


class FonteCamara:
    """Adquire imagens da câmara indefinidamente (ou `n` imagens)."""

    def __init__(self, cfg: ConfigCamara, n: int | None = None):
        from .camara import Camara  # importação tardia: pypylon só é necessário aqui

        self.camara = Camara(cfg)
        self.n = n

    def __enter__(self) -> "FonteCamara":
        self.camara.abrir()
        return self

    def __exit__(self, *exc) -> None:
        self.camara.fechar()

    def __iter__(self) -> Iterator[tuple[str, np.ndarray]]:
        i = 0
        while self.n is None or i < self.n:
            imagem = self.camara.adquirir()
            nome = datetime.now().strftime("Image__%Y-%m-%d__%H-%M-%S-%f")[:-3] + ".bmp"
            yield nome, imagem
            i += 1

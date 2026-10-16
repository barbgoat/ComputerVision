"""Log CSV de todas as deteções + cópia das imagens que não foram LIDO ou deram NOK."""
from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np

from .resultado import Deteccao, Estado
from .validador import Resultado

CABECALHO = ["data_hora", "imagem", "resultado", "codigo", "formato", "nivel",
             "produto", "esperado", "conformidade", "roi", "tempo_ms"]


class Registo:
    def __init__(self, pasta: Path, guardar_nok: bool = True):
        self.pasta = Path(pasta)
        self.pasta_nok = self.pasta / "nok"
        self.guardar_nok = guardar_nok
        self.pasta.mkdir(parents=True, exist_ok=True)
        self.ficheiro = self.pasta / f"log_{datetime.now():%Y-%m-%d}.csv"
        novo = not self.ficheiro.exists()
        self._f = open(self.ficheiro, "a", newline="", encoding="utf-8")
        self._csv = csv.writer(self._f, delimiter=";")
        if novo:
            self._csv.writerow(CABECALHO)

    def registar(self, nome: str, imagem: np.ndarray, det: Deteccao, esperado: str = "") -> None:
        self._csv.writerow([
            datetime.now().isoformat(timespec="milliseconds"), nome, det.estado.value,
            det.codigo or "", det.formato, det.nivel, det.produto or "", esperado,
            det.conformidade.value if det.conformidade else "",
            "" if det.roi is None else ",".join(map(str, det.roi)),
            f"{det.tempo_ms:.1f}",
        ])
        self._f.flush()
        guardar = det.estado is not Estado.LIDO or det.conformidade is Resultado.NOK
        if self.guardar_nok and guardar:
            self.pasta_nok.mkdir(exist_ok=True)
            motivo = det.estado.value if det.estado is not Estado.LIDO else "NOK"
            cv2.imwrite(str(self.pasta_nok / f"{motivo}__{Path(nome).stem}.bmp"), imagem)

    def fechar(self) -> None:
        self._f.close()

    def __enter__(self) -> "Registo":
        return self

    def __exit__(self, *exc) -> None:
        self.fechar()

"""Grava imagens da câmara para uma pasta (por omissão img/).

    python ferramentas/capturar.py --listar
    python ferramentas/capturar.py --n 10 --intervalo 1.0

Atenção: só uma aplicação pode usar a câmara de cada vez — feche o MCM primeiro.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import cv2  # noqa: E402

from leitor import camara, config  # noqa: E402
from leitor.fontes import FonteCamara  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="Gravar imagens da câmara")
    ap.add_argument("--n", type=int, default=1, help="n.º de imagens")
    ap.add_argument("--intervalo", type=float, default=0.0, help="segundos entre imagens")
    ap.add_argument("--destino", default=str(config.RAIZ / "img"))
    ap.add_argument("--listar", action="store_true", help="listar câmaras ligadas e sair (não abre a câmara)")
    ap.add_argument("--config", default=str(config.CONFIG_PADRAO))
    args = ap.parse_args()

    if args.listar:
        for serial, modelo, ip in camara.listar():
            print(f"{serial}\t{modelo}\t{ip}")
        return 0

    cfg = config.carregar(args.config)
    destino = Path(args.destino)
    destino.mkdir(parents=True, exist_ok=True)

    try:
        with FonteCamara(cfg.camara, args.n) as fonte:
            for nome, imagem in fonte:
                cv2.imwrite(str(destino / nome), imagem)
                print(destino / nome)
                if args.intervalo:
                    time.sleep(args.intervalo)
    except camara.ErroCamara as e:
        print(f"ERRO: {e}")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

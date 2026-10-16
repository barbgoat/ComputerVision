"""Vista ao vivo da câmara, com ROI desenhável e leitura em tempo real.

    python ferramentas/ver.py

Teclas:
  r = desenhar a ROI com o rato (arrastar; ENTER confirma; c cancela)
  x = limpar a ROI (voltar à imagem inteira)
  g = gravar a ROI atual no config.toml
  d = ligar/desligar leitura       s = gravar imagem em img_camara/
  q ou Esc = sair (repõe os parâmetros da câmara)
Só uma aplicação usa a câmara de cada vez.
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import cv2  # noqa: E402

from leitor import config  # noqa: E402
from leitor.camara import Camara, ErroCamara  # noqa: E402
from leitor.descodificador import Descodificador, localizar_tipado, para_cinzento  # noqa: E402
from leitor.produtos import Produtos  # noqa: E402
from leitor.resultado import Estado, classificar  # noqa: E402

JANELA = "Camara"
AJUDA = "r=ROI  x=limpar  g=gravar ROI  a=auto-ROI  d=ler  s=foto  q=sair"


def main() -> int:
    ap = argparse.ArgumentParser(description="Vista ao vivo da câmara")
    ap.add_argument("--destino", default=str(config.RAIZ / "img_camara"))
    ap.add_argument("--config", default=str(config.CONFIG_PADRAO))
    args = ap.parse_args()

    cfg = config.carregar(args.config)
    produtos = Produtos.carregar(cfg.ficheiro_produtos)
    desc = Descodificador(cfg.descodificacao, cfg.roi)   # partilha o objeto cfg.roi
    destino = Path(args.destino)
    ler, det, msg, auto = True, None, "", False

    try:
        with Camara(cfg.camara) as cam:
            for n, imagem in enumerate(cam.fluxo()):
                if ler and n % 3 == 0:          # ~1 em 3 imagens, para a vista não travar
                    det = classificar(desc.ler(imagem), produtos, cfg.validacao.codigo_esperado)

                vista = cv2.cvtColor(para_cinzento(imagem), cv2.COLOR_GRAY2BGR)
                r = cfg.roi
                if r.largura > 0 and r.altura > 0:
                    cv2.rectangle(vista, (r.x, r.y), (r.x + r.largura, r.y + r.altura), (0, 255, 255), 2)
                if auto:                                  # candidatas da ROI automática
                    for (cx, cy, cw, ch), tipo in localizar_tipado(
                            para_cinzento(imagem), cfg.descodificacao.max_candidatos, 0.0):
                        cor_c = {"1D": (0, 255, 0), "1D?": (0, 200, 255)}.get(tipo, (255, 160, 0))
                        cv2.rectangle(vista, (cx, cy), (cx + cw, cy + ch), cor_c, 2)
                        cv2.putText(vista, tipo, (cx + 4, cy + 18), cv2.FONT_HERSHEY_SIMPLEX, 0.6, cor_c, 2)
                if ler and det is not None:
                    cor = (0, 200, 0) if det.estado is Estado.LIDO else (0, 0, 255)
                    texto = f"{det.estado.value}  {det.codigo or ''}  {det.produto or ''}  {det.tempo_ms:.0f} ms"
                    if det.conformidade:
                        texto += f"  {det.conformidade.value}"
                    cv2.putText(vista, texto, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, cor, 2)
                cv2.putText(vista, msg or AJUDA, (10, vista.shape[0] - 12),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1)
                cv2.imshow(JANELA, vista)

                tecla = cv2.waitKey(1) & 0xFF
                if tecla in (ord("q"), 27):
                    break
                if tecla == ord("d"):
                    ler, det = not ler, None
                elif tecla == ord("a"):
                    auto = not auto
                    msg = "ROI automática: " + ("ligada" if auto else "desligada")
                elif tecla == ord("x"):
                    r.x = r.y = r.largura = r.altura = 0
                    msg = "ROI limpa (imagem inteira); g para gravar"
                elif tecla == ord("r"):
                    # imagem parada; arrastar o retângulo, ENTER confirma, c cancela
                    x, y, w, h = cv2.selectROI(JANELA, imagem, showCrosshair=False, fromCenter=False)
                    if w > 0 and h > 0:
                        r.x, r.y, r.largura, r.altura = int(x), int(y), int(w), int(h)
                        msg = f"ROI x={x} y={y} {w}x{h}; g para gravar no config.toml"
                    else:
                        msg = "ROI cancelada"
                    det = None
                elif tecla == ord("g"):
                    config.gravar_roi(args.config, r)
                    msg = "ROI gravada no config.toml"
                    print(msg, (r.x, r.y, r.largura, r.altura))
                elif tecla == ord("s"):
                    destino.mkdir(parents=True, exist_ok=True)
                    nome = destino / (datetime.now().strftime("Image__%Y-%m-%d__%H-%M-%S-%f")[:-3] + ".bmp")
                    cv2.imwrite(str(nome), imagem)       # imagem original, sem desenhos
                    msg = f"gravada: {nome.name}"
                    print("gravada:", nome)
                if cv2.getWindowProperty(JANELA, cv2.WND_PROP_VISIBLE) < 1:
                    break
    except ErroCamara as e:
        print(f"ERRO: {e}")
        return 2
    except KeyboardInterrupt:
        pass
    finally:
        cv2.destroyAllWindows()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

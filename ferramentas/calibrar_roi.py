"""Calibra a ROI fixa a partir de imagens reais.

    python ferramentas/calibrar_roi.py                       # analisa img_camara/, só mostra
    python ferramentas/calibrar_roi.py --formatos EAN13,UPCA --margem 0.3
    python ferramentas/calibrar_roi.py --guardar-vista resultados/calibracao
    python ferramentas/calibrar_roi.py --aplicar             # grava a ROI proposta no config.toml

Dica: capture (tecla 's' no ver.py) 15-30 imagens com o produto nas posições reais da linha.
Se a ROI proposta for muito maior do que o código, as posições variam demasiado: reveja o
posicionamento mecânico ou aceite a ROI maior (mais lenta, mais falsos candidatos).
"""
from __future__ import annotations

import argparse
import dataclasses
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import cv2  # noqa: E402

from leitor import calibracao, config  # noqa: E402
from leitor.descodificador import Descodificador  # noqa: E402
from leitor.fontes import FontePasta  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="Calibrar a ROI fixa")
    ap.add_argument("--pasta", default=str(config.RAIZ / "img_camara"))
    ap.add_argument("--formatos", default="EAN13,UPCA",
                    help="formatos a considerar (nomes do zxing, separados por vírgulas) ou 'todos'")
    ap.add_argument("--margem", type=float, default=0.25, help="folga à volta do envelope (fração)")
    ap.add_argument("--guardar-vista", default=None, help="pasta onde gravar imagens com as caixas e a ROI")
    ap.add_argument("--aplicar", action="store_true", help="gravar a ROI proposta no config.toml")
    ap.add_argument("--config", default=str(config.CONFIG_PADRAO))
    args = ap.parse_args()

    cfg = config.carregar(args.config)
    formatos = None if args.formatos.lower() == "todos" else {f.strip() for f in args.formatos.split(",")}
    desc = Descodificador(cfg.descodificacao, config.ConfigROI())     # sem ROI fixa

    imagens: dict[str, tuple[int, int]] = {}
    observacoes: list[calibracao.Observacao] = []
    sem_leitura: list[str] = []
    with FontePasta(args.pasta) as fonte:
        cache = {}
        for nome, imagem in fonte:
            h, w = imagem.shape[:2]
            imagens[nome] = (w, h)
            cache[nome] = imagem
            obs = calibracao.observar(nome, imagem, desc, formatos)
            observacoes += obs
            if not obs:
                sem_leitura.append(nome)

    if not observacoes:
        print("Nenhum código dos formatos pedidos foi lido: não há dados para calibrar.")
        return 1

    larguras = {s for s in imagens.values()}
    if len(larguras) > 1:
        print(f"AVISO: imagens com tamanhos diferentes {sorted(larguras)}; uso o maior.")
    W = max(w for w, _ in imagens.values())
    H = max(h for _, h in imagens.values())

    print(f"Imagens: {len(imagens)}  com código: {len(imagens) - len(sem_leitura)}  sem leitura: {len(sem_leitura)}")
    for n in sem_leitura:
        print(f"   sem leitura: {n}")

    grupos = calibracao.agrupar(observacoes)
    print("\nPor código lido:")
    for codigo, obs in grupos.items():
        caixas = [o.caixa for o in obs]
        env = calibracao.envolvente(caixas, args.margem, W, H)
        aprox = sum(not o.exata for o in obs)
        media_a = sum(c[2] * c[3] for c in caixas) / len(caixas)
        print(f"  {codigo:16s} [{obs[0].formato}]  {len(obs)} imagens"
              + (f" ({aprox} com posição aproximada)" if aprox else "")
              + f"  ROI x={env[0]} y={env[1]} {env[2]}x{env[3]}"
              + f"  ({env[2] * env[3] / media_a:.1f}× a área média do código)")

    todas = [o.caixa for o in observacoes]
    roi = calibracao.envolvente(todas, args.margem, W, H)
    fracao = roi[2] * roi[3] / (W * H)
    print(f"\nROI proposta (união de todos os códigos): x={roi[0]} y={roi[1]} largura={roi[2]} altura={roi[3]}"
          f"  = {100 * fracao:.0f}% da imagem")
    if fracao > 0.6:
        print("AVISO: a ROI ocupa mais de 60 % da imagem — as posições variam muito; "
              "a ROI fixa traz pouco ganho.")

    # Verificação: dentro da ROI, o N1 sozinho lê cada imagem?
    desc_roi = Descodificador(dataclasses.replace(cfg.descodificacao, localizar_roi=False),
                              config.ConfigROI(*roi))
    lidos = fora = 0
    tempos = []
    for nome, imagem in cache.items():
        esperados = {chave for chave, obs in grupos.items() if any(o.imagem == nome for o in obs)}
        if not esperados:
            continue
        leitura = desc_roi.ler(imagem)
        tempos.append(leitura.tempo_ms)
        if leitura.texto is not None and calibracao.chave(leitura.texto) in esperados:
            lidos += 1
        else:
            fora += 1
    n = lidos + fora
    print(f"Verificação com a ROI (só N1, sem N2): {lidos}/{n} imagens lidas"
          + (f", {sum(tempos) / len(tempos):.0f} ms em média" if tempos else ""))

    if args.guardar_vista:
        destino = Path(args.guardar_vista)
        destino.mkdir(parents=True, exist_ok=True)
        for nome, imagem in cache.items():
            vista = cv2.cvtColor(imagem, cv2.COLOR_GRAY2BGR) if imagem.ndim == 2 else imagem.copy()
            cv2.rectangle(vista, (roi[0], roi[1]), (roi[0] + roi[2], roi[1] + roi[3]), (0, 255, 255), 3)
            for o in observacoes:
                if o.imagem == nome:
                    x, y, w, h = o.caixa
                    cv2.rectangle(vista, (x, y), (x + w, y + h), (0, 200, 0) if o.exata else (0, 140, 255), 2)
            cv2.imwrite(str(destino / f"{Path(nome).stem}.png"), vista)
        print(f"Vistas em {destino}  (amarelo=ROI, verde=código, laranja=posição aproximada)")

    if args.aplicar:
        antiga = cfg.roi
        config.gravar_roi(args.config, config.ConfigROI(*roi))
        print(f"\nROI gravada em {args.config}  (antes: x={antiga.x} y={antiga.y} "
              f"{antiga.largura}x{antiga.altura})")
    else:
        print("\n(nada gravado; use --aplicar para escrever no config.toml)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

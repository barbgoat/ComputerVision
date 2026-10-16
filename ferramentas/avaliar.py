"""Taxa de leitura, nível da cascata e tempos sobre a pasta img/.

    python ferramentas/avaliar.py --detalhe
    python ferramentas/avaliar.py --gerar-esperados   # escreve img/esperados.csv a partir das leituras
    python ferramentas/avaliar.py --guardar-roi resultados/roi   # recortes das ROI (PARCIAL/LIDO N2)
"""
from __future__ import annotations

import argparse
import csv
import statistics
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import cv2  # noqa: E402

from leitor import config  # noqa: E402
from leitor.descodificador import Descodificador  # noqa: E402
from leitor.fontes import FontePasta  # noqa: E402
from leitor.produtos import Produtos  # noqa: E402
from leitor.resultado import Estado, classificar  # noqa: E402
from leitor.validador import Resultado, normalizar  # noqa: E402


def ler_esperados(caminho: Path) -> dict[str, str]:
    if not caminho.exists():
        return {}
    with open(caminho, newline="", encoding="utf-8-sig") as f:
        return {l["imagem"]: l["esperado"].strip() for l in csv.DictReader(f, delimiter=";")}


def main() -> int:
    ap = argparse.ArgumentParser(description="Avaliar o descodificador sobre uma pasta")
    ap.add_argument("--pasta", default=str(config.RAIZ / "img"))
    ap.add_argument("--esperados", default=None, help="CSV imagem;esperado (por omissão <pasta>/esperados.csv)")
    ap.add_argument("--gerar-esperados", action="store_true",
                    help="escrever o CSV de esperados a partir das leituras (EAN-13 normalizado)")
    ap.add_argument("--guardar-roi", default=None, help="pasta onde gravar a imagem com a ROI desenhada")
    ap.add_argument("--detalhe", action="store_true", help="mostrar uma linha por imagem")
    ap.add_argument("--config", default=str(config.CONFIG_PADRAO))
    args = ap.parse_args()

    cfg = config.carregar(args.config)
    pasta = Path(args.pasta)
    caminho_csv = Path(args.esperados) if args.esperados else pasta / "esperados.csv"
    esperados = {} if args.gerar_esperados else ler_esperados(caminho_csv)
    desc = Descodificador(cfg.descodificacao, cfg.roi)
    produtos = Produtos.carregar(cfg.ficheiro_produtos)

    tempos: list[float] = []
    estados = Counter()
    niveis = Counter()
    conformes = Counter()
    gerados: list[tuple[str, str]] = []
    destino_roi = Path(args.guardar_roi) if args.guardar_roi else None
    if destino_roi:
        destino_roi.mkdir(parents=True, exist_ok=True)

    with FontePasta(pasta) as fonte:
        for nome, imagem in fonte:
            esperado = esperados.get(nome) or cfg.validacao.codigo_esperado
            leitura = desc.ler(imagem)
            det = classificar(leitura, produtos, esperado)
            tempos.append(det.tempo_ms)
            estados[det.estado] += 1
            if det.estado is Estado.LIDO:
                niveis[det.nivel.split(":")[0] + ":" + (det.nivel.split(":")[-1] if det.nivel.startswith("N2") else "direta")] += 1
            if det.conformidade:
                conformes[det.conformidade] += 1
            gerados.append((nome, (normalizar(det.codigo) or det.codigo or "") if det.estado is Estado.LIDO else ""))
            if args.detalhe:
                extra = f"{det.codigo} [{det.formato}] {det.produto}" if det.codigo else \
                    (f"roi={det.roi} cand={leitura.candidatos}" if det.roi else "")
                conf = f" {det.conformidade.value}" if det.conformidade else ""
                print(f"{nome:36s} {det.estado.value:15s} {det.nivel:22s} {det.tempo_ms:6.1f} ms  {extra}{conf}")
            if destino_roi and det.roi:
                vista = cv2.cvtColor(imagem, cv2.COLOR_GRAY2BGR) if imagem.ndim == 2 else imagem.copy()
                x, y, w, h = det.roi
                cor = (0, 200, 0) if det.estado is Estado.LIDO else (0, 0, 255)
                cv2.rectangle(vista, (x, y), (x + w, y + h), cor, 3)
                cv2.imwrite(str(destino_roi / f"{det.estado.value}__{Path(nome).stem}.png"), vista)

    total = len(tempos)
    if not total:
        print("Nenhuma imagem encontrada.")
        return 1

    if args.gerar_esperados:
        with open(caminho_csv, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f, delimiter=";")
            w.writerow(["imagem", "esperado"])
            w.writerows(gerados)
        print(f"Escrito {caminho_csv} ({sum(1 for _, e in gerados if e)}/{total} preenchidos; "
              "as vazias não foram lidas — rever à mão)")

    print(f"\nImagens:  {total}")
    print("Estados:  " + "  ".join(f"{e.value}={estados[e]}" for e in Estado))
    print("Nível:    " + ("  ".join(f"{k}={v}" for k, v in sorted(niveis.items())) or "-"))
    if conformes:
        print("Esperado: " + "  ".join(f"{r.value}={conformes[r]}" for r in (Resultado.OK, Resultado.NOK)))
    q = statistics.quantiles(tempos, n=20) if total > 1 else tempos * 19
    print(f"Tempo ms: média={statistics.mean(tempos):.1f}  mediana={statistics.median(tempos):.1f}  "
          f"p95={q[-1]:.1f}  máx={max(tempos):.1f}")
    return 0 if estados[Estado.LIDO] == total else 1


if __name__ == "__main__":
    raise SystemExit(main())

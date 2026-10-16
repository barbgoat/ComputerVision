"""Ponto de entrada: deteta, lê e identifica códigos de barras (pasta ou câmara).

    python main.py --fonte pasta
    python main.py --fonte camara --n 10
"""
from __future__ import annotations

import argparse
from pathlib import Path

from leitor import config
from leitor.camara import ErroCamara
from leitor.descodificador import Descodificador
from leitor.fontes import FonteCamara, FontePasta
from leitor.produtos import Produtos
from leitor.registo import Registo
from leitor.resultado import Estado, classificar
from leitor.validador import Resultado


def main() -> int:
    ap = argparse.ArgumentParser(description="Leitor de códigos de barras")
    ap.add_argument("--fonte", choices=["pasta", "camara"], required=True)
    ap.add_argument("--pasta", default=str(config.RAIZ / "img"), help="pasta de imagens (fonte=pasta)")
    ap.add_argument("--n", type=int, default=None, help="n.º de imagens a adquirir (fonte=camara)")
    ap.add_argument("--esperado", default=None, help="sobrepõe validacao.codigo_esperado ('' = sem esperado)")
    ap.add_argument("--config", default=str(config.CONFIG_PADRAO))
    args = ap.parse_args()

    cfg = config.carregar(args.config)
    if cfg.plc.ativo:
        ap.error("plc.ativo = true: a ligação ao PLC ainda não está implementada (etapa 5).")
    esperado = cfg.validacao.codigo_esperado if args.esperado is None else args.esperado

    produtos = Produtos.carregar(cfg.ficheiro_produtos)
    fonte = FontePasta(Path(args.pasta)) if args.fonte == "pasta" else FonteCamara(cfg.camara, args.n)
    desc = Descodificador(cfg.descodificacao, cfg.roi)
    contagem = {e: 0 for e in Estado}
    conformes = {r: 0 for r in (Resultado.OK, Resultado.NOK)}

    try:
        with fonte, Registo(cfg.pasta_resultados, cfg.registo.guardar_nok) as reg:
            for nome, imagem in fonte:
                det = classificar(desc.ler(imagem), produtos, esperado)
                reg.registar(nome, imagem, det, esperado)
                contagem[det.estado] += 1
                if det.conformidade:
                    conformes[det.conformidade] += 1
                extra = f"{det.codigo}  [{det.formato}]  {det.produto}" if det.codigo else ""
                conf = f"  {det.conformidade.value}" if det.conformidade else ""
                print(f"{nome:40s} {det.estado.value:15s} {extra}{conf}  {det.tempo_ms:.0f} ms")
    except ErroCamara as e:
        print(f"ERRO: {e}")
        return 2
    except KeyboardInterrupt:
        pass

    print("\n" + "  ".join(f"{e.value}={n}" for e, n in contagem.items())
          + ("  |  " + "  ".join(f"{r.value}={n}" for r, n in conformes.items()) if esperado else ""))
    return 0 if contagem[Estado.LIDO] == sum(contagem.values()) and not conformes[Resultado.NOK] else 1


if __name__ == "__main__":
    raise SystemExit(main())

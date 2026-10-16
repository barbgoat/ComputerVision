"""Leitura do config.toml para dataclasses."""
from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
CONFIG_PADRAO = RAIZ / "config" / "config.toml"


@dataclass
class ConfigCamara:
    serial: str = ""
    ip: str = ""
    exposicao_us: float = 9000.0
    ganho_raw: int = -1
    timeout_ms: int = 2000


@dataclass
class ConfigROI:
    x: int = 0  # (ordem: x, y, largura, altura)
    y: int = 0
    largura: int = 0
    altura: int = 0


@dataclass
class ConfigDescodificacao:
    formatos: str = "All"
    tentar_rodar: bool = True
    localizar_roi: bool = True
    max_candidatos: int = 4
    margem: float = 0.15
    usar_cv_barcode: bool = True
    ampliar: list[float] = field(default_factory=lambda: [2.0, 3.0])


@dataclass
class ConfigValidacao:
    codigo_esperado: str = ""


@dataclass
class ConfigRegisto:
    pasta: str = "resultados"
    guardar_nok: bool = True


@dataclass
class ConfigPLC:
    ativo: bool = False
    ip: str = ""
    porta: int = 502
    unit_id: int = 1


@dataclass
class Config:
    camara: ConfigCamara = field(default_factory=ConfigCamara)
    roi: ConfigROI = field(default_factory=ConfigROI)
    descodificacao: ConfigDescodificacao = field(default_factory=ConfigDescodificacao)
    validacao: ConfigValidacao = field(default_factory=ConfigValidacao)
    registo: ConfigRegisto = field(default_factory=ConfigRegisto)
    plc: ConfigPLC = field(default_factory=ConfigPLC)

    produtos: str = "produtos.csv"

    @property
    def ficheiro_produtos(self) -> Path:
        p = Path(self.produtos)
        return p if p.is_absolute() else RAIZ / p

    @property
    def pasta_resultados(self) -> Path:
        p = Path(self.registo.pasta)
        return p if p.is_absolute() else RAIZ / p


def gravar_roi(caminho: str | Path, roi: ConfigROI) -> None:
    """Atualiza só as 4 linhas da secção [roi] do config.toml (mantém comentários)."""
    import re

    caminho = Path(caminho)
    texto = caminho.read_text(encoding="utf-8")
    m = re.search(r"(?ms)^\[roi\]\s*\n(.*?)(?=^\[|\Z)", texto)
    if m is None:
        raise RuntimeError("Secção [roi] não encontrada no config.toml.")
    bloco = m.group(1)
    for chave in ("x", "y", "largura", "altura"):
        bloco, n = re.subn(rf"(?m)^{chave}\s*=\s*-?\d+", f"{chave} = {getattr(roi, chave)}", bloco)
        if n != 1:
            raise RuntimeError(f"Chave '{chave}' não encontrada em [roi].")
    caminho.write_text(texto[:m.start(1)] + bloco + texto[m.end(1):], encoding="utf-8")


def carregar(caminho: str | Path = CONFIG_PADRAO) -> Config:
    with open(caminho, "rb") as f:
        dados = tomllib.load(f)
    return Config(
        camara=ConfigCamara(**dados.get("camara", {})),
        roi=ConfigROI(**dados.get("roi", {})),
        descodificacao=ConfigDescodificacao(**dados.get("descodificacao", {})),
        validacao=ConfigValidacao(**dados.get("validacao", {})),
        registo=ConfigRegisto(**dados.get("registo", {})),
        plc=ConfigPLC(**dados.get("plc", {})),
        produtos=dados.get("produtos", {}).get("ficheiro", "produtos.csv"),
    )

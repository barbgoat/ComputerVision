"""Câmara Basler (acA1300-30gm, modelo legacy) via pypylon.

Segurança (câmara partilhada com o MCM):
  - abre pelo S/N; se estiver em uso falha com mensagem clara;
  - guarda os parâmetros originais e repõe-nos à saída (fechar() é chamado em finally);
  - NUNCA grava nem carrega User Sets.
"""
from __future__ import annotations

import numpy as np
from pypylon import genicam, pylon

from .config import ConfigCamara


class ErroCamara(RuntimeError):
    pass


def listar() -> list[tuple[str, str, str]]:
    """Devolve [(serial, modelo, ip), ...] sem abrir nenhuma câmara."""
    tlf = pylon.TlFactory.GetInstance()
    return [(d.GetSerialNumber(), d.GetModelName(), d.GetIpAddress()) for d in tlf.EnumerateDevices()]


class Camara:
    # nome do parâmetro (modelo legacy) → atributo da configuração
    _PARAMETROS = {"ExposureTimeAbs": "exposicao_us", "GainRaw": "ganho_raw"}

    def __init__(self, cfg: ConfigCamara):
        if not cfg.serial:
            raise ErroCamara("Defina camara.serial no config.toml (a câmara abre-se sempre pelo S/N).")
        self.cfg = cfg
        self._cam: pylon.InstantCamera | None = None
        self._originais: dict[str, float] = {}

    # --- ciclo de vida -------------------------------------------------
    def abrir(self) -> None:
        tlf = pylon.TlFactory.GetInstance()
        info = next((d for d in tlf.EnumerateDevices() if d.GetSerialNumber() == self.cfg.serial), None)
        if info is None:
            raise ErroCamara(f"Câmara S/N {self.cfg.serial} não encontrada na rede.")

        cam = pylon.InstantCamera(tlf.CreateDevice(info))
        try:
            cam.Open()
        except genicam.GenericException as e:
            raise ErroCamara(
                f"Não foi possível abrir a câmara S/N {self.cfg.serial}. "
                f"Provavelmente está em uso por outra aplicação (MCM). Feche-a e tente de novo. ({e})"
            ) from e
        self._cam = cam
        try:
            self._aplicar()
        except Exception:
            self.fechar()
            raise

    def fechar(self) -> None:
        """Repõe os parâmetros originais e fecha. Seguro de chamar várias vezes."""
        cam, self._cam = self._cam, None
        if cam is None:
            return
        try:
            if cam.IsOpen():
                if cam.IsGrabbing():
                    cam.StopGrabbing()
                for nome, valor in self._originais.items():
                    try:
                        getattr(cam, nome).Value = valor
                    except genicam.GenericException:
                        pass
        finally:
            self._originais.clear()
            if cam.IsOpen():
                cam.Close()

    def __enter__(self) -> "Camara":
        self.abrir()
        return self

    def __exit__(self, *exc) -> None:
        self.fechar()

    # --- parâmetros ----------------------------------------------------
    def _aplicar(self) -> None:
        cam = self._exigir()
        for nome, chave in self._PARAMETROS.items():
            valor = getattr(self.cfg, chave)
            if chave == "ganho_raw" and valor < 0:
                continue
            no = getattr(cam, nome)
            self._originais[nome] = no.Value          # guardar ANTES de alterar
            no.Value = type(no.Value)(valor)

    # --- aquisição -----------------------------------------------------
    def adquirir(self) -> np.ndarray:
        cam = self._exigir()
        resultado = cam.GrabOne(self.cfg.timeout_ms)
        try:
            if not resultado.GrabSucceeded():
                raise ErroCamara(f"Falha na aquisição: {resultado.ErrorDescription}")
            return resultado.GetArray().copy()
        finally:
            resultado.Release()

    def fluxo(self):
        """Gera imagens continuamente (só a mais recente; descarta atrasadas).

        Pára a aquisição ao sair do gerador.
        """
        cam = self._exigir()
        cam.StartGrabbing(pylon.GrabStrategy_LatestImageOnly)
        try:
            while cam.IsGrabbing():
                try:
                    r = cam.RetrieveResult(self.cfg.timeout_ms, pylon.TimeoutHandling_ThrowException)
                except genicam.TimeoutException as e:
                    raise ErroCamara("Sem imagens da câmara (timeout).") from e
                try:
                    if r.GrabSucceeded():
                        yield r.GetArray().copy()
                finally:
                    r.Release()
        finally:
            if cam.IsGrabbing():
                cam.StopGrabbing()

    def _exigir(self) -> pylon.InstantCamera:
        if self._cam is None:
            raise ErroCamara("Câmara não está aberta.")
        return self._cam

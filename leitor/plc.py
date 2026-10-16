"""Etapa 5: comunicação com o PLC Delta DVP-12SE11T (Modbus TCP) — por implementar.

Regras quando for implementado (plc.ativo = false até lá; só leitura até aprovação):
NUNCA escrever em Y0–Y3, D5–D7, D10, D12, D51 nem C251.
Registos D começam em 0x1000 (D0 = 4096).
"""

# Corrida en dos máquinas — 23 nov 2026 (madrugada, sin supervisión)

Escritorio: VM VirtualBox Ubuntu 24.04 (6 vCPU, 12 GB) en 192.168.1.236 → ray-head + nodo-a
Notebook: 192.168.1.104 por Wi-Fi (-66 dBm) → nodo-b
Red medida: ~11 Mbit/s, RTT medio 42–61 ms (picos 189 ms)

| Medición | Una PC | Dos máquinas |
|---|---|---|
| Demo 1 relación distrib/local (n=512..4096) | 2,8x..1,0x | 111x..35x |
| Demo 2 ms/token pipeline / entero | 152 / 148 | 3900 / 122 |
| Demo 2 8 pedidos solapados (s) | 4,0 | 289,5 |
| Demo 3 1 réplica (s) | 88,6 | 74,2 |
| Demo 3 2 réplicas (s) | 76,6 | 49,0 |
| Demo 3 con caída de nodo-b (s) | 81,9 | 58,3 (30/30, recuperación ~19 s) |
| Secuencial (s) | 100,7 | 62,9 escritorio / 79,4 notebook |

CSVs de una PC: resultados/una-pc/. CSVs nuevos: esta carpeta.
Informe actualizado (sección 4.5, resumen, limitaciones): https://claude.ai/artifact/QuTaiTwt9eLGttgAb9dde6
Pendiente: actualizar el artefacto explicativo y el md de NotebookLM con estos números; repetir con cable.

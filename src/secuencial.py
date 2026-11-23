"""Versión secuencial (sin Ray) de la carga de la demo 3.

Los mismos 30 pedidos (misma semilla, prompts de 16 tokens, 20 tokens generados)
se atienden uno detrás de otro en un solo proceso, sin cluster ni red. Es la línea
base contra la que se comparan las réplicas de la demo 3: el speedup es
tiempo_secuencial / tiempo_distribuido.

Uso:  python src/secuencial.py [--pedidos 30] [--tokens 20]
"""
import argparse
import csv
import socket
import time

import torch

from modelo import Tramo, cargar_modelo, generar


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--pedidos", type=int, default=30)
    p.add_argument("--tokens", type=int, default=20)
    p.add_argument("--salida", default="resultados/secuencial.csv")
    a = p.parse_args()

    modelo, _ = cargar_modelo()
    tramo = Tramo(modelo, 0, len(modelo.transformer.h))
    g = torch.Generator().manual_seed(0)  # mismos prompts que demo3_router.py
    prompts = [torch.randint(0, 50257, (1, 16), generator=g) for _ in range(a.pedidos)]
    print(f"{a.pedidos} pedidos de a uno en {socket.gethostname()}, {torch.get_num_threads()} hilo(s), {a.tokens} tokens cada uno.\n")

    generar(tramo, prompts[0], 1)  # calentamiento, fuera de la medición
    filas = []
    t0 = time.perf_counter()
    for i, x in enumerate(prompts):
        t = time.perf_counter()
        salida = generar(tramo, x, a.tokens)
        fin = time.perf_counter() - t0
        assert salida.shape[1] == x.shape[1] + a.tokens
        filas.append({"pedido": i, "t_fin_s": round(fin, 3), "latencia_s": round(time.perf_counter() - t, 3)})
        print(f"  t={fin:6.2f}s  pedido {i:>3} ({filas[-1]['latencia_s']:.2f}s)")
    total = time.perf_counter() - t0

    lat = sorted(f["t_fin_s"] for f in filas)  # en una cola, la latencia de cada pedido es su espera + servicio
    print(f"\nTotal: {total:.2f} s -> {a.pedidos / total:.2f} pedidos/s")
    print(f"Latencia media {sum(lat) / len(lat):.2f} s (cada pedido espera a todos los anteriores)")
    print(f"Pedidos completados: {len(filas)}/{a.pedidos}")
    with open(a.salida, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=filas[0].keys()); w.writeheader(); w.writerows(filas)
    print(f"Resultados en {a.salida}")


if __name__ == "__main__":
    main()

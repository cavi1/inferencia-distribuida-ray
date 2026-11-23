"""Demo 1 - Paralelismo de tensores.

Se simula una red de L capas densas (x <- tanh(x @ W_l)). Cada matriz W_l se
corta por columnas entre K actores ubicados en nodos distintos (como hace
Megatron-LM). En cada capa el driver envía x a todos los fragmentos, recibe las
partes y las concatena: hay una ronda de comunicación POR CAPA.

Se compara contra un actor que tiene las matrices completas y hace todo sin red.
Hipótesis: con matrices chicas o con latencia de red, distribuir es MÁS LENTO,
porque la comunicación por capa domina sobre el cálculo.

Uso:  python src/demo1_tensores.py [--capas 12] [--lote 8] [--tamanos 512 1024 2048 4096]
"""
import argparse
import csv
import time

import numpy as np
import ray

from cluster import NODOS, conectar, en_nodo, host
from eventos import instante, tarea


@ray.remote(num_cpus=1)
class Fragmento:
    def __init__(self, n, capas, k, indice, semilla=0):
        rng = np.random.default_rng(semilla)
        columnas = np.array_split(np.arange(n), k)[indice]
        self.W = []
        for _ in range(capas):  # misma semilla => mismas matrices en todos los actores
            W = rng.standard_normal((n, n), dtype=np.float32) / np.sqrt(n)
            self.W.append(np.ascontiguousarray(W[:, columnas]))

    def multiplicar(self, x, capa, flujo="dist", paso=0):
        with tarea(f"capa {capa + 1}", flujo, paso, clave=capa):
            return x @ self.W[capa]

    def ejecutar_todo(self, x, flujo="local"):
        """Solo tiene sentido con k=1: todas las capas en el mismo proceso."""
        for c, W in enumerate(self.W):
            with tarea(f"capa {c + 1}", flujo, c, clave=c):
                x = np.tanh(x @ W)
        return x

    def nodo(self):
        return host()


def ejecutar_distribuido(frags, x0, capas, flujo="dist"):
    """Una pasada por todas las capas con las matrices repartidas entre `frags`."""
    instante("enviar lote", flujo, 0)
    x = x0
    for c in range(capas):
        partes = ray.get([f.multiplicar.remote(x, c, flujo, 2 * c + 1) for f in frags])
        with tarea("juntar", flujo, 2 * c + 2, clave=c):
            x = np.tanh(np.concatenate(partes, axis=1))
    return x


def medir(n, capas, lote, k, repeticiones=3):
    x0 = np.random.default_rng(1).standard_normal((lote, n), dtype=np.float32)

    local = Fragmento.options(**en_nodo(NODOS[0])).remote(n, capas, 1, 0)
    frags = [Fragmento.options(**en_nodo(NODOS[i % len(NODOS)])).remote(n, capas, k, i) for i in range(k)]
    ubicacion = ray.get([f.nodo.remote() for f in frags])

    ref_local = ray.get(local.ejecutar_todo.remote(x0))  # calentamiento + resultado de referencia
    dif = float(np.abs(ejecutar_distribuido(frags, x0, capas) - ref_local).max())

    t_local, t_dist = [], []
    for _ in range(repeticiones):
        t = time.perf_counter(); ray.get(local.ejecutar_todo.remote(x0)); t_local.append(time.perf_counter() - t)
        t = time.perf_counter(); ejecutar_distribuido(frags, x0, capas); t_dist.append(time.perf_counter() - t)

    for a in [local, *frags]:
        ray.kill(a)
    return min(t_local), min(t_dist), dif, ubicacion


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--capas", type=int, default=12)
    p.add_argument("--lote", type=int, default=8)
    p.add_argument("--fragmentos", type=int, default=2)
    p.add_argument("--tamanos", type=int, nargs="+", default=[512, 1024, 2048, 4096])
    p.add_argument("--salida", default="resultados/demo1_tensores.csv")
    a = p.parse_args()

    conectar()
    print(f"\n{a.capas} capas, lote {a.lote}, {a.fragmentos} fragmentos por matriz\n")
    print(f"{'n':>6} | {'local (ms)':>10} | {'distrib. (ms)':>13} | {'relación':>8} | {'dif. máx':>9} | fragmentos en")
    filas = []
    for n in a.tamanos:
        tl, td, dif, ubic = medir(n, a.capas, a.lote, a.fragmentos)
        print(f"{n:>6} | {tl*1e3:>10.1f} | {td*1e3:>13.1f} | {td/tl:>7.2f}x | {dif:>9.1e} | {', '.join(ubic)}")
        filas.append({"n": n, "capas": a.capas, "lote": a.lote, "fragmentos": a.fragmentos,
                      "local_ms": round(tl * 1e3, 2), "distribuido_ms": round(td * 1e3, 2),
                      "relacion": round(td / tl, 2), "dif_max": dif})
    with open(a.salida, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=filas[0].keys()); w.writeheader(); w.writerows(filas)
    print(f"\nrelación > 1 => distribuir fue más lento. Resultados en {a.salida}")
    print(f"Rondas de comunicación por ejecución: {a.capas} (una por capa).")


if __name__ == "__main__":
    main()

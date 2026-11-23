"""Demo 2 - Paralelismo de pipeline.

GPT-2 (12 bloques) se parte en dos actores: la etapa 1 (embeddings + bloques
0-5) vive en nodo_a y la etapa 2 (bloques 6-11 + cabeza) en nodo_b. Los estados
ocultos viajan de una etapa a otra por el object store de Ray, sin pasar por el
driver (se pasa la referencia del resultado de la etapa 1 a la etapa 2).

Se muestra:
  1. Corrección: el pipeline da los mismos logits que el modelo entero.
  2. Generación de texto token por token a través de los dos nodos.
  3. Rendimiento con varios pedidos: mientras la etapa 2 procesa el pedido i,
     la etapa 1 ya procesa el pedido i+1 (línea de montaje).

Uso:  python src/demo2_pipeline.py [--pedidos 8] [--largo 128] [--tokens 15]
"""
import argparse
import csv
import time

import ray
import torch

from cluster import NODOS, conectar, en_nodo, host
from eventos import tarea
from modelo import Tramo, cargar_modelo, cargar_tokenizer, codificar, decodificar, generar


@ray.remote(num_cpus=1)
class Etapa:
    def __init__(self, desde, hasta, nombre="etapa"):
        modelo, _ = cargar_modelo()
        self.tramo = Tramo(modelo, desde, hasta)  # el resto del modelo se libera
        self.capas = (desde, hasta)
        self.nombre = nombre

    def forward(self, x, flujo="p", paso=1, rotulo="", clave=None):
        with tarea(f"{rotulo} · {self.nombre}".strip(" ·"), flujo, paso, clave=clave):
            return self.tramo(x)

    def info(self):
        return f"bloques {self.capas[0]}-{self.capas[1] - 1} en {host()}"


@ray.remote(num_cpus=1)
class ModeloCompleto:
    def __init__(self):
        modelo, _ = cargar_modelo()
        self.tramo = Tramo(modelo, 0, len(modelo.transformer.h))

    def forward(self, x, flujo="p", paso=1, rotulo="", clave=None):
        with tarea(f"{rotulo} · modelo entero".strip(" ·"), flujo, paso, clave=clave):
            return self.tramo(x)

    def info(self):
        return f"modelo entero en {host()}"


def pasar_por_pipeline(e1, e2, x, flujo="p", rotulo="", clave=None):
    """Devuelve la referencia al resultado. La etapa 2 recibe la salida de la 1
    desde el object store de Ray, sin que los datos pasen por el driver."""
    return e2.forward.remote(e1.forward.remote(x, flujo, 1, rotulo, clave), flujo, 2, rotulo, clave)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--pedidos", type=int, default=8)
    p.add_argument("--largo", type=int, default=128, help="tokens por pedido en la prueba de rendimiento")
    p.add_argument("--tokens", type=int, default=15, help="tokens a generar en la prueba de texto")
    p.add_argument("--salida", default="resultados/demo2_pipeline.csv")
    a = p.parse_args()

    conectar()
    tok = cargar_tokenizer()
    e1 = Etapa.options(**en_nodo(NODOS[0])).remote(0, 6, "etapa 1")
    e2 = Etapa.options(**en_nodo(NODOS[1])).remote(6, 12, "etapa 2")
    completo = ModeloCompleto.options(**en_nodo(NODOS[0])).remote()
    print("\nEtapa 1:", ray.get(e1.info.remote()))
    print("Etapa 2:", ray.get(e2.info.remote()))
    print("Base   :", ray.get(completo.info.remote()))

    def paso_pipeline(ids):
        return ray.get(pasar_por_pipeline(e1, e2, ids))  # e1 -> e2 sin pasar por el driver

    def paso_completo(ids):
        return ray.get(completo.forward.remote(ids))

    # 1. Corrección
    ids = codificar(tok, "Los sistemas distribuidos permiten")
    dif = (paso_pipeline(ids) - paso_completo(ids)).abs().max().item()
    print(f"\n[1] Diferencia máxima de logits pipeline vs modelo entero: {dif:.2e}")

    # 2. Generación
    t = time.perf_counter(); salida = generar(paso_pipeline, ids, a.tokens); t_pipe = time.perf_counter() - t
    t = time.perf_counter(); generar(paso_completo, ids, a.tokens); t_comp = time.perf_counter() - t
    print(f"[2] Texto generado por el pipeline: {decodificar(tok, salida)!r}")
    print(f"    ms por token: pipeline {t_pipe / a.tokens * 1e3:.1f} | modelo entero {t_comp / a.tokens * 1e3:.1f}")

    # 3. Rendimiento con varios pedidos
    g = torch.Generator().manual_seed(0)
    pedidos = [torch.randint(0, 50257, (1, a.largo), generator=g) for _ in range(a.pedidos)]

    t = time.perf_counter()
    for x in pedidos:
        ray.get(completo.forward.remote(x))
    t_base = time.perf_counter() - t

    t = time.perf_counter()
    for i, x in enumerate(pedidos):  # uno por vez: una etapa siempre está ociosa
        ray.get(pasar_por_pipeline(e1, e2, x, f"s{i}", f"pedido {i + 1}", i))
    t_seq = time.perf_counter() - t

    t = time.perf_counter()
    ray.get([pasar_por_pipeline(e1, e2, x, f"o{i}", f"pedido {i + 1}", i)
             for i, x in enumerate(pedidos)])  # todos a la vez: se solapan
    t_sol = time.perf_counter() - t

    print(f"[3] {a.pedidos} pedidos de {a.largo} tokens:")
    filas = [("modelo entero, 1 nodo", t_base), ("pipeline, de a uno", t_seq), ("pipeline, solapado", t_sol)]
    for nombre, tiempo in filas:
        print(f"    {nombre:<22} {tiempo:6.2f} s  -> {a.pedidos / tiempo:5.2f} pedidos/s")

    with open(a.salida, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["escenario", "segundos", "pedidos_por_s"])
        for nombre, tiempo in filas:
            w.writerow([nombre, round(tiempo, 3), round(a.pedidos / tiempo, 3)])
        w.writerow(["dif_max_logits", dif, ""])
        w.writerow(["ms_por_token_pipeline", round(t_pipe / a.tokens * 1e3, 2), ""])
        w.writerow(["ms_por_token_entero", round(t_comp / a.tokens * 1e3, 2), ""])
    print(f"\nResultados en {a.salida}")


if __name__ == "__main__":
    main()

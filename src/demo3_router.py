"""Demo 3 - Paralelismo de datos: réplicas + router + tolerancia a fallas.

Varias réplicas del modelo entero (una por worker) atienden pedidos que llegan
todos a la vez. Un actor Router (en el head) envía cada pedido a la réplica con
menos pedidos en curso y lleva estadísticas compartidas (estado en un actor).

Tolerancia a fallas: las réplicas se crean con max_restarts=-1 y
max_task_retries=-1. Si se apaga un worker en medio de la ejecución
(docker compose kill ray-worker-2), Ray recrea la réplica en el nodo que queda y
reintenta los pedidos que estaban en curso: ningún pedido se pierde.

Uso:  python src/demo3_router.py [--replicas 2] [--pedidos 30] [--tokens 20]
"""
import argparse
import csv
import time

import ray
import torch

from cluster import conectar, host
from eventos import emitir, instante, nodo_id, tarea
from modelo import Tramo, cargar_modelo, generar, muestrear


@ray.remote(num_cpus=1, max_restarts=-1, max_task_retries=-1)
class Replica:
    def __init__(self, nombre):
        modelo, _ = cargar_modelo()
        self.tramo = Tramo(modelo, 0, len(modelo.transformer.h))
        self.nombre = nombre
        print(f"[{nombre}] lista en {host()}")  # se vuelve a ver si Ray la recrea
        emitir("evento", texto=f"{nombre} lista")

    def listo(self):
        return host()

    def donde(self):
        return nodo_id()

    def paso(self, ids, semilla):
        """Una palabra del chat del panel. La semilla fija hace que un reintento tras una caída
        devuelva el mismo token."""
        logits = self.tramo(ids)
        siguiente = muestrear(logits, ids, torch.Generator().manual_seed(semilla))
        return int(siguiente), host()

    def generar(self, ids, n_tokens, pedido=0):
        with tarea(f"pedido {pedido + 1}", f"r{pedido}", 1, clave=pedido, replica=self.nombre):
            salida = generar(self.tramo, ids, n_tokens)
        return {"replica": self.nombre, "nodo": host(), "tokens": salida.shape[1]}


@ray.remote(num_cpus=0, resources={"head": 0.01})
class Router:
    def __init__(self, replicas):
        self.replicas = replicas
        self.en_curso = [0] * len(replicas)
        self.total = [0] * len(replicas)
        self.atendidos = {}  # (réplica, nodo) -> cantidad
        self.latencias = []

    def listo(self):
        return True

    def elegir(self):
        """Réplica con menos pedidos en curso; si empatan, la que atendió menos (chat del panel)."""
        i = min(range(len(self.replicas)), key=lambda j: (self.en_curso[j], self.total[j]))
        self.en_curso[i] += 1
        self.total[i] += 1
        return i

    def soltar(self, i):
        self.en_curso[i] -= 1

    async def atender(self, ids, n_tokens, pedido=0):
        i = min(range(len(self.replicas)), key=lambda j: self.en_curso[j])  # menos cargada
        self.en_curso[i] += 1
        instante(f"asignar pedido {pedido + 1}", f"r{pedido}", 0, clave=pedido)
        t = time.perf_counter()
        try:
            r = await self.replicas[i].generar.remote(ids, n_tokens, pedido)
        finally:
            self.en_curso[i] -= 1
        r["latencia_s"] = time.perf_counter() - t
        instante(f"respuesta {pedido + 1}", f"r{pedido}", 2, clave=pedido)
        emitir("pedido_fin", pedido=pedido, latencia=r["latencia_s"], replica=r["replica"])
        clave = f"{r['replica']}@{r['nodo']}"
        self.atendidos[clave] = self.atendidos.get(clave, 0) + 1
        self.latencias.append(r["latencia_s"])
        return r

    def estadisticas(self):
        lat = sorted(self.latencias)
        return {"atendidos": self.atendidos, "lat_media": sum(lat) / len(lat),
                "lat_p95": lat[int(0.95 * (len(lat) - 1))]}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--replicas", type=int, default=2)
    p.add_argument("--pedidos", type=int, default=30)
    p.add_argument("--tokens", type=int, default=20)
    p.add_argument("--simular-falla", type=float, default=None, metavar="SEG",
                   help="mata el proceso de la réplica 2 a los SEG segundos (sin Docker)")
    p.add_argument("--salida", default="resultados/demo3_router.csv")
    a = p.parse_args()

    conectar()
    replicas = [Replica.options(scheduling_strategy="SPREAD").remote(f"replica-{i + 1}")
                for i in range(a.replicas)]
    print("Réplicas listas en:", ray.get([r.listo.remote() for r in replicas]))
    router = Router.remote(replicas)
    g = torch.Generator().manual_seed(0)
    prompts = [torch.randint(0, 50257, (1, 16), generator=g) for _ in range(a.pedidos)]

    print(f"\n{a.pedidos} pedidos simultáneos, {a.replicas} réplica(s), {a.tokens} tokens cada uno.")
    print("Para probar la tolerancia a fallas, en otra terminal:  docker compose kill ray-worker-2\n")
    t0 = time.perf_counter()
    pendientes = {router.atender.remote(x, a.tokens, i): i for i, x in enumerate(prompts)}
    filas = []
    falla_pendiente = a.simular_falla is not None and len(replicas) > 1
    while pendientes:
        listos, _ = ray.wait(list(pendientes), num_returns=1, timeout=0.5)
        if falla_pendiente and time.perf_counter() - t0 >= a.simular_falla:
            print(f"  t={time.perf_counter() - t0:6.2f}s  *** se mata el proceso de replica-2 ***")
            ray.kill(replicas[1], no_restart=False)  # como una caída: Ray la reinicia
            falla_pendiente = False
        if not listos:
            continue
        r = ray.get(listos[0])
        i = pendientes.pop(listos[0])
        t = time.perf_counter() - t0
        print(f"  t={t:6.2f}s  pedido {i:>3} -> {r['replica']} en {r['nodo']:<13} ({r['latencia_s']:.2f}s)")
        filas.append({"pedido": i, "t_fin_s": round(t, 3), "replica": r["replica"],
                      "nodo": r["nodo"], "latencia_s": round(r["latencia_s"], 3)})
    total = time.perf_counter() - t0

    est = ray.get(router.estadisticas.remote())
    print(f"\nTotal: {total:.2f} s -> {a.pedidos / total:.2f} pedidos/s")
    print(f"Latencia media {est['lat_media']:.2f} s, p95 {est['lat_p95']:.2f} s")
    print("Pedidos por réplica y nodo:", est["atendidos"])
    print(f"Pedidos completados: {len(filas)}/{a.pedidos}")

    with open(a.salida, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=filas[0].keys()); w.writeheader(); w.writerows(filas)
    print(f"Resultados en {a.salida}")


if __name__ == "__main__":
    main()

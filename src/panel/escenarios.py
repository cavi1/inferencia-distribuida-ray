"""Escenarios que el panel puede ejecutar. Reutilizan los actores de las demos
y publican, además, el relato de lo que pasa (fases, estado, resúmenes).

Cada escenario recibe un diccionario de parámetros y no devuelve nada: todo lo
que el panel necesita sale por eventos (ver eventos.py).
"""
import threading
import time

import numpy as np
import ray
import torch

import demo1_tensores as d1
import demo2_pipeline as d2
import demo3_router as d3
from cluster import NODOS, en_nodo
from eventos import emitir

_cache = {"pipeline": None, "replicas": None}  # actores que se conservan entre ejecuciones (cargar GPT-2 tarda)
pedir_falla = threading.Event()


def _entero(p, nombre, defecto, minimo, maximo):
    try:
        v = int(p.get(nombre, defecto))
    except (TypeError, ValueError):
        v = defecto
    return max(minimo, min(maximo, v))


def liberar(conservar=None):
    """Mata los actores cacheados de otras demos para liberar CPUs."""
    for clave, valor in list(_cache.items()):
        if clave != conservar and valor:
            for actor in valor["actores"]:
                try:
                    ray.kill(actor)
                except Exception:
                    pass
            _cache[clave] = None


# ---------------------------------------------------------------- demo 1
def tensores(p):
    liberar()
    n = _entero(p, "n", 1024, 128, 4096)
    capas = _entero(p, "capas", 8, 2, 16)
    lote = 8
    emitir("estado", texto="Creando las matrices en cada nodo...")
    local = d1.Fragmento.options(**en_nodo(NODOS[0])).remote(n, capas, 1, 0)
    frags = [d1.Fragmento.options(**en_nodo(NODOS[i])).remote(n, capas, 2, i) for i in range(2)]
    ray.get([a.nodo.remote() for a in [local, *frags]])
    x0 = np.random.default_rng(1).standard_normal((lote, n), dtype=np.float32)
    emitir("estado", texto="Calentando (una pasada de prueba)...")
    referencia = ray.get(local.ejecutar_todo.remote(x0, "calentar"))
    d1.ejecutar_distribuido(frags, x0, capas, "calentar")

    emitir("estado", texto="Midiendo")
    emitir("fase", clave="local", texto="Un solo nodo hace todas las capas")
    t = time.perf_counter()
    ray.get(local.ejecutar_todo.remote(x0, "local"))
    t_local = time.perf_counter() - t
    emitir("resumen", fase="local", segundos=t_local)

    emitir("fase", clave="dist", texto="Dos nodos: cada uno calcula la mitad de cada capa")
    t = time.perf_counter()
    salida = d1.ejecutar_distribuido(frags, x0, capas, "dist")
    t_dist = time.perf_counter() - t
    emitir("resumen", fase="dist", segundos=t_dist)
    emitir("resumen", fase="comparacion", relacion=t_dist / t_local, capas=capas,
           diferencia=float(np.abs(salida - referencia).max()),
           texto=f"Distribuir tardó {t_dist / t_local:.2f} veces lo que tardó un solo nodo: "
                 f"hubo {capas} rondas de comunicación, una por capa.")
    for a in [local, *frags]:
        ray.kill(a)


# ---------------------------------------------------------------- demo 2
def pipeline(p):
    liberar(conservar="pipeline")
    pedidos = _entero(p, "pedidos", 6, 2, 16)
    largo = _entero(p, "largo", 64, 8, 256)
    if not _cache["pipeline"]:
        emitir("estado", texto="Cargando GPT-2 en cada nodo (la primera vez tarda unos segundos)...")
        e1 = d2.Etapa.options(**en_nodo(NODOS[0])).remote(0, 6, "etapa 1")
        e2 = d2.Etapa.options(**en_nodo(NODOS[1])).remote(6, 12, "etapa 2")
        completo = d2.ModeloCompleto.options(**en_nodo(NODOS[0])).remote()
        ray.get([e1.info.remote(), e2.info.remote(), completo.info.remote()])
        _cache["pipeline"] = {"actores": [e1, e2, completo]}
    e1, e2, completo = _cache["pipeline"]["actores"]

    g = torch.Generator().manual_seed(0)
    xs = [torch.randint(0, 50257, (1, largo), generator=g) for _ in range(pedidos)]
    emitir("estado", texto="Calentando (una pasada de prueba)...")
    ray.get(completo.forward.remote(xs[0], "calentar", 1))
    ray.get(d2.pasar_por_pipeline(e1, e2, xs[0], "calentar2"))

    emitir("estado", texto="Midiendo")
    resultados = {}

    emitir("fase", clave="entero", texto="Modelo entero en un nodo, un pedido tras otro")
    t = time.perf_counter()
    for i, x in enumerate(xs):
        ray.get(completo.forward.remote(x, f"m{i}", 1, f"pedido {i + 1}", i))
    resultados["entero"] = time.perf_counter() - t
    emitir("resumen", fase="entero", segundos=resultados["entero"], pedidos=pedidos)

    emitir("fase", clave="seq", texto="Pipeline en dos nodos, un pedido por vez")
    t = time.perf_counter()
    for i, x in enumerate(xs):
        ray.get(d2.pasar_por_pipeline(e1, e2, x, f"s{i}", f"pedido {i + 1}", i))
    resultados["seq"] = time.perf_counter() - t
    emitir("resumen", fase="seq", segundos=resultados["seq"], pedidos=pedidos)

    emitir("fase", clave="solapado", texto="Pipeline en dos nodos, todos los pedidos a la vez")
    t = time.perf_counter()
    ray.get([d2.pasar_por_pipeline(e1, e2, x, f"o{i}", f"pedido {i + 1}", i) for i, x in enumerate(xs)])
    resultados["solapado"] = time.perf_counter() - t
    emitir("resumen", fase="solapado", segundos=resultados["solapado"], pedidos=pedidos)

    mejora = resultados["seq"] / resultados["solapado"]
    emitir("resumen", fase="comparacion", relacion=mejora,
           texto=f"Con los pedidos solapados, el pipeline terminó {mejora:.2f} veces más rápido que "
                 f"procesándolos de a uno: mientras el nodo B termina un pedido, el A ya empieza el siguiente.")


# ---------------------------------------------------------------- demo 3
def replicas(p):
    liberar(conservar="replicas")
    pedidos = _entero(p, "pedidos", 16, 2, 40)
    tokens = _entero(p, "tokens", 6, 1, 30)
    n_rep = _entero(p, "replicas", 2, 1, 2)
    def crear():
        liberar()
        time.sleep(1.5)  # ray.kill es asíncrono: dar tiempo a que se liberen las CPUs antes de ubicar las nuevas
        emitir("estado", texto="Cargando una copia de GPT-2 en cada nodo (la primera vez tarda unos segundos)...")
        reps = [d3.Replica.options(scheduling_strategy="SPREAD").remote(f"réplica {i + 1}") for i in range(n_rep)]
        ray.get([r.listo.remote() for r in reps])
        _cache["replicas"] = {"actores": reps, "n": n_rep}

    if not _cache["replicas"] or _cache["replicas"]["n"] != n_rep:
        crear()
    for _ in range(3):
        reps = _cache["replicas"]["actores"]
        donde = ray.get([r.donde.remote() for r in reps])
        if n_rep == 1 or len(set(donde)) == n_rep:
            break
        crear()  # una caída anterior (o un reparto desparejo) las dejó juntas en un solo nodo
    router = d3.Router.remote(reps)
    ray.get(router.listo.remote())  # que el router ya esté vivo antes de empezar a medir

    g = torch.Generator().manual_seed(0)
    prompts = [torch.randint(0, 50257, (1, 16), generator=g) for _ in range(pedidos)]
    ray.get([r.generar.remote(prompts[0], 1, 0) for r in reps])  # calentamiento
    pedir_falla.clear()

    emitir("estado", texto="Midiendo")
    emitir("fase", clave="replicas", texto=f"{pedidos} pedidos a la vez, repartidos entre {n_rep} réplica(s)")
    t0 = time.perf_counter()
    pendientes = {router.atender.remote(x, tokens, i): i for i, x in enumerate(prompts)}
    completados = 0
    while pendientes:
        listos, _ = ray.wait(list(pendientes), num_returns=1, timeout=0.3)
        if pedir_falla.is_set() and n_rep > 1:
            pedir_falla.clear()
            emitir("falla", texto="se cayó la réplica 2", nodo_caido=donde[1])
            ray.kill(reps[1], no_restart=False)  # como una caída del proceso: Ray la recrea
        for ref in listos:
            ray.get(ref)
            pendientes.pop(ref)
            completados += 1
    total = time.perf_counter() - t0
    est = ray.get(router.estadisticas.remote())
    emitir("resumen", fase="replicas", segundos=total, pedidos=pedidos, completados=completados,
           por_segundo=pedidos / total, lat_media=est["lat_media"], lat_p95=est["lat_p95"])
    emitir("resumen", fase="comparacion", relacion=0,
           texto=f"Se completaron {completados} de {pedidos} pedidos en {total:.1f} s "
                 f"({pedidos / total:.2f} pedidos por segundo).")
    ray.kill(router)


ESCENARIOS = {"tensores": tensores, "pipeline": pipeline, "replicas": replicas}

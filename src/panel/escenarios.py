"""Escenarios que el panel puede ejecutar. Reutilizan los actores de las demos
y publican, además, el relato de lo que pasa (fases, estado, resúmenes).

Cada escenario recibe un diccionario de parámetros y no devuelve nada: todo lo
que el panel necesita sale por eventos (ver eventos.py).
"""
import time

import numpy as np
import ray
import torch

import demo1_tensores as d1
import demo2_pipeline as d2
import demo3_router as d3
from cluster import NODOS, en_nodo
from eventos import emitir
from modelo import cargar_tokenizer, codificar, decodificar, muestrear

_cache = {"pipeline": None, "replicas": None}  # actores que se conservan entre ejecuciones (cargar GPT-2 tarda)
_caer = {"f": None}  # la escena en marcha deja acá cómo tirar su réplica


def caer():
    """La llama POST /api/falla: mata la réplica en el momento (sin esperar al bucle de la
    escena) y devuelve el nombre del nodo donde estaba, o None si no hay réplicas en marcha."""
    f = _caer["f"]
    return f() if f else None


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
            for actor in valor["actores"] + ([valor["router"]] if valor.get("router") else []):
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
def _etapas():
    """Etapa 1 en nodo-a, etapa 2 en nodo-b y el modelo entero en nodo-a (se conservan entre ejecuciones)."""
    if not _cache["pipeline"]:
        emitir("estado", texto="Cargando GPT-2 en cada nodo (la primera vez tarda unos segundos)...")
        e1 = d2.Etapa.options(**en_nodo(NODOS[0])).remote(0, 6, "etapa 1")
        e2 = d2.Etapa.options(**en_nodo(NODOS[1])).remote(6, 12, "etapa 2")
        completo = d2.ModeloCompleto.options(**en_nodo(NODOS[0])).remote()
        ray.get([e1.info.remote(), e2.info.remote(), completo.info.remote()])
        _cache["pipeline"] = {"actores": [e1, e2, completo]}
    return _cache["pipeline"]["actores"]


def pipeline(p):
    liberar(conservar="pipeline")
    pedidos = _entero(p, "pedidos", 6, 2, 16)
    largo = _entero(p, "largo", 64, 8, 256)
    e1, e2, completo = _etapas()

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
def _replicas(n_rep):
    """Una réplica por nodo (se conservan entre ejecuciones). Devuelve (réplicas, id de nodo de cada una)."""
    def crear():
        liberar()
        time.sleep(1.5)  # ray.kill es asíncrono: dar tiempo a que se liberen las CPUs antes de ubicar las nuevas
        emitir("estado", texto="Cargando una copia de GPT-2 en cada nodo (la primera vez tarda unos segundos)...")
        # cada réplica atada a su nodo: si se cae, Ray la recrea en el mismo nodo y no en el otro
        reps = [d3.Replica.options(**en_nodo(NODOS[i])).remote(f"réplica {i + 1}") for i in range(n_rep)]
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
    return reps, donde


def replicas(p):
    liberar(conservar="replicas")
    pedidos = _entero(p, "pedidos", 16, 2, 40)
    tokens = _entero(p, "tokens", 6, 1, 30)
    n_rep = _entero(p, "replicas", 2, 1, 2)
    reps, donde = _replicas(n_rep)
    router = d3.Router.remote(reps)
    ray.get(router.listo.remote())  # que el router ya esté vivo antes de empezar a medir

    g = torch.Generator().manual_seed(0)
    prompts = [torch.randint(0, 50257, (1, 16), generator=g) for _ in range(pedidos)]
    ray.get([r.generar.remote(prompts[0], 1, 0) for r in reps])  # calentamiento
    nombres = _nombres_nodos()

    def tirar():
        ray.kill(reps[1], no_restart=False)  # como una caída del proceso: Ray la recrea
        emitir("falla", texto="se cayó la réplica 2", nodo_caido=donde[1])
        return nombres.get(donde[1])

    emitir("estado", texto="Midiendo")
    emitir("fase", clave="replicas", texto=f"{pedidos} pedidos a la vez, repartidos entre {n_rep} réplica(s)")
    t0 = time.perf_counter()
    pendientes = {router.atender.remote(x, tokens, i): i for i, x in enumerate(prompts)}
    completados = 0
    _caer["f"] = tirar if n_rep > 1 else None
    try:
        while pendientes:
            listos, _ = ray.wait(list(pendientes), num_returns=1, timeout=0.3)
            for ref in listos:
                ray.get(ref)
                pendientes.pop(ref)
                completados += 1
    finally:
        _caer["f"] = None
    total = time.perf_counter() - t0
    est = ray.get(router.estadisticas.remote())
    emitir("resumen", fase="replicas", segundos=total, pedidos=pedidos, completados=completados,
           por_segundo=pedidos / total, lat_media=est["lat_media"], lat_p95=est["lat_p95"])
    emitir("resumen", fase="comparacion", relacion=0,
           texto=f"Se completaron {completados} de {pedidos} pedidos en {total:.1f} s "
                 f"({pedidos / total:.2f} pedidos por segundo).")
    ray.kill(router)


# ---------------------------------------------------------------- chat: completar una frase
_tok = {"t": None}
CONTEXTO = 1024  # posiciones de GPT-2: frase + palabras generadas no pueden pasar de acá


def _nombres_nodos():
    nombres = {}
    for n in ray.nodes():
        r = n["Resources"]
        nombres[n["NodeID"]] = "nodo-a" if "nodo_a" in r else "nodo-b" if "nodo_b" in r else "ray-head"
    return nombres


def chat(p, estado):
    """Completa `p["texto"]` palabra por palabra en modo réplicas o pipeline.
    No usa el bus de eventos: va dejando todo en `estado`, que la página consulta."""
    if _tok["t"] is None:
        _tok["t"] = cargar_tokenizer()
    tok = _tok["t"]
    modo = p["modo"]
    ids = codificar(tok, p["texto"])
    n = p["palabras"]
    if ids.shape[1] + n > CONTEXTO:
        raise ValueError(f"la frase es demasiado larga: GPT-2 admite {CONTEXTO} tokens en total")
    semilla = int(time.time())
    nombres = _nombres_nodos()

    if modo == "replicas":
        liberar(conservar="replicas")
        reps, donde = _replicas(2)
        if not _cache["replicas"].get("router"):
            _cache["replicas"]["router"] = d3.Router.remote(reps)
        router = _cache["replicas"]["router"]
        i = ray.get(router.elegir.remote())
        estado.update(replica=f"réplica {i + 1}", nodo=nombres.get(donde[i]), fase="generando")
    else:
        liberar(conservar="pipeline")
        e1, e2, _ = _etapas()
        estado.update(fase="generando")

    def tirar():
        estado["caida"] = {"palabra": len(estado["palabras"]), "nodo": estado["nodo"], "ts": time.time()}
        ray.kill(reps[i], no_restart=False)  # la palabra en curso falla y Ray la reintenta en la réplica recreada
        return estado["nodo"]

    _caer["f"] = tirar if modo == "replicas" else None
    texto_previo = decodificar(tok, ids)
    try:
        for k in range(n):
            t = time.perf_counter()
            if modo == "replicas":
                siguiente, nodo = ray.get(reps[i].paso.remote(ids, semilla + k))
                nodo = nodo.split("/")[0]
                estado["nodo"] = nodo  # tras una caída, Ray puede recrearla en otro nodo
                pasos = [nodo]
            else:
                logits = ray.get(e2.forward.remote(e1.forward.remote(ids, "chat", 1), "chat", 2))
                siguiente = int(muestrear(logits, ids, torch.Generator().manual_seed(semilla + k)))
                pasos = ["nodo-a", "nodo-b"]
            ids = torch.cat([ids, torch.tensor([[siguiente]])], dim=1)
            texto = decodificar(tok, ids)
            estado["palabras"].append({"texto": texto[len(texto_previo):], "nodos": pasos,
                                       "ms": round((time.perf_counter() - t) * 1000), "ts": time.time()})
            texto_previo = texto
    finally:
        _caer["f"] = None
        if modo == "replicas":
            router.soltar.remote(i)
    estado["fase"] = "listo"


ESCENARIOS = {"tensores": tensores, "pipeline": pipeline, "replicas": replicas}

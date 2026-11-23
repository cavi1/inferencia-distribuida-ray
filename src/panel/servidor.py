"""Servidor del panel web: http://localhost:8000

Corre en el contenedor ray-head. Se conecta al cluster como driver, crea el bus
de eventos y expone una API chica que usa la página:

  GET  /                 la página
  GET  /api/nodos        nodos del cluster (y si están vivos)
  GET  /api/eventos      eventos nuevos desde la posición `desde`
  POST /api/ejecutar     {"demo": "tensores" | "pipeline" | "replicas", ...parámetros}
  POST /api/falla        mata la réplica 2 durante la demo de réplicas
"""
import os
import sys
import threading
import time
import traceback

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI))  # src/

import ray  # noqa: E402
import uvicorn  # noqa: E402
from fastapi import Body, FastAPI, HTTPException  # noqa: E402
from fastapi.responses import FileResponse  # noqa: E402

import escenarios  # noqa: E402
from cluster import conectar  # noqa: E402
import eventos  # noqa: E402
from eventos import crear_bus, emitir  # noqa: E402

app = FastAPI(title="Panel de inferencia distribuida")
estado = {"corriendo": False, "demo": None}
bloqueo = threading.Lock()
bus = None


def nombre_nodo(n):
    r = n["Resources"]
    if "head" in r:
        return "ray-head"
    if "nodo_a" in r:
        return "nodo-a"
    if "nodo_b" in r:
        return "nodo-b"
    return n["NodeManagerHostname"]


@app.get("/")
def pagina():
    return FileResponse(os.path.join(AQUI, "index.html"))


@app.get("/api/nodos")
def nodos():
    return [{"id": n["NodeID"], "nombre": nombre_nodo(n), "vivo": n["Alive"]} for n in ray.nodes()]


@app.get("/api/eventos")
def eventos(desde: int = 0):
    nuevos, siguiente = ray.get(bus.leer.remote(desde))
    return {"eventos": nuevos, "siguiente": siguiente, "ahora": time.time(),
            "corriendo": estado["corriendo"], "demo": estado["demo"]}


def _correr(demo, params):
    try:
        escenarios.ESCENARIOS[demo](params)
    except Exception as e:  # se muestra en la página en vez de morir en silencio
        traceback.print_exc()
        emitir("error", texto=f"{type(e).__name__}: {e}")
    finally:
        emitir("fin")
        estado["corriendo"] = False


@app.post("/api/ejecutar")
def ejecutar(params: dict = Body(...)):
    demo = params.get("demo")
    if demo not in escenarios.ESCENARIOS:
        raise HTTPException(400, "demo desconocida")
    with bloqueo:
        if estado["corriendo"]:
            raise HTTPException(409, "ya hay una ejecución en curso")
        estado.update(corriendo=True, demo=demo)
    ray.get(bus.reiniciar.remote())
    emitir("inicio", demo=demo)
    threading.Thread(target=_correr, args=(demo, params), daemon=True).start()
    return {"ok": True}


@app.post("/api/falla")
def falla():
    if not estado["corriendo"] or estado["demo"] != "replicas":
        raise HTTPException(409, "la caída solo se puede simular durante la demo de réplicas")
    escenarios.pedir_falla.set()
    return {"ok": True}


def main():
    global bus
    conectar(eventos=True)
    eventos.NODO_FIJO = next(n["NodeID"] for n in ray.nodes() if n["Alive"] and "head" in n["Resources"])
    bus = crear_bus()
    ray.get(bus.reiniciar.remote())
    print("[panel] listo en http://localhost:8000", flush=True)
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="warning")


if __name__ == "__main__":
    main()

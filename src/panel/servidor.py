"""Servidor del panel web: http://localhost:8000

Corre en el contenedor ray-head. Se conecta al cluster como driver, crea el bus
de eventos y expone una API chica que usa la página:

  GET  /                 la página
  GET  /api/nodos        nodos del cluster (y si están vivos)
  GET  /api/eventos      eventos nuevos desde la posición `desde`
  POST /api/ejecutar     {"demo": "tensores" | "pipeline" | "replicas", ...parámetros}
  POST /api/falla        mata la réplica 2 durante la demo de réplicas (o la réplica en uso del chat)
  GET  /chat.js          la pestaña «Completá la frase» (/?demo=frase)
  POST /api/chat         {"texto", "modo": "replicas" | "pipeline", "palabras"}
  GET  /api/chat         estado de la frase en curso
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


@app.get("/chat.js")
def chat_js():
    return FileResponse(os.path.join(AQUI, "chat.js"), media_type="text/javascript")


@app.get("/fuentes/{archivo}")
def fuentes(archivo: str):
    ruta = os.path.join(AQUI, "fuentes", os.path.basename(archivo))  # basename: nada fuera de fuentes/
    if not os.path.isfile(ruta):
        raise HTTPException(404)
    return FileResponse(ruta)


@app.get("/figura.svg")
def figura():
    return FileResponse(os.path.join(AQUI, "figura.svg"), media_type="image/svg+xml")


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


chat_estado = {"fase": "vacio", "palabras": []}


def _correr_chat(params):
    try:
        escenarios.chat(params, chat_estado)
    except Exception as e:
        traceback.print_exc()
        chat_estado.update(fase="error", error=f"{type(e).__name__}: {e}")
    finally:
        estado["corriendo"] = False


@app.post("/api/chat")
def chat(params: dict = Body(...)):
    texto = params.get("texto")
    if not isinstance(texto, str):
        raise HTTPException(400, "falta el texto")
    texto = texto.strip()
    modo = params.get("modo")
    if not 1 <= len(texto) <= 200:
        raise HTTPException(400, "escribí entre 1 y 200 caracteres")
    if modo not in ("replicas", "pipeline"):
        raise HTTPException(400, "modo desconocido")
    palabras = escenarios._entero(params, "palabras", 20, 1, 40)
    with bloqueo:
        if estado["corriendo"]:
            raise HTTPException(409, "ya hay una ejecución en curso")
        estado.update(corriendo=True, demo="chat")
    global chat_estado
    inicio = time.time()
    # se reemplaza el dict entero (no clear + update): una consulta nunca ve el estado a medio armar
    chat_estado = {"fase": "cargando", "modo": modo, "texto": texto, "total": palabras, "palabras": [], "inicio": inicio}
    threading.Thread(target=_correr_chat, args=({"texto": texto, "modo": modo, "palabras": palabras},), daemon=True).start()
    return {"ok": True, "inicio": inicio}


@app.get("/api/chat")
def ver_chat():
    return {**chat_estado, "ahora": time.time()}


@app.post("/api/falla")
def falla():
    en_chat = estado["demo"] == "chat" and chat_estado.get("modo") == "replicas"
    if not estado["corriendo"] or not (estado["demo"] == "replicas" or en_chat):
        raise HTTPException(409, "la caída solo se puede simular con réplicas en marcha")
    nodo = escenarios.caer()
    if nodo is None:
        raise HTTPException(409, "todavía no hay réplicas en marcha: probá en un segundo")
    return {"ok": True, "nodo": nodo}


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

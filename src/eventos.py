"""Bus de eventos: lo que las demos "cuentan" para que el panel web lo dibuje.

Hay un único actor `Bus` en el head (nombre "bus", namespace "inferencia").
Cualquier proceso del cluster (el driver, los actores en los workers) puede
mandarle eventos con `emitir()`. Si el bus no existe (por ejemplo al correr una
demo por consola sin el panel), `emitir()` no hace nada y casi no cuesta.

Eventos principales:
  tarea   un tramo de trabajo en un nodo: t0, t1, texto, flujo, paso, clave
  fase    arranca una etapa de la medición ("Un solo nodo", "Dos nodos"...)
  estado  texto de progreso ("cargando GPT-2...")
  resumen resultado de una fase (tiempos, pedidos por segundo)
  fin     terminó la ejecución

Los tiempos son time.time() de cada proceso. En Docker todos los contenedores
comparten el reloj del host, así que se pueden ordenar entre sí.
En un cluster real habría que sincronizar relojes (NTP/PTP).
"""
import os
import time
from contextlib import contextmanager

import ray

NOMBRE = "bus"


@ray.remote(num_cpus=0, resources={"head": 0.01})
class Bus:
    def __init__(self):
        self.eventos = []

    def emitir(self, evento):
        self.eventos.append(evento)

    def leer(self, desde):
        return self.eventos[desde:], len(self.eventos)

    def reiniciar(self):
        self.eventos = []


def crear_bus():
    return Bus.options(name=NOMBRE, get_if_exists=True).remote()


_cache = {"bus": None, "ultimo_intento": 0.0}


def _bus():
    if os.environ.get("EVENTOS") == "0":  # demos por consola: no publicar nada
        return None
    if _cache["bus"] is not None:
        return _cache["bus"]
    if time.time() - _cache["ultimo_intento"] < 3:  # no consultar al GCS en cada llamada
        return None
    _cache["ultimo_intento"] = time.time()
    try:
        _cache["bus"] = ray.get_actor(NOMBRE)
    except Exception:
        _cache["bus"] = None
    return _cache["bus"]


NODO_FIJO = None  # el servidor del panel fija aquí el id del head (el driver corre "en el head")


def nodo_id():
    return NODO_FIJO or ray.get_runtime_context().get_node_id()


def emitir(tipo, **datos):
    bus = _bus()
    if bus is None:
        return
    datos.update(tipo=tipo, ts=time.time(), nodo=nodo_id())
    try:
        bus.emitir.remote(datos)  # sin esperar respuesta
    except Exception:
        _cache["bus"] = None


@contextmanager
def tarea(texto, flujo, paso, clave=None, **extra):
    """Mide un tramo de trabajo y lo publica al terminar.

    flujo: identifica una cadena de pasos que se pasan datos (un pedido, una pasada por las capas...)
    paso:  orden dentro del flujo; el panel dibuja un paquete entre pasos consecutivos
           que ocurrieron en nodos distintos.
    clave: número que el panel usa para elegir el color.
    """
    t0 = time.time()
    try:
        yield
    finally:
        emitir("tarea", t0=t0, t1=time.time(), texto=texto, flujo=flujo, paso=paso, clave=clave, **extra)


def instante(texto, flujo, paso, clave=None, **extra):
    """Tarea casi instantánea (por ejemplo, el router eligiendo una réplica)."""
    t = time.time()
    emitir("tarea", t0=t, t1=t + 0.002, texto=texto, flujo=flujo, paso=paso, clave=clave, **extra)

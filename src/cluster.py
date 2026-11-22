"""Conexión al cluster Ray y utilidades de ubicación.

Dos modos:
  - Docker: la variable CLUSTER_RAY=auto hace que el script se conecte al cluster
    real (1 head + 2 workers). Cada worker publica un recurso propio
    ("nodo_a" o "nodo_b") para poder ubicar actores en un nodo concreto.
  - Local (sin Docker): se levanta un Ray de un solo proceso que simula esos
    mismos recursos. Sirve para probar el código, pero no hay red de por medio.
"""
import os
import socket

import ray

NODOS = ("nodo_a", "nodo_b")


def conectar():
    direccion = os.environ.get("CLUSTER_RAY")
    if direccion:
        ray.init(address=direccion)
        modo = "cluster"
    else:
        ray.init(
            num_cpus=4,
            resources={"head": 1, "nodo_a": 1, "nodo_b": 1},
            include_dashboard=False,
        )
        modo = "local (simulado, sin red)"
    vivos = [n for n in ray.nodes() if n["Alive"]]
    print(f"[cluster] modo {modo}: {len(vivos)} nodo(s) vivos")
    for n in vivos:
        propios = [r for r in n["Resources"] if r in NODOS or r == "head"]
        print(f"   - {n['NodeManagerHostname']:<12} CPUs={n['Resources'].get('CPU', 0):.0f} recursos={propios}")
    return modo


def en_nodo(nombre):
    """Opciones para fijar un actor en un nodo (usa una fracción mínima del recurso)."""
    return {"resources": {nombre: 0.01}}


def host():
    """Nombre del contenedor + 4 caracteres del id de nodo de Ray."""
    return f"{socket.gethostname()}/{ray.get_runtime_context().get_node_id()[:4]}"

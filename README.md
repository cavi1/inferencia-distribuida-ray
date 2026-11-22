# Inferencia distribuida de modelos de lenguaje con Ray

Trabajo de promoción de **Sistemas Distribuidos** (UNPSJB, 2026).

Un modelo de lenguaje (GPT-2) se reparte entre los nodos de un cluster Ray de tres contenedores. Se comparan tres formas de reparto:

| Demo | Técnica | Qué demuestra |
| --- | --- | --- |
| `demo1_tensores.py` | Paralelismo de tensores | Cortar cada matriz entre nodos obliga a comunicarse en **cada capa**, y en red eso suele ser más lento que no distribuir |
| `demo2_pipeline.py` | Paralelismo de pipeline | El modelo partido en dos nodos da **el mismo resultado** y gana rendimiento cuando hay varios pedidos a la vez |
| `demo3_router.py` | Paralelismo de datos | Un router reparte pedidos entre réplicas; si se cae un nodo, la réplica se recrea en otro y **no se pierde ningún pedido** |

## Arquitectura

```
ray-head      (0 CPUs: coordina, no ejecuta trabajo)
  ├─ GCS + dashboard :8265
  ├─ driver (los scripts de demo)
  └─ Router (demo 3)
      │
      ├── ray-worker-1 / nodo-a  (recurso nodo_a, 2 CPUs)
      │     Etapa 1 · Fragmento 0 · Réplica
      │
      └── ray-worker-2 / nodo-b  (recurso nodo_b, 2 CPUs)
            Etapa 2 · Fragmento 1 · Réplica
```

Cada worker publica un recurso propio (`nodo_a`, `nodo_b`), y así se elige en qué nodo vive cada actor.

## Requisitos

- Docker y Docker Compose.
- Unos 6 GB de RAM libres y 4 GB de disco: la imagen incluye PyTorch para CPU y los pesos de GPT-2.
- No hace falta GPU: el modelo corre en CPU. Los principios son los mismos que con GPUs.

## Ejecución

```bash
docker compose build          # la primera vez tarda (descarga PyTorch y GPT-2)
docker compose up -d          # levanta head + 2 workers
docker compose exec ray-head ray status    # deberían verse 3 nodos

docker compose exec ray-head python src/demo1_tensores.py
docker compose exec ray-head python src/demo2_pipeline.py
docker compose exec ray-head python src/demo3_router.py

docker compose down
```

Los resultados se guardan en `resultados/*.csv`. El dashboard de Ray queda en <http://localhost:8265>.

### Demo 3: tolerancia a fallas

Mientras corre la demo 3, en otra terminal:

```bash
docker compose kill ray-worker-2
```

Ray tarda unos segundos en declarar muerto al nodo (por falta de *heartbeats*). Después recrea la réplica en `nodo-a` y reintenta los pedidos que estaban en curso. Al final tiene que aparecer `Pedidos completados: N/N`. Para volver a levantar el nodo: `docker compose up -d ray-worker-2`.

Para comparar el rendimiento con una sola réplica: `python src/demo3_router.py --replicas 1`.

### Simular nodos lejanos

```bash
./scripts/latencia.sh ray-worker-1 20     # +20 ms en cada paquete saliente
./scripts/latencia.sh ray-worker-2 20
docker compose exec ray-head python src/demo1_tensores.py
./scripts/latencia.sh ray-worker-1 0      # quitar
./scripts/latencia.sh ray-worker-2 0
```

Con latencia, la demo 1 empeora en proporción a la cantidad de capas: hay una ronda de comunicación por capa. Es la razón por la que no se reparte un mismo pedido entre centros de datos distintos.

## Ejecución sin Docker (para desarrollo)

```bash
pip install torch --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements.txt
python src/demo1_tensores.py
```

Sin la variable `CLUSTER_RAY`, los scripts levantan un Ray local de un solo proceso que simula los recursos `nodo_a` y `nodo_b`. Sirve para probar el código, pero no hay red de por medio. La caída se puede simular con `python src/demo3_router.py --simular-falla 3`, que mata el proceso de una réplica.

Si no están los pesos de GPT-2, se usan pesos aleatorios con semilla fija. El texto sale sin sentido, pero los tiempos y la verificación de igualdad siguen valiendo.

## Estructura

```
src/cluster.py         conexión al cluster y ubicación de actores
src/modelo.py          carga de GPT-2, división en tramos de capas y generación greedy
src/demo1_tensores.py  paralelismo de tensores (numpy)
src/demo2_pipeline.py  paralelismo de pipeline (GPT-2 en dos etapas)
src/demo3_router.py    réplicas + router + tolerancia a fallas
scripts/latencia.sh    agrega latencia de red con tc/netem
```

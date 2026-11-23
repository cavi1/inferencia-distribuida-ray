# Inferencia distribuida de modelos de lenguaje con Ray

Trabajo de promoción de **Sistemas Distribuidos** (UNPSJB, 2026).

Un modelo de lenguaje (GPT-2) se reparte entre los nodos de un cluster Ray de tres contenedores, y un **panel web** muestra en vivo qué calcula cada nodo, cuándo se pasan datos y cuánto se espera. Se comparan tres formas de reparto:

| Demo | Técnica | Qué demuestra |
| --- | --- | --- |
| `demo1_tensores.py` | Paralelismo de tensores | Cortar cada matriz entre nodos obliga a comunicarse en **cada capa**, y en red eso suele ser más lento que no distribuir |
| `demo2_pipeline.py` | Paralelismo de pipeline | El modelo partido en dos nodos da **el mismo resultado** y gana rendimiento cuando hay varios pedidos a la vez |
| `demo3_router.py` | Paralelismo de datos | Un router reparte pedidos entre réplicas; si se cae una réplica o un nodo, se recrea en otro y **no se pierde ningún pedido** |

Es una reproducción a escala reducida: corre en CPU, con un modelo de 124 millones de parámetros y la red virtual de Docker. Los principios (cuánta comunicación exige cada reparto) son los mismos que en un datacenter, pero los tiempos absolutos no.

## Arquitectura

```
ray-head      (0 CPUs: coordina, no ejecuta trabajo)
  ├─ GCS + dashboard de Ray :8265
  ├─ panel web :8000  (driver + bus de eventos)
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
- No hace falta GPU.

## Puesta en marcha

```bash
docker compose build          # la primera vez tarda (descarga PyTorch y GPT-2)
docker compose up -d          # levanta head + 2 workers + panel
docker compose exec ray-head ray status    # deberían verse 3 nodos activos
```

Esperá unos 20 segundos a que se conecten los workers y abrí **http://localhost:8000**.

## El panel web

Elegí una demo en las pestañas, ajustá los parámetros y apretá **Ejecutar**.

- **Arriba:** el cluster. Un nodo se ilumina mientras calcula y cada círculo que viaja entre nodos es un dato que se manda por la red.
- **Abajo:** una línea de tiempo con una fila por nodo y una barra por cada tramo de trabajo. Los **huecos** entre barras son espera y comunicación.
- **Velocidad:** las demos de tensores duran milisegundos. En «× 1/20» o «× 1/50» se ven en cámara lenta. Las mediciones se hacen siempre a velocidad real; la cámara lenta solo cambia cómo se reproduce.
- **Ver de nuevo:** repite la animación sin volver a ejecutar.
- **Simular caída** (demo 3): mata el proceso de una réplica en plena ejecución. Ray la recrea y reintenta los pedidos que estaban en curso.

Qué esperar:

| Demo | Qué se ve |
| --- | --- |
| Tensores | Muchos huecos entre capas. Distribuido tarda más que un solo nodo (relación mayor que 1). Con matrices más grandes la relación baja |
| Pipeline | En la última fase, A y B trabajan a la vez sobre pedidos distintos. Los resultados son idénticos a los del modelo entero |
| Réplicas | Los pedidos se reparten entre las dos réplicas. Tras la caída hay un tramo con una sola réplica y luego una marca de recuperación; terminan todos los pedidos |

Para probar una **caída real de un nodo** (en vez de la simulada), mientras corre la demo 3:

```bash
docker compose kill ray-worker-2
```

Ray tarda unos segundos en declarar muerto al nodo (por falta de *heartbeats*), recrea la réplica en `nodo-a` y reintenta los pedidos. El panel marca el nodo como caído. Como el contenedor tiene `restart: on-failure`, puede volver solo a los pocos segundos.

## Demos por consola

Las mismas demos se pueden correr sin el panel, y guardan sus mediciones en `resultados/*.csv` (con los números para el informe):

```bash
docker compose exec ray-head python src/demo1_tensores.py
docker compose exec ray-head python src/demo2_pipeline.py
docker compose exec ray-head python src/demo3_router.py
docker compose exec ray-head python src/demo3_router.py --replicas 1     # para comparar con 1 réplica
docker compose exec ray-head python src/demo1_tensores.py --tamanos 512 2048 6144 --capas 4
```

Por consola no se publica ningún evento al panel, así que las mediciones no tienen costo extra.

### Simular nodos lejanos

```bash
./scripts/latencia.sh ray-worker-1 20     # +20 ms en cada paquete saliente
./scripts/latencia.sh ray-worker-2 20
docker compose exec ray-head python src/demo1_tensores.py
./scripts/latencia.sh ray-worker-1 0      # quitar
./scripts/latencia.sh ray-worker-2 0
```

Con latencia, la demo 1 empeora en proporción a la cantidad de capas: hay una ronda de comunicación por capa. Es la razón por la que no se reparte un mismo pedido entre centros de datos distintos. (Requiere bash: Linux, Mac o WSL.)

## Apagar

```bash
docker compose down
```

## Ejecución sin Docker (para desarrollo)

```bash
pip install torch --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements.txt
python src/demo1_tensores.py
python src/panel/servidor.py     # panel en http://localhost:8000
```

Sin la variable `CLUSTER_RAY`, los scripts levantan un Ray local de un solo proceso que simula los recursos `nodo_a` y `nodo_b`. Sirve para probar el código, pero no hay red de por medio y el panel mostrará todo en un único nodo físico. La caída de una réplica se puede simular con `python src/demo3_router.py --simular-falla 3`.

Si no están los pesos de GPT-2, se usan pesos aleatorios con semilla fija. El texto sale sin sentido, pero los tiempos y la verificación de igualdad siguen valiendo.

## Cómo funciona el panel

Las demos publican eventos a un actor `Bus` de Ray ubicado en el head (`src/eventos.py`). Cada evento «tarea» tiene el nodo, el instante de inicio y de fin, y un identificador de flujo y de paso. El servidor (`src/panel/servidor.py`, FastAPI) los entrega a la página, que los reproduce a la velocidad elegida. Un paquete entre dos nodos se dibuja cuando dos pasos consecutivos de un mismo flujo ocurrieron en nodos distintos.

Los tiempos se toman con el reloj de cada proceso. Los contenedores comparten el reloj del equipo anfitrión, por lo que se pueden ordenar entre sí. En un cluster real habría que sincronizar los relojes (NTP/PTP).

## Estructura

```
src/cluster.py         conexión al cluster y ubicación de actores
src/modelo.py          carga de GPT-2, división en tramos de capas y generación greedy
src/eventos.py         bus de eventos que alimenta el panel
src/demo1_tensores.py  paralelismo de tensores (numpy)
src/demo2_pipeline.py  paralelismo de pipeline (GPT-2 en dos etapas)
src/demo3_router.py    réplicas + router + tolerancia a fallas
src/panel/             servidor web (FastAPI), escenarios y página (index.html)
scripts/latencia.sh    agrega latencia de red con tc/netem
```

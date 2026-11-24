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
- **Cortar nodo-b** (demo 3): apaga Ray en nodo-b, como si se desenchufara. Ray recrea la réplica 2 en nodo-a y ningún pedido se pierde. nodo-b vuelve a conectarse solo a los 20 s (`VUELTA_NODO` en `src/worker.sh`).

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

## Completá la frase

En la pestaña «4 · Completá la frase» del panel (`http://localhost:8000/?demo=frase`) se escribe el comienzo de una frase en inglés y GPT-2 la completa en el cluster, palabra por palabra. Un dibujo isométrico del cluster muestra qué nodo calcula cada palabra:

- **Réplicas:** el Router elige la réplica menos usada y ese nodo genera toda la frase. «Simular caída» mata la réplica a mitad de frase: Ray la recrea y la frase sigue sin perder palabras.
- **Pipeline:** cada palabra pasa por las capas 1–6 en nodo-a y por las 7–12 en nodo-b.

GPT-2 small autocompleta texto, no responde preguntas: lo que se muestra es el reparto. El diseño está en `docs/chat-panel.md`. El dibujo (`src/panel/figura.svg`) se genera con `herramientas/figura/build.mjs`.

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

### Versión secuencial (sin Ray)

`src/secuencial.py` atiende los mismos 30 pedidos de la demo 3 (misma semilla, 20 tokens) uno detrás de otro, en un solo proceso y sin cluster. Es la línea base para calcular el speedup:

```bash
docker compose run --rm --no-deps ray-head python src/secuencial.py
```

Speedup = tiempo de `secuencial.py` / tiempo de `demo3_router.py`. Los resultados quedan en `resultados/secuencial.csv`.

### En dos máquinas reales

`docker-compose.dos-maquinas.yml` reparte el cluster en dos PCs de la misma red: el escritorio corre `ray-head` y `ray-worker-1` (nodo-a), y la notebook corre `ray-worker-2` (nodo-b). Los contenedores usan la red del host porque Ray conecta los nodos directamente por IP. Requiere Docker en Linux en las dos máquinas (en Windows o macOS, `network_mode: host` no expone la IP de la máquina).

1. En las dos máquinas: clonar el repo, `docker compose build` y `cp .env.ejemplo .env` con las IPs reales (`ip -4 addr`).
2. Permitir el tráfico entre las dos IPs en el firewall, por ejemplo con `sudo ufw allow from <IP de la otra máquina>`. Los puertos son fijos: el escritorio usa 6379–6381, 6390–6391, 8265, 10001, 52365–52378 y 11000–11199; la notebook usa 6400–6401, 52385–52388 y 11200–11299.
3. Levantar primero el escritorio y después la notebook:

```bash
docker compose -f docker-compose.dos-maquinas.yml --profile escritorio up -d   # escritorio
docker compose -f docker-compose.dos-maquinas.yml --profile notebook up -d     # notebook
```

4. Desde el escritorio: `docker compose -f docker-compose.dos-maquinas.yml exec ray-head ray status` debe mostrar 3 nodos. Las demos se corren igual, con `-f docker-compose.dos-maquinas.yml exec ray-head python src/...`.
5. Falla: en medio de la demo 3, en la notebook, `docker compose -f docker-compose.dos-maquinas.yml kill ray-worker-2` (o desconectarla de la red).

`scripts/latencia.sh` no se usa en este modo: con red del host, `tc` afectaría a toda la máquina, y además la red ya es real.

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
src/panel/             servidor web (FastAPI), escenarios, página (index.html, chat.js) y figura.svg
src/panel/fuentes/     IBM Plex guardada en el repo, para usar el panel sin internet
herramientas/figura/   genera figura.svg (kit isométrico de anatomy)
docs/chat-panel.md     diseño de la pestaña «Completá la frase»
src/secuencial.py      misma carga que la demo 3, sin Ray (línea base)
scripts/latencia.sh    agrega latencia de red con tc/netem
docker-compose.dos-maquinas.yml  cluster repartido en dos PCs (escritorio + notebook)
```

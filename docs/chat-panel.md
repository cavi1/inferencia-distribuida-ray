# Pestaña «Completá la frase» del panel

## Objetivo

Escribir el comienzo de una frase en inglés y ver cómo el cluster Ray la completa con GPT-2,
palabra por palabra, mostrando en un dibujo isométrico qué nodo calcula cada palabra y por dónde
viajan los datos. El modelo es chico (GPT-2 small, 124 M de parámetros, 2019): autocompleta, no
responde preguntas. El foco es el reparto que hace Ray.

## Qué ve el usuario (pestaña 4 del panel, `http://localhost:8000/?demo=frase`)

- Una caja de texto, un selector **Réplicas / Pipeline**, la cantidad de palabras y el botón
  **Completar**. En modo réplicas, también **Simular caída**.
- El dibujo del cluster sobre el fondo de la página, en una vista fija:
  - `ray-head` con el driver, el Router, el GCS y el dashboard.
  - Un **teclado** frente al head: muestra la frase escrita.
  - Una **impresora** al lado: cada palabra nueva sale impresa en una **cinta de papel**.
  - `nodo-a` y `nodo-b`, cada uno con una pila de 12 placas (las 12 capas de GPT-2).
  - Un switch con los cables a los tres contenedores.
- La respuesta debajo, con cada palabra subrayada con el color del nodo que la calculó
  (los dos colores en pipeline), y el tiempo por palabra.

### Qué se anima

| Modo | Por cada palabra |
|---|---|
| Réplicas | El Router elige la réplica menos usada (se encienden Router y nodo). El pedido viaja head → nodo, se encienden las 12 capas de ese nodo, la palabra vuelve al head y se imprime. |
| Pipeline | Viaja head → nodo-a, se encienden las capas 1–6, el estado oculto viaja a nodo-b, se encienden las 7–12, la palabra vuelve al head y se imprime. |
| Caída | En réplicas, el botón mata el proceso de la réplica en uso. El nodo se marca caído hasta que Ray la recrea y la frase sigue sin perder palabras. |
| Cortar nodo | En réplicas, apaga Ray en el nodo que responde. Su pila de capas flota hasta que Ray recrea la réplica en el otro nodo, viaja hasta ahí y aterriza como una segunda pila. En la respuesta, una marca «✂» muestra cuánto duró la pausa. El nodo vuelve solo a los 20 s y la frase siguiente reparte las réplicas de nuevo. En pipeline el botón está deshabilitado: cada mitad del modelo está atada a su nodo. |

Las animaciones siguen a los eventos reales; si las palabras llegan más rápido que la animación,
la animación se acelera para no atrasarse.

## Diseño técnico

### Backend

- `src/modelo.py`: `muestrear(logits, ids, generador)` con temperatura 0.8, top-p 0.9 y
  penalización de repetición 1.3. La generación greedy de las demos no cambia.
- `src/demo3_router.py`:
  - `Replica.paso(ids, semilla)` devuelve el próximo token y el nodo.
  - `Router.elegir()` y `Router.soltar(i)` eligen la réplica con menos pedidos en curso; si hay
    empate, la que atendió menos.
- `src/panel/escenarios.py`: la creación de réplicas y etapas se separa en funciones que usan las
  demos y el chat (se reusan los actores cacheados). Nueva función `chat(p, estado)`.
- `src/panel/servidor.py`:
  - `GET /chat.js` (la lógica de la pestaña) y `GET /figura.svg`.
  - `POST /api/chat {texto, modo, palabras}` y `GET /api/chat` con el estado de la frase.
  - `POST /api/falla` también vale durante un chat en modo réplicas.

### Decisiones

- **Un trabajo a la vez.** El chat usa el mismo candado que las demos: mientras corre un chat
  no se puede correr una demo y al revés. El panel se usa desde una sola PC.
- **Un paso remoto por palabra.** El driver pide cada palabra por separado. Si la réplica se cae,
  Ray reintenta solo esa palabra en la réplica recreada (`max_task_retries=-1`). La semilla de
  cada palabra es fija, así que el reintento da la misma palabra y no se duplica texto.
- **El estado del chat no pasa por el bus de eventos** de las demos: el servidor lo guarda en
  memoria y la página lo consulta. Así un chat no borra ni ensucia la línea de tiempo de una demo.
- **Validación:** texto de 1 a 200 caracteres, 1 a 40 palabras, y frase más respuesta dentro de
  los 1024 tokens de GPT-2.
- **Cambiar de modo** libera los actores del otro modo (igual que las demos): la primera frase
  después de cambiar tarda unos segundos más porque carga GPT-2.

### Dibujo

- `herramientas/figura/build.mjs` genera `src/panel/figura.svg` con el kit isométrico de anatomy.
  El SVG trae sus estilos, las piezas con `data-part` para encenderlas, y los recorridos de los
  paquetes como `<path data-ruta>` invisibles.
- Sin tarjeta: el dibujo va directo sobre el fondo. Sigue el tema del panel: claro u oscuro
  según el sistema.

## Plan de implementación

1. Backend: muestreo, `Replica.paso`, `Router.elegir/soltar`, escenario `chat`, endpoints.
2. Prueba por consola: una frase en cada modo y una caída a mitad de frase.
3. Dibujo: `build.mjs` y `figura.svg`; revisión con capturas.
4. Pestaña «4 · Completá la frase» dentro del panel (`index.html` + `chat.js`): controles, salida
   coloreada y animación ligada al estado. Sigue el tema claro u oscuro del panel.
5. `docker-compose.dos-maquinas.yml`: el head también arranca el panel (`http://IP_ESCRITORIO:8000`).
6. Prueba completa en el navegador, revisión del código con agy y PR.

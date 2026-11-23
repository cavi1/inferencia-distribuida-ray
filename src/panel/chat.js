// Pestaña «Completá la frase» del panel: GPT-2 completa una frase en el cluster y el dibujo
// isométrico (figura.svg) muestra qué nodo calcula cada palabra. Ver docs/chat-panel.md.
(() => {
"use strict";
const $ = (id) => document.getElementById(id);
const EXPLICA = {
  replicas: "Cada nodo tiene el modelo entero; el Router elige uno para toda la frase.",
  pipeline: "Las capas 1–6 están en nodo-a y las 7–12 en nodo-b; cada palabra pasa por los dos.",
};
const quieto = matchMedia("(prefers-reduced-motion: reduce)").matches;
const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const corto = (n) => n && n.startsWith("nodo-") ? n.slice(5) : null;  // "nodo-a" -> "a"

let svg, rutas = {}, paquete;
const S = { cuantas: 20, corriendo: false, mostradas: 0, recibidas: 0, cola: [], animando: false, chat: null, };

function modo() { return document.querySelector("input[name=modo]:checked").value; }
const part = (n) => svg.querySelector(`[data-part="${n}"]`);
const encender = (n, v) => { const p = part(n); if (p) v ? p.setAttribute("data-on", v) : p.removeAttribute("data-on"); };

// ---------------------------------------------------------------- figura
async function cargarFigura() {
  $("figura").innerHTML = await (await fetch("/figura.svg")).text();
  svg = $("figura").querySelector("svg");
  for (const p of svg.querySelectorAll("[data-ruta]")) {
    rutas[p.dataset.ruta] = p.getAttribute("d").match(/-?[\d.]+/g).map(Number).reduce((a, v, i) => (i % 2 ? a[a.length - 1].push(v) : a.push([v]), a), []);
  }
  const g = part("paquetes");
  paquete = document.createElementNS("http://www.w3.org/2000/svg", "circle");
  paquete.setAttribute("r", "5.5"); paquete.setAttribute("class", "paquete"); paquete.style.display = "none";
  g.appendChild(paquete);
  prepararModo();
}
function prepararModo() {
  if (!svg) return;
  const m = modo();
  $("explica").textContent = EXPLICA[m];
  for (const n of ["a", "b"]) for (let i = 1; i <= 12; i++) {
    const enOtroNodo = m === "pipeline" && (n === "a" ? i > 6 : i <= 6);
    part(`capa-${n}-${i}`).toggleAttribute("data-apagada", enOtroNodo);
  }
}
function textoEn(n, texto) { part(n).querySelector("text").textContent = texto; }

// recorrido como lista de puntos: ["head", "a"] = head -> switch -> nodo-a; "-a" = al revés.
// "teclado" va del teclado al head e "impresora" de la impresora al head.
function camino(tramos) {
  const pts = [];
  for (const t of tramos) { const r = t.startsWith("-") ? [...rutas[t.slice(1)]].reverse() : rutas[t]; pts.push(...r); }
  return pts;
}
function puntoEn(pts, f) {
  const largos = pts.slice(1).map((p, i) => Math.hypot(p[0] - pts[i][0], p[1] - pts[i][1]));
  let resto = f * largos.reduce((a, b) => a + b, 0);
  for (let i = 0; i < largos.length; i++) {
    if (resto <= largos[i]) { const u = largos[i] ? resto / largos[i] : 0; return [pts[i][0] + (pts[i + 1][0] - pts[i][0]) * u, pts[i][1] + (pts[i + 1][1] - pts[i][1]) * u]; }
    resto -= largos[i];
  }
  return pts[pts.length - 1];
}
const esperar = (ms) => new Promise((r) => setTimeout(r, quieto ? 0 : ms));
async function viajar(tramos, ms) {
  if (quieto) return;
  const pts = camino(tramos), t0 = performance.now();
  paquete.style.display = "";
  await new Promise((fin) => {
    const paso = (ahora) => {
      const f = Math.min(1, (ahora - t0) / ms), e = f < .5 ? 2 * f * f : 1 - Math.pow(-2 * f + 2, 2) / 2;
      const [x, y] = puntoEn(pts, e);
      paquete.setAttribute("cx", x.toFixed(1)); paquete.setAttribute("cy", y.toFixed(1));
      f < 1 ? requestAnimationFrame(paso) : fin();
    };
    requestAnimationFrame(paso);
  });
  paquete.style.display = "none";
}
async function capas(n, desde, hasta, ms) {
  for (let i = desde; i <= hasta; i++) { encender(`capa-${n}-${i}`, n); await esperar(ms / (hasta - desde + 1)); }
}
function apagarCapas() { for (const n of ["a", "b"]) for (let i = 1; i <= 12; i++) encender(`capa-${n}-${i}`, null); }

// una palabra: la animación sigue lo que pasó en el cluster
async function animarPalabra(p) {
  const rapido = 1 + Math.min(4, S.cola.length * 0.8);  // si llegan palabras más rápido que la animación, acelerar
  const ms = (x) => x / rapido;
  const nodos = p.nodos.map(corto);
  estado(`Palabra ${S.mostradas + 1} de ${S.chat.total}`, nodos.length > 1 ? "capas 1–6 en nodo-a, 7–12 en nodo-b" : `calcula nodo-${nodos[0]}`);
  const caida = S.chat.caida;
  if (caida && caida.palabra === S.mostradas) {  // la caída se muestra cuando la animación llega a esa palabra
    part(caida.nodo).setAttribute("data-caido", "");
    estado(`Se cayó la réplica de ${caida.nodo}`, `Ray la recreó en ${(p.ms / 1000).toFixed(1)} s y la frase siguió donde estaba`);
    await esperar(Math.min(p.ms, 4000));
    part(caida.nodo).removeAttribute("data-caido");
    estado(`Palabra ${S.mostradas + 1} de ${S.chat.total}`, `calcula nodo-${nodos[0]}`);
  }
  encender("driver", "h");
  if (nodos.length === 1) {
    encender("router", "h");
    await viajar(["teclado", "head", nodos[0]].slice(S.mostradas ? 1 : 0), ms(420));
    encender("router", null);
    await capas(nodos[0], 1, 12, ms(520));
    await viajar([`-${nodos[0]}`, "-head", "-impresora"], ms(420));
  } else {
    await viajar(["teclado", "head", "a"].slice(S.mostradas ? 1 : 0), ms(380));
    await capas("a", 1, 6, ms(300));
    await viajar(["-a", "b"], ms(320));
    await capas("b", 7, 12, ms(300));
    await viajar(["-b", "-head", "-impresora"], ms(380));
  }
  apagarCapas(); encender("driver", null);
  imprimir(p);
}
function imprimir(p) {
  S.mostradas++;
  const clase = p.nodos.length > 1 ? "ab" : corto(p.nodos[0]);
  $("salida").insertAdjacentHTML("beforeend", `<span class="tok ${clase}">${esc(p.texto)}</span>`);
  const cinta = S.chat.palabras.slice(0, S.mostradas).map((x) => x.texto).join("").replace(/\s+/g, " ").trim();
  textoEn("cinta", cinta.length > 62 ? "…" + cinta.slice(-61) : cinta);
  const prom = S.chat.palabras.slice(0, S.mostradas).reduce((a, x) => a + x.ms, 0) / S.mostradas;
  $("datos").textContent = `${S.mostradas} palabras · ${Math.round(prom)} ms por palabra en promedio`;
}
async function reproducir() {
  if (S.animando) return;
  S.animando = true;
  try {
    while (S.cola.length) {
      const p = S.cola.shift();
      try { await animarPalabra(p); } catch (e) { console.error(e); imprimir(p); }  // si falla el dibujo, la palabra igual se muestra
    }
  } finally { S.animando = false; }
  if (!S.corriendo && S.chat && S.mostradas) cerrar();
}
function estado(t, sub = "") { $("estado").innerHTML = `${esc(t)}${sub ? `<small>${esc(sub)}</small>` : ""}`; }
function cerrar() {
  const c = S.chat;
  if (c.fase === "listo") estado("Listo", `${c.palabras.length} palabras · ${c.modo === "replicas" ? "atendió " + c.nodo : "pipeline nodo-a → nodo-b"}`);
  for (const n of ["nodo-a", "nodo-b"]) part(n).removeAttribute("data-caido");
  actualizarBotones();
}

// ---------------------------------------------------------------- servidor
async function api(ruta, cuerpo) {
  const r = await fetch(ruta, cuerpo === undefined ? {} : { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(cuerpo) });
  if (!r.ok) { let m = r.statusText; try { m = (await r.json()).detail || m; } catch (_) {} throw new Error(m); }
  return r.json();
}
async function sondear() {
  try {
    const c = await api("/api/chat");
    if (S.inicio && c.inicio !== S.inicio) throw 0;  // respuesta vieja, de antes de mandar la frase nueva
    S.chat = c;
    S.corriendo = c.fase === "cargando" || c.fase === "generando";
    if (c.fase === "cargando") estado("Preparando el cluster…", "la primera frase, o al cambiar de modo, carga GPT-2 en los nodos");
    if (c.fase === "error") { mostrarError(c.error); S.corriendo = false; }
    if (!S.visto) { S.visto = true; if (!S.corriendo) S.recibidas = c.palabras.length; }  // al abrir la página no se repite la frase anterior
    const nuevas = c.palabras.slice(S.recibidas);
    S.recibidas += nuevas.length;
    S.cola.push(...nuevas);
    reproducir();
    actualizarBotones();
  } catch (_) { /* el servidor puede estar ocupado; se reintenta */ }
  setTimeout(sondear, S.corriendo ? 150 : 600);
}
function actualizarBotones() {
  const ocupado = S.corriendo || S.animando;
  $("completar").disabled = ocupado;
  $("caida").disabled = !(S.corriendo && S.chat?.modo === "replicas" && S.chat.fase === "generando");
  $("caida").hidden = modo() !== "replicas";
  document.querySelectorAll("input[name=modo]").forEach((r) => (r.disabled = ocupado));
}
function mostrarError(m) { const e = $("error"); e.style.display = m ? "block" : "none"; e.textContent = m || ""; }

$("form").onsubmit = async (ev) => {
  ev.preventDefault();
  const texto = $("texto").value.trim() || $("texto").placeholder;
  mostrarError("");
  try {
    const r = await api("/api/chat", { texto, modo: modo(), palabras: S.cuantas });
    S.inicio = r.inicio;
    S.corriendo = true; S.mostradas = 0; S.recibidas = 0; S.cola = [];
    S.chat = { total: S.cuantas, palabras: [], fase: "cargando", modo: modo() };
    $("salida").innerHTML = `<span class="prompt">${esc(texto)}</span>`;
    $("datos").textContent = "";
    textoEn("frase", texto.length > 30 ? "…" + texto.slice(-29) : texto);
    textoEn("cinta", "");
    actualizarBotones();
  } catch (e) { mostrarError(e.message); }
};
$("caida").onclick = () => api("/api/falla", {}).catch((e) => mostrarError(e.message));
$("menos").onclick = () => { S.cuantas = Math.max(1, S.cuantas - 5 + (S.cuantas % 5 ? 5 - S.cuantas % 5 : 0)); $("cuantas").textContent = S.cuantas; };
$("mas").onclick = () => { S.cuantas = Math.min(40, S.cuantas + 5); $("cuantas").textContent = S.cuantas; };
document.querySelectorAll("input[name=modo]").forEach((r) => (r.onchange = () => { prepararModo(); actualizarBotones(); }));

// el dibujo sigue el tema del panel (claro u oscuro)
const oscuro = matchMedia("(prefers-color-scheme: dark)");
const tema = () => $("figura").setAttribute("data-theme", oscuro.matches ? "dark" : "light");
oscuro.addEventListener("change", tema);

let iniciado = false;
window.Frase = {
  mostrar() {
    tema();
    if (iniciado) return;
    iniciado = true;
    cargarFigura().then(() => { estado("Escribí una frase y apretá «Completar»"); textoEn("frase", "Distributed systems are"); sondear(); });
  },
};
})();

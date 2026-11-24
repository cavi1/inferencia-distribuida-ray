// Genera src/panel/figura.svg: el cluster en isométrico para la pestaña «Completá la frase».
// Usa el kit isométrico de la skill anatomy de Claude Code. Para regenerarlo:
//   ANATOMY_KIT=~/.claude/skills/anatomy/kit node herramientas/figura/build.mjs
// La página (chat.js) enciende piezas por data-part y mueve el paquete por los <path data-ruta>.
import { readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { homedir } from "node:os";

const KIT = process.env.ANATOMY_KIT || join(homedir(), ".claude/skills/anatomy/kit");
const k = await import(join(KIT, "iso-kit.mjs"));
const AQUI = dirname(fileURLToPath(import.meta.url));

const W = 900, H = 560;
const PLATE = { x: -240, y: -160, w: 480, d: 320, r: 12 };
const HEAD = { x: -210, y: -140, w: 112, d: 100, r: 5 }, HEAD_H = 66;
const KB = { x: -214, y: 0, w: 76, d: 40, r: 3 };
const SW = { x: -64, y: -6, w: 40, d: 30, r: 3 }, SW_H = 11;
const NA = { x: 70, y: -150, w: 112, d: 92, r: 5 }, NB = { x: 70, y: 8, w: 112, d: 92, r: 5 }, N_H = 46;
const PR = { x: -124, y: 112, w: 34, d: 30, r: 3 }, PR_H = 16;
const TAPE = { x: PR.x + PR.w, y: 119, w: 270, d: 16, r: 1 };
const CAPAS = 12, PITCH = 4.6, LAMINA = 3.2;

const P = k.fitProjection([...k.boxCorners(PLATE, -18, 0), [-154, -90, HEAD_H + 26], [126, -100, N_H + 4 + CAPAS * PITCH + 8], [126, 50, N_H + 4 + CAPAS * PITCH + 8]], W, H, { pad: 18, headroom: 24, azimuth: 40 });
const at = (p) => k.iso(p, P);
const S = (paths, o) => k.solidSvg(paths, o);
const L = (d, o) => k.lineSvg(d, o);
const D = (pts, o) => k.dotsSvg(pts, o);
const T = (m, txt, o) => k.faceTextSvg(m, txt, o);
const part = (name, body, extra = "") => `<g data-part="${name}"${extra}>${body}</g>`;

function plate() {
  const out = [`<path class="iso-halo" d="${k.haloOf(PLATE, -18, 14, P)}"/>`];
  for (const [x, y] of k.corners(PLATE, 26)) out.push(S(k.cylinder(x, y, 8, -18, 2, P, 28), { tone: "lo" }), S(k.cylinder(x, y, 6, -16, 2, P, 28), { tone: "mid" }));
  out.push(S(k.slabOf(PLATE, -14, 14, P, 8, 1.8), { tone: "mid" }));
  out.push(L(k.planOutline(k.insetPlan(PLATE, 6), 0, P), { tone: "lo" }));
  const screws = k.corners(PLATE, 12);
  out.push(L(screws.map(([x, y]) => k.ring(x, y, 2.4, 0, P, 16)).join(""), { tone: "lo" }), D(screws.map(([x, y]) => at([x, y, 0])), { size: 0.55 }));
  const strip = { x: 196, y: -140, w: 8, d: 280, r: 1 };
  out.push(S(k.slabOf(strip, 0, 0.6, P, 3), { tone: "lo", crease: "none" }));
  const ticks = [];
  for (let y = strip.y + 6, i = 0; y <= strip.y + strip.d - 6; y += 5, i++) ticks.push(k.lineOnTop([strip.x + 0.8, y], [strip.x + (i % 5 ? 3 : 5.4), y], 0.6, P));
  out.push(L(ticks.join(""), { tone: "lo" }));
  const tag = { x: -222, y: 64, w: 74, d: 24, r: 2 };
  out.push(S(k.slabOf(tag, 0, 0.8, P, 3), { tone: "lo", crease: "none" }));
  out.push(T(k.topMatrix([tag.x + 5, tag.y + 9], 0.8, P, "x"), "docker compose", { size: 3.8, tone: "mid" }));
  out.push(T(k.topMatrix([tag.x + 5, tag.y + 16], 0.8, P, "x"), "3 servicios · red del host", { size: 2.6, tone: "lo" }));
  out.push(D([at([tag.x + 3, tag.y + 3, 0.8]), at([tag.x + tag.w - 3, tag.y + tag.d - 3, 0.8])], { size: 0.45 }));
  return out.join("");
}

function caja(plan, h, nombre, sub, extra = "") {
  const out = [`<path class="iso-halo" d="${k.haloOf(plan, 0, h, P)}"/>`];
  out.push(S(k.slabOf(plan, 0, h, P, 6, 1.4), { tone: "mid" }));
  out.push(L(k.planOutline(k.insetPlan(plan, 4), h, P, 4), { tone: "faint" }));
  out.push(D(k.corners(plan, 4).map(([x, y]) => at([x, y, h])), { size: 0.5 }));
  const fy = plan.y + plan.d;
  out.push(T(k.sideMatrix([plan.x + 8, fy], h - 10, P, "right"), nombre, { size: 7, tone: "hi" }));
  out.push(T(k.sideMatrix([plan.x + 8, fy], h - 17, P, "right"), sub, { size: 3.4, tone: "lo" }));
  const fx = plan.x + plan.w;
  for (let i = 0; i < 8; i++) out.push(L(k.pathOf([at([fx, plan.y + 14 + i * 4.4, 7]), at([fx, plan.y + 14 + i * 4.4, 19])]), { tone: "lo" }));
  out.push(`<g data-part="leds-${extra}">${D([at([plan.x + 9, fy, 6]), at([plan.x + 15, fy, 6])], { size: 0.9, tone: "hi" })}</g>`);
  return out.join("");
}

function tile(plan, z, h, label, tone = "mid") {
  return S(k.slabOf(plan, z, h, P, 3, 0.5), { tone }) + T(k.topMatrix([plan.x + 3, plan.y + plan.d / 2 + 1.6], z + h, P, "x"), label, { size: 3.6, tone: "mid" });
}

function head() {
  const out = [caja(HEAD, HEAD_H, "ray-head", "0 CPUs · coordina", "head")];
  const z = HEAD_H;
  out.push(part("driver", tile({ x: HEAD.x + 10, y: HEAD.y + 12, w: 34, d: 22, r: 2 }, z, 5, "driver")));
  out.push(part("dashboard", tile({ x: HEAD.x + 10, y: HEAD.y + 46, w: 34, d: 22, r: 2 }, z, 5, ":8265")));
  out.push(part("gcs", S(k.cylinder(HEAD.x + 80, HEAD.y + 26, 13, z, 7, P, 40, 0.6), { tone: "mid" }) + L(k.ring(HEAD.x + 80, HEAD.y + 26, 9, z + 7, P, 32), { tone: "faint" }) + T(k.topMatrix([HEAD.x + 74.5, HEAD.y + 27.5], z + 7, P, "x"), "GCS", { size: 3.6, tone: "mid" })));
  const rt = [HEAD.x + 80, HEAD.y + 70];
  out.push(part("router", S(k.slabOf({ x: rt[0] - 12, y: rt[1] - 12, w: 24, d: 24, r: 3 }, z, 4, P, 3, 0.5), { tone: "mid" }) + S(k.cylinder(rt[0], rt[1], 7, z + 4, 8, P, 32, 0.5), { tone: "hi" }) + L(k.knurl(rt[0], rt[1], 7, z + 6, z + 11, 28, P), { tone: "lo" }) + T(k.topMatrix([rt[0] - 9, rt[1] + 10.5], z + 4, P, "x"), "router", { size: 2.8, tone: "lo" })));
  return out.join("");
}

function teclado() {
  const out = [`<path class="iso-halo" d="${k.haloOf(KB, 0, 6, P)}"/>`];
  out.push(S(k.slabOf(KB, 0, 5, P, 4, 0.7), { tone: "mid" }));
  for (let r = 0; r < 3; r++) for (let c = 0; c < 9; c++) {
    const key = { x: KB.x + 4 + c * 7.7, y: KB.y + 15 + r * 7.6, w: 6.2, d: 6.2, r: 0.9 };
    out.push(S(k.slabOf(key, 5, 2, P, 2, 0.25), { tone: r === 2 && c > 1 && c < 7 ? "mid" : "hi", crease: "none" }));
  }
  const slip = { x: KB.x + 3, y: KB.y + 3, w: KB.w - 6, d: 9, r: 1 };
  out.push(S(k.slabOf(slip, 5, 0.6, P, 2), { tone: "hi", crease: "none" }));
  out.push(`<g data-part="frase">${T(k.topMatrix([slip.x + 2, slip.y + 6.2], 5.6, P, "x"), "", { size: 3.6, tone: "hi" })}</g>`);
  out.push(D(k.corners(KB, 2).map(([x, y]) => at([x, y, 5])), { size: 0.45 }));
  return out.join("");
}

function impresora() {
  const out = [`<path class="iso-halo" d="${k.haloOf(PR, 0, PR_H, P)}"/>`];
  out.push(S(k.slabOf(PR, 0, PR_H, P, 4, 0.9), { tone: "mid" }));
  out.push(L(k.planOutline(k.insetPlan(PR, 3.5), PR_H, P, 2), { tone: "faint" }));
  out.push(S(k.slabOf({ x: PR.x + 6, y: PR.y + 8, w: 22, d: 4, r: 1 }, PR_H, 1.2, P, 2), { tone: "lo", crease: "none" }));
  out.push(D([at([PR.x + 6, PR.y + PR.d, 10]), at([PR.x + 11, PR.y + PR.d, 10])], { size: 0.7, tone: "hi" }));
  out.push(`<g data-part="leds-impresora">${D([at([PR.x + PR.w, PR.y + 8, 11])], { size: 1, tone: "hi" })}</g>`);
  return out.join("");
}

function cinta() {
  const out = [S(k.slabOf(TAPE, 0, 0.5, P, 2), { tone: "hi", crease: "none" })];
  for (let x = TAPE.x + 10; x < TAPE.x + TAPE.w - 4; x += 10) out.push(L(k.lineOnTop([x, TAPE.y + 1.5], [x, TAPE.y + 3], 0.5, P), { tone: "faint" }));
  out.push(`<g data-part="cinta">${T(k.topMatrix([TAPE.x + 4, TAPE.y + 10.6], 0.5, P, "x"), "", { size: 5, tone: "hi" })}</g>`);
  return out.join("");
}

function pila(plan, nodo) {
  const out = [], cx = plan.x + 38, cy = plan.y + 36;
  const cpu = { x: plan.x + 76, y: plan.y + 58, w: 22, d: 20, r: 1.5 };
  out.push(S(k.slabOf(cpu, N_H, 2.4, P, 2, 0.3), { tone: "mid" }) + L(k.planOutline(k.insetPlan(cpu, 3.5), N_H + 2.4, P, 1), { tone: "faint" }) + T(k.topMatrix([cpu.x + 4, cpu.y + 12], N_H + 2.4, P, "x"), "CPU", { size: 3, tone: "lo" }));
  out.push(part(`pila-${nodo}`, apilar({ x: cx - 24, y: cy - 20, w: 48, d: 40, r: 2.5 }, nodo)));
  // segunda pila, oculta: la copia que Ray recrea acá si se apaga el otro nodo (pestaña 4, «Cortar nodo»)
  out.push(part(`pila-${nodo}2`, apilar({ x: plan.x + 72, y: plan.y + 12, w: 32, d: 30, r: 2 }, `${nodo}2`), ' style="display:none"'));
  return out.join("");
}

function apilar(card, id) {
  const out = [S(k.slabOf(k.insetPlan(card, -5), N_H, 4, P, 4, 0.6), { tone: "mid" })];
  for (let i = 0; i < CAPAS; i++) {
    const z = N_H + 4 + i * PITCH;
    out.push(part(`capa-${id}-${i + 1}`, S(k.slabOf(card, z, LAMINA, P, 4, 0.4), { tone: "hi", crease: "lo" })));
  }
  out.push(S(k.slabOf(k.insetPlan(card, 2), N_H + 4 + CAPAS * PITCH, 3, P, 4, 0.5), { tone: "mid" }));
  return out.join("");
}

function nodo(plan, id) {
  return part(`nodo-${id}`, caja(plan, N_H, `nodo-${id}`, `ray-worker · 2 CPUs · recurso nodo_${id}`, id) + pila(plan, id));
}

function sw() {
  return part("switch", `<path class="iso-halo" d="${k.haloOf(SW, 0, SW_H, P)}"/>` + S(k.slabOf(SW, 0, SW_H, P, 3, 0.7), { tone: "mid" }) +
    T(k.topMatrix([SW.x + 4, SW.y + 17], SW_H, P, "x"), "switch", { size: 3.4, tone: "lo" }) +
    D([0, 1, 2, 3].map((i) => at([SW.x + SW.w, SW.y + 7 + i * 5, 6])), { size: 0.8, tone: "hi" }));
}

// recorridos de los cables (sobre la placa, z = 2); los paquetes viajan por estos mismos puntos
const Z = 2;
const RUTAS = {
  head: [[-110, HEAD.y + HEAD.d, Z], [-110, 9, Z], [SW.x, 9, Z]],
  a: [[SW.x + SW.w, 2, Z], [30, 2, Z], [30, -97, Z], [NA.x, -97, Z]],
  b: [[SW.x + SW.w, 16, Z], [NB.x, 16, Z]],
  teclado: [[KB.x + 36, KB.y, Z], [KB.x + 36, HEAD.y + HEAD.d, Z]],
  impresora: [[PR.x + 17, PR.y, Z], [PR.x + 17, HEAD.y + HEAD.d, Z]],
};
const cable = (pts) => k.wireSvg(at(pts[0]), at(pts[pts.length - 1]), { via: pts.slice(1, -1).map(at), tone: "mid", size: 1.3 });
const rutaSvg = (nombre, pts) => `<path data-ruta="${nombre}" d="${k.pathOf(pts.map(at))}" fill="none" stroke="none"/>`;

const body = [
  plate(),
  ...Object.values(RUTAS).map(cable),
  part("head", head()),
  part("teclado", teclado()),
  sw(),
  nodo(NA, "a"),
  part("impresora", impresora()),
  nodo(NB, "b"),
  cinta(),
  ...Object.entries(RUTAS).map(([n, pts]) => rutaSvg(n, pts)),
  `<g data-part="paquetes"></g>`,
];

const svg = k.figureSvg({
  width: W, height: H,
  label: "Cluster Ray en isométrico: ray-head con driver, dashboard, GCS y router; un teclado con la frase escrita y una impresora con la cinta de la respuesta; un switch; nodo-a y nodo-b con las 12 capas de GPT-2 apiladas.",
  body,
});
const css = readFileSync(join(KIT, "iso.css"), "utf8");
const salida = join(AQUI, "../../src/panel/figura.svg");
writeFileSync(salida, svg.replace(/>/, `><style>${css}</style>`));
console.log("escribí", salida);

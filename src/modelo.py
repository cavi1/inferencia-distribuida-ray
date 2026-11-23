"""Carga de GPT-2 y división del modelo en tramos de capas.

GPT-2 small: embeddings -> 12 bloques transformer -> normalización -> cabeza (logits).
Un "tramo" es un rango de bloques; el primero incluye los embeddings y el último
la cabeza. Encadenando tramos se obtiene exactamente el mismo resultado que el
modelo entero (lo verifica la demo 2).
"""
import os

import torch
from transformers import GPT2Config, GPT2LMHeadModel, GPT2TokenizerFast

MODELO = os.environ.get("MODELO", "gpt2")
torch.set_num_threads(int(os.environ.get("HILOS_TORCH", "1")))


def cargar_modelo():
    """Devuelve (modelo, tokenizer). Si no hay pesos descargados usa pesos
    aleatorios con semilla fija: el texto sale sin sentido, pero los tiempos y
    la verificación de igualdad siguen siendo válidos."""
    try:
        modelo = GPT2LMHeadModel.from_pretrained(MODELO, attn_implementation="eager")
        tok = GPT2TokenizerFast.from_pretrained(MODELO)
    except Exception:
        print("[modelo] no se encontraron pesos de", MODELO, "-> uso pesos aleatorios")
        torch.manual_seed(0)
        cfg = GPT2Config()
        cfg._attn_implementation = "eager"
        modelo = GPT2LMHeadModel(cfg)
        tok = None
    modelo.eval()
    return modelo, tok


def cargar_tokenizer():
    try:
        return GPT2TokenizerFast.from_pretrained(MODELO)
    except Exception:
        return None


def codificar(tok, texto):
    if tok is None:
        return torch.tensor([[b % 50257 for b in texto.encode()]])
    return tok(texto, return_tensors="pt").input_ids


def decodificar(tok, ids):
    if tok is None:
        return "ids " + str(ids.tolist()[0][-10:])
    return tok.decode(ids[0])


class Tramo(torch.nn.Module):
    def __init__(self, modelo, desde, hasta):
        super().__init__()
        n = len(modelo.transformer.h)
        self.primero = desde == 0
        self.ultimo = hasta == n
        if self.primero:
            self.wte = modelo.transformer.wte
            self.wpe = modelo.transformer.wpe
        self.bloques = torch.nn.ModuleList(modelo.transformer.h[desde:hasta])
        if self.ultimo:
            self.ln_f = modelo.transformer.ln_f
            self.lm_head = modelo.lm_head

    @torch.no_grad()
    def forward(self, x):
        if self.primero:  # x = ids de tokens
            pos = torch.arange(x.shape[1]).unsqueeze(0)
            x = self.wte(x) + self.wpe(pos)
        for bloque in self.bloques:  # x = estados ocultos
            salida = bloque(x)
            x = salida[0] if isinstance(salida, tuple) else salida
        if self.ultimo:  # x = logits
            x = self.lm_head(self.ln_f(x))
        return x


def generar(paso, ids, n_tokens):
    """Generación greedy: en cada paso se elige el token más probable.
    `paso` es una función ids -> logits (local o distribuida)."""
    for _ in range(n_tokens):
        logits = paso(ids)
        siguiente = logits[:, -1, :].argmax(dim=-1, keepdim=True)
        ids = torch.cat([ids, siguiente], dim=1)
    return ids


def muestrear(logits, ids, generador, temperatura=0.8, top_p=0.9, penalizacion=1.3):
    """Elige el próximo token con azar controlado (para el chat del panel; las demos usan greedy).
    Penaliza los tokens ya usados (evita los bucles de GPT-2) y sortea entre los más probables
    que suman `top_p` de la probabilidad. Con el mismo `generador` da siempre el mismo token."""
    x = logits[0, -1, :].clone()
    usados = ids[0].unique()
    x[usados] = torch.where(x[usados] > 0, x[usados] / penalizacion, x[usados] * penalizacion)
    p = torch.softmax(x / temperatura, dim=-1)
    orden = torch.argsort(p, descending=True)
    acumulada = torch.cumsum(p[orden], dim=0)
    corte = int((acumulada < top_p).sum()) + 1
    elegidos = orden[:corte]
    i = torch.multinomial(p[elegidos] / p[elegidos].sum(), 1, generator=generador)
    return elegidos[i].view(1, 1)

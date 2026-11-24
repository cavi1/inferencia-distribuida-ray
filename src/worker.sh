#!/usr/bin/env bash
# Arranca un worker de Ray con los argumentos que recibe (los de «ray start», sin --block).
# Si Ray se apaga en este nodo (por ejemplo, con «Cortar nodo» del panel), espera VUELTA_NODO
# segundos y lo vuelve a conectar al cluster, como un nodo nuevo.
VUELTA=${VUELTA_NODO:-20}
raylet_vivo() { grep -qsx raylet /proc/[0-9]*/comm; }
while true; do
  if ray start "$@"; then
    while raylet_vivo; do sleep 1; done
    echo "[worker] Ray se apagó en este nodo: se vuelve a conectar en ${VUELTA} s"
  fi
  sleep "$VUELTA"
done

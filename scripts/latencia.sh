#!/usr/bin/env bash
# Agrega latencia a la salida de red de un contenedor, para simular nodos lejanos.
# Uso:  ./scripts/latencia.sh <servicio> <ms>     (ms = 0 quita la latencia)
# Ej.:  ./scripts/latencia.sh ray-worker-2 20
set -e
servicio=${1:?falta el servicio}; ms=${2:?faltan los ms}
if [ "$ms" = "0" ]; then
  docker compose exec "$servicio" tc qdisc del dev eth0 root 2>/dev/null || true
  echo "$servicio: sin latencia agregada"
else
  docker compose exec "$servicio" tc qdisc replace dev eth0 root netem delay "${ms}ms"
  echo "$servicio: +${ms} ms en cada paquete saliente"
fi

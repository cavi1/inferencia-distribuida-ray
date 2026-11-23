# Dos máquinas con red buena — 23 nov 2026, tarde (3 corridas, media ± desvío)
Escritorio por cable (VM 192.168.1.236), notebook en 5 GHz (-44 dBm). RTT 1,3 ms, 628 Mbit/s.
Demo 1 relación n=512/1024/2048/4096: 20,0 / 8,5 / 6,1 / 3,4
Demo 2: logits iguales; ms/token pipeline 242 vs entero 118; 8 pedidos: entero 4,3 s, pipeline de a uno 10,9 s, solapado 9,3 s
Demo 3: 2 réplicas 43,9 s (±1,4); 1 réplica 77,3 s (±9,9); con caída 55,8 s (±4,0), 30/30 x3, recuperación ~20 s
Secuencial: escritorio 66,4 s, notebook 87,0 s
Nota: las 3 primeras "falla" del script no mataron a tiempo (grep con buffer); se repitieron aparte y son las que quedan en los CSV.

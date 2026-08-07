"""
Vigilante: revisa desde fuera si n8n sigue vivo.

Corre en las maquinas de GitHub, NO en el servidor. Si viviera en el mismo
servidor que vigila, el dia que el servidor se caiga tampoco podria avisar.

Termina con codigo 1 cuando algo falla: GitHub lo marca en rojo y manda correo.
"""

import os
import sys
import time
import urllib.request

BASE = os.environ.get("N8N_URL")
if not BASE:
    print("Falta el secreto N8N_URL en el repositorio.")
    sys.exit(1)

URL = BASE.rstrip("/") + "/healthz"
INTENTOS = 3
ESPERA = 20  # segundos entre intentos


def esta_vivo():
    with urllib.request.urlopen(URL, timeout=15) as respuesta:
        return respuesta.status == 200 and b'"ok"' in respuesta.read()


for intento in range(1, INTENTOS + 1):
    try:
        if esta_vivo():
            print(f"Intento {intento}: n8n responde. Todo bien.")
            sys.exit(0)
        print(f"Intento {intento}: contesto, pero no dijo ok.")
    except Exception as error:
        print(f"Intento {intento}: sin respuesta ({type(error).__name__}).")

    if intento < INTENTOS:
        time.sleep(ESPERA)

print("n8n NO responde despues de 3 intentos. Revisa el servidor.")
sys.exit(1)

"""Pruebas del control de separacion de ambientes (ISO/IEC 27001:2022 A.8.31).

Lo que se demuestra aqui es que el control IMPIDE, no que avisa. Antes esto
era una frase en el README, y una frase no detiene un click.

Se prueba sin sesion de Forms: se sustituye la lectura del titulo por titulos
de prueba, incluido uno de produccion. No hace falta -ni seria aceptable-
abrir produccion para comprobar que se rechaza.

    python pruebas_ambiente.py

Codigo 0 si todo pasa, 1 si algo falla.
"""
import os
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
os.environ.setdefault("FORMS_VISION_PROYECTO", r"Z:\Projects")

import nucleo  # noqa: E402
import winauto as w  # noqa: E402

fallos, hechas = [], 0


def comprobar(titulo, condicion, detalle=""):
    global hechas
    hechas += 1
    print(f"  [{'OK' if condicion else 'FALLA'}]  {titulo}"
          + (f"  {detalle}" if detalle else ""))
    if not condicion:
        fallos.append(titulo)


print("=" * 70)
print("PRUEBAS — separacion de ambientes (A.8.31)")
print("=" * 70)

# ── 1. la lectura del titulo ────────────────────────────────────────────────
print("\n1. El ambiente se lee del TITULO, no de la configuracion")
CASOS = [
    ("Administración del Sistema [XENCO/Safix@SAFIXDEMOS/2026-09]", "SAFIXDEMOS"),
    ("Cartera [XENCO/Safix@safixprod/2026-09]", "SAFIXPROD"),
    ("Nomina [OTRO/Safix@SAFIX_QA/2026-09]", "SAFIX_QA"),
    ("Bien Inmueble 346789097612[Binmueb/Desarrollada por XENCO S.A.]", None),
    ("", None),
    (None, None),
]
for t, esperado in CASOS:
    comprobar(f"{str(t)[:44]!r} -> {esperado}", w.ambiente_de(t) == esperado,
              f"dio {w.ambiente_de(t)}")

# ── 2. el control decide ────────────────────────────────────────────────────
print("\n2. El control autoriza y rechaza segun el titulo")
titulo_actual = {"v": ""}
original = w._texto
w._texto = lambda hwnd: titulo_actual["v"]
try:
    titulo_actual["v"] = "X [XENCO/Safix@SAFIXDEMOS/2026-09]"
    amb, motivo = nucleo._ambiente_permitido(0)
    comprobar("SAFIXDEMOS: autorizado", amb == "SAFIXDEMOS" and motivo is None,
              repr(motivo))

    titulo_actual["v"] = "X [XENCO/Safix@SAFIXPROD/2026-09]"
    amb, motivo = nucleo._ambiente_permitido(0)
    comprobar("SAFIXPROD: RECHAZADO", amb == "SAFIXPROD" and motivo is not None)
    comprobar("y el motivo nombra el ambiente y el permitido",
              motivo is not None and "SAFIXPROD" in motivo
              and "SAFIXDEMOS" in motivo)

    # Falla CERRADO: sin ambiente legible, no se actua. Es la diferencia entre
    # un control y una sugerencia.
    titulo_actual["v"] = "una ventana cualquiera sin ambiente"
    amb, motivo = nucleo._ambiente_permitido(0)
    comprobar("titulo sin ambiente: RECHAZADO (falla cerrado)",
              amb is None and motivo is not None)

    titulo_actual["v"] = ""
    amb, motivo = nucleo._ambiente_permitido(0)
    comprobar("titulo vacio: RECHAZADO (falla cerrado)", motivo is not None)

    # ── 3. la lista vacia inhabilita, no abre ───────────────────────────────
    print("\n3. Una lista de permitidos vacia INHABILITA la herramienta")
    real = w.ajustes
    w.ajustes = lambda: {**real(), "ambientes_permitidos": []}
    try:
        titulo_actual["v"] = "X [XENCO/Safix@SAFIXDEMOS/2026-09]"
        amb, motivo = nucleo._ambiente_permitido(0)
        comprobar("sin permitidos, ni SAFIXDEMOS pasa", motivo is not None,
                  (motivo or "")[:46])
    finally:
        w.ajustes = real
finally:
    w._texto = original

# ── 4. el control esta cableado donde se actua ──────────────────────────────
print("\n4. El control esta en los puntos donde se actua")
import inspect  # noqa: E402

import server  # noqa: E402
fuente = inspect.getsource(server)
comprobar("_exigir_frente lo comprueba (paso obligado de toda entrada)",
          "_ambiente_permitido" in inspect.getsource(server._exigir_frente))
comprobar("forms_capturar lo comprueba",
          "_ambiente_permitido" in inspect.getsource(server.forms_capturar))
comprobar("forms_ventanas lo REPORTA (inspeccionar sigue permitido)",
          "_ambiente_permitido" in inspect.getsource(server.forms_ventanas))
comprobar("un rechazo queda en la bitacora (A.8.15)",
          fuente.count('accion="RECHAZADO"') >= 2,
          f"{fuente.count('accion=RECHAZADO'.replace('=', '=\"') + chr(34))} sitios")

print("\n" + "=" * 70)
if fallos:
    print(f"RESULTADO: {len(fallos)} FALLO(S) de {hechas}")
    for f in fallos:
        print(f"   - {f}")
else:
    print(f"RESULTADO: las {hechas} comprobaciones pasan")
print("=" * 70)
sys.exit(1 if fallos else 0)

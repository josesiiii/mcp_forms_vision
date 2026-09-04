"""Pruebas del contrato de exito/fallo de los pasos.

Existe porque la version anterior adivinaba el resultado de un paso buscando
subcadenas en su texto, y eso costo tres defectos en un dia: un lote siguio
despues de una calibracion fallida, despues de un click rechazado y despues de
un recuadro sin cerrar, y en dos casos guardo fotos con el nombre de una lista
que nunca se abrio. Un marcador que falla por una tilde no es una guarda.

    python pruebas_contrato.py

Codigo 0 si todo pasa, 1 si algo falla.
"""
import os
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
os.environ.setdefault("FORMS_VISION_PROYECTO", r"Z:\Projects")

import server  # noqa: E402

fallos, hechas = [], 0


def comprobar(titulo, condicion, detalle=""):
    global hechas
    hechas += 1
    print(f"  [{'OK' if condicion else 'FALLA'}]  {titulo}"
          + (f"  {detalle}" if detalle else ""))
    if not condicion:
        fallos.append(titulo)


print("=" * 70)
print("PRUEBAS — contrato de exito y fallo")
print("=" * 70)

# ── 1. el token manda, sin importar el texto ────────────────────────────────
print("\n1. El token detiene el lote, diga lo que diga el texto")
for texto, esperado in [
    (server._fallo("cualquier cosa"), "cualquier cosa"),
    (server._aviso("foco EQUIVOCADO en (1,2)"), "foco EQUIVOCADO en (1,2)"),
    # Y aqui el caso que antes se escapaba: un fallo redactado de forma que
    # NINGUN marcador de texto reconoceria.
    (server._fallo("el planeta gira al reves"), "el planeta gira al reves"),
]:
    m = server._es_fallo(texto)
    comprobar(f"detecta {texto[:34]!r}", m == esperado, f"-> {m!r}")

comprobar("un token en MITAD de la salida tambien cuenta",
          server._es_fallo("todo bien\n  " + server._aviso("pero no")) == "pero no")

# ── 2. el exito no se confunde ──────────────────────────────────────────────
print("\n2. Lo que salio bien NO detiene el lote")
BUENOS = [
    "foco OK: el resalte cubre el punto pulsado - (122,175) 150x14",
    "ventana activa (224,80) 612x544 -> foto.png  (612x544 px)",
    "encuadre OK: barra de titulo completa en el borde superior",
    "Calibrada binmueb - CNV_TAB/BASICA  escala 1.335",
    "Cerrado el LOV (466x326) con Cancel.",
    "Click izquierdo en ventana (200,184) / pantalla (424,287).",
    "1 recuadro(s) cerrado(s): LOV (466x326) con Cancel.",
    "Esperado 0.5s.",
]
for t in BUENOS:
    m = server._es_fallo(t)
    comprobar(f"pasa {t[:44]!r}", m is None, f"paro por {m!r}" if m else "")

# ── 3. la red de seguridad sigue ahi, y se identifica ───────────────────────
print("\n3. La red de marcadores cubre lo que aun no lleva token")
m = server._es_fallo("Ajuste pobre: 2 encajes con residuo 0.1 px")
comprobar("un texto sin token pero conocido, se detecta", m is not None, repr(m))
comprobar("y dice que fue por marcador, no por contrato",
          m is not None and "sin token" in m)

# ── 4. los retornos reales del codigo llevan token ──────────────────────────
#
# Esta comprobacion es la que de verdad protege: audita el CODIGO, no ejemplos
# escritos a mano. Cuando se anada una herramienta nueva con un retorno de
# fallo sin token, esta prueba lo dira. Ya cazo cuatro que se me escaparon en
# la conversion: forms_abrir, forms_foco, la guarda de riesgo de click_item y
# forms_pendientes.
print("\n4. Los retornos de fallo del codigo llevan el token")
import inspect  # noqa: E402

# Excepciones legitimas, cada una con su razon. No son retornos de herramienta:
EXCEPTUADOS = {
    # _exigir_ventana_datos devuelve un MOTIVO que click_item envuelve en
    # _fallo(). Ponerle token aqui lo duplicaria.
    "no se detecta ninguna ventana activa: no se pulsa a ciegas",
    # "nada que cerrar" NO es un fallo: es un resultado valido de cerrar un
    # recuadro que ya no estaba. Marcarlo detendria lotes correctos.
    "no se detecta ningun recuadro; nada que cerrar.",
}

# Se auditan las CUATRO capas: al partir server.py, los retornos de fallo se
# repartieron entre nucleo, plan y calibra. Una auditoria que mirara solo
# server.py daria un OK enganoso.
import calibra  # noqa: E402
import nucleo  # noqa: E402
import plan  # noqa: E402

CAPAS = {"nucleo": nucleo, "plan": plan, "calibra": calibra, "server": server}
fuente_total = ""
sin_token = []
for nombre, modulo in CAPAS.items():
    fuente = inspect.getsource(modulo)
    fuente_total += fuente
    for linea in fuente.splitlines():
        t = linea.strip()
        if not t.startswith("return ") or "_fallo(" in t or "_aviso(" in t:
            continue
        if any(e in t for e in EXCEPTUADOS):
            continue
        if any(p in t.lower() for p in (
                '"no se ', '"no hay ventanas', '"falta calibrar', '"no existe',
                '"no se detect', 'f"no se pulsa', 'f"no existe',
                'f"no se pudo')):
            sin_token.append(f"{nombre}: {t[:58]}")

comprobar("ningun retorno de fallo se quedo sin token, en las 4 capas",
          not sin_token, f"{len(sin_token)} sueltos de {len(CAPAS)} modulos")
for t in sin_token:
    print(f"         {t}")
comprobar("las 2 excepciones legitimas siguen en el codigo",
          all(e in fuente_total for e in EXCEPTUADOS))

print("\n" + "=" * 70)
if fallos:
    print(f"RESULTADO: {len(fallos)} FALLO(S) de {hechas}")
    for f in fallos:
        print(f"   - {f}")
else:
    print(f"RESULTADO: las {hechas} comprobaciones pasan")
print("=" * 70)
sys.exit(1 if fallos else 0)

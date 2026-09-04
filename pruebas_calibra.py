"""Pruebas del ajuste .fmb -> pixel, con el caso de la rejilla.

Existe por un fallo que no daba ninguna senal y que ya se habia manifestado dos
veces antes de tener nombre:

  * canvas IMAGENES de binmueb: 3 encajes dieron off_y 82 donde lo correcto era
    64, y los clicks salian 27 px bajos
  * fcalifica: 4 encajes dieron off_y 58 donde lo correcto era 39 — 19 px,
    exactamente el alto de una fila de la rejilla

La causa es la misma y es estructural: una rejilla dibuja MUCHAS filas
identicas de los mismos items del .fmb, asi que el ajuste encaja igual de bien
alineado con cualquiera de ellas — mismo numero de aciertos y mismo residuo. El
residuo no puede delatarlo porque solo mide los puntos que encajaron.

Se prueba sin sesion de Forms: se sustituyen la deteccion de pixeles y el
extract por datos sinteticos que reproducen la ambiguedad.

    python pruebas_calibra.py

Codigo 0 si todo pasa, 1 si algo falla.
"""
import os
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
os.environ.setdefault("FORMS_VISION_PROYECTO", r"Z:\Projects")

import calibra  # noqa: E402
import winauto as w  # noqa: E402

fallos, hechas = [], 0


def comprobar(titulo, condicion, detalle=""):
    global hechas
    hechas += 1
    print(f"  [{'OK' if condicion else 'FALLA'}]  {titulo}"
          + (f"  {detalle}" if detalle else ""))
    if not condicion:
        fallos.append(titulo)


# La verdad que se quiere recuperar. Son los numeros reales de fcalifica.
ESCALA, OFF_X, OFF_Y, FILA = 1.33, 3, 39, 19

# Items del .fmb: la fila maestra en y=24 y cuatro columnas de rejilla en y=86.
ITEMS = [
    {"nombre": "VKPCODIGO_M", "x": "108", "y": "24", "ancho": "89",
     "canvas": "C", "tab_page": "", "visible": "true"},
    {"nombre": "VRNOMBRE", "x": "212", "y": "24", "ancho": "342",
     "canvas": "C", "tab_page": "", "visible": "true"},
    {"nombre": "COD", "x": "12", "y": "86", "ancho": "93",
     "canvas": "C", "tab_page": "", "visible": "true"},
    {"nombre": "DESC", "x": "105", "y": "86", "ancho": "263",
     "canvas": "C", "tab_page": "", "visible": "true"},
    {"nombre": "TIPO", "x": "368", "y": "86", "ancho": "94",
     "canvas": "C", "tab_page": "", "visible": "true"},
    {"nombre": "CLAS", "x": "461", "y": "86", "ancho": "93",
     "canvas": "C", "tab_page": "", "visible": "true"},
]


def rect(it, fila_n=0):
    """El rectangulo que se veria en pantalla para ese item, en esa fila."""
    x, y, a = int(it["x"]), int(it["y"]), int(it["ancho"])
    return (round(OFF_X + x * ESCALA), round(OFF_Y + y * ESCALA + fila_n * FILA),
            round(a * ESCALA), 14)


def calibrar_con(campos, foco=None):
    """Corre _calibrar con pixeles y extract sinteticos."""
    reales = (w.detectar_ventana_reintentando, w.detectar_campos,
              w.detectar_foco, calibra._items_de, calibra._calib_guardar)
    w.detectar_ventana_reintentando = lambda h, *a, **k: {
        "x": 50, "y": 68, "ancho": 772, "alto": 511, "canvas": (0, 23, 1366, 720)}
    w.detectar_campos = lambda h, v=None, *a, **k: list(campos)
    w.detectar_foco = lambda h, v=None, *a, **k: foco
    calibra._items_de = lambda f, c, t: ITEMS
    calibra._calib_guardar = lambda *a, **k: None
    try:
        return calibra._calibrar("x", "C", "", 1)
    finally:
        (w.detectar_ventana_reintentando, w.detectar_campos,
         w.detectar_foco, calibra._items_de, calibra._calib_guardar) = reales


print("=" * 70)
print("PRUEBAS — ajuste .fmb -> pixel")
print("=" * 70)

# ── 1. la rejilla sola es ambigua, y hay que DECIRLO ────────────────────────
print("\n1. Con solo la rejilla el off_y es ambiguo")
# En pantalla se ven 13 filas de la rejilla y NINGUN campo de la fila maestra
# (en fcalifica uno estaba en gris y el otro amarillo por el foco).
rejilla = [rect(it, n) for n in range(13) for it in ITEMS if it["y"] == "86"]
cal, err = calibrar_con(rejilla)
comprobar("el ajuste no se rechaza (hay encajes de sobra)", err is None, err)
comprobar("pero declara UNA sola altura explicada",
          cal and cal.get("niveles") == 1, cal and cal.get("niveles"))
comprobar("y el off_y elegido es una de las filas, no otra cosa",
          cal and (cal["off_y"] - OFF_Y) % FILA in (0, 1, FILA - 1),
          cal and f"off_y={cal['off_y']} (correcto {OFF_Y})")

# ── 2. con la fila maestra visible, se acierta ──────────────────────────────
print("\n2. Con dos alturas distintas, el off_y queda determinado")
con_maestra = rejilla + [rect(ITEMS[1])]      # VRNOMBRE, ancho 342
cal, err = calibrar_con(con_maestra)
comprobar("se explican DOS alturas", cal and cal["niveles"] == 2,
          cal and cal.get("niveles"))
comprobar("y el off_y es el correcto", cal and abs(cal["off_y"] - OFF_Y) <= 1,
          cal and f"off_y={cal['off_y']} (correcto {OFF_Y})")
comprobar("con la escala correcta", cal and abs(cal["escala"] - ESCALA) <= 0.006,
          cal and cal["escala"])

# ── 3. el campo ENFOCADO cuenta como campo ──────────────────────────────────
print("\n3. El campo con el foco (amarillo) tambien sirve de referencia")
# Es el caso exacto de fcalifica: el unico campo blanco de la fila maestra
# estaba enfocado, se pintaba amarillo y la deteccion de campos no lo veia.
x, y, a, al = rect(ITEMS[0])                  # VKPCODIGO_M, ancho 89
cal, err = calibrar_con(rejilla, foco={"x": x, "y": y, "ancho": a, "alto": al,
                                       "color": (255, 255, 190), "cuantos": 1})
comprobar("el amarillo entra en el ajuste", cal and cal["niveles"] == 2,
          cal and cal.get("niveles"))
comprobar("y rescata el off_y correcto", cal and abs(cal["off_y"] - OFF_Y) <= 1,
          cal and f"off_y={cal['off_y']} (correcto {OFF_Y})")

# ── 4. lo que ya rechazaba, sigue rechazando ────────────────────────────────
print("\n4. Un ajuste sin base sigue rechazandose")
cal, err = calibrar_con([(10, 10, 50, 14), (10, 30, 50, 14)])
comprobar("menos de 3 campos detectados -> fallo declarado",
          cal is None and err is not None and "[FALLO]" in err,
          (err or "")[:58])

cal, err = calibrar_con([(999, 999, 300, 14), (900, 950, 300, 14),
                         (800, 900, 300, 14), (700, 850, 300, 14)])
comprobar("campos que no encajan con nada -> fallo declarado",
          cal is None and err is not None, (err or "")[:58])

# ── 5. el consumidor avisa de la ambiguedad ─────────────────────────────────
print("\n5. forms_calibrar avisa cuando queda una sola altura")
import inspect  # noqa: E402

import server  # noqa: E402
fuente = inspect.getsource(
    getattr(server.forms_calibrar, "fn", None)
    or getattr(server.forms_calibrar, "func", None)
    or server.forms_calibrar)
comprobar("mira cal['niveles']", "niveles" in fuente)
comprobar("y lo saca como AVISO, que detiene el lote",
          "_aviso(" in fuente, "para que forms_secuencia se pare")

print("\n" + "=" * 70)
if fallos:
    print(f"RESULTADO: {len(fallos)} FALLO(S) de {hechas}")
    for f in fallos:
        print(f"   - {f}")
else:
    print(f"RESULTADO: las {hechas} comprobaciones pasan")
print("=" * 70)
sys.exit(1 if fallos else 0)

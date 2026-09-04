"""Pruebas de apartar el recuadro para que la foto diga a QUE campo pertenece.

Una LOV se abre encima del campo que la sirve y lo tapa con su etiqueta. La
foto queda con una lista y sin ninguna pista de a que campo corresponde, y el
lector del manual no puede situarla. Apartandola caben las dos cosas en la
misma imagen y sobra la segunda foto de contexto.

Lo que se prueba aqui es la GEOMETRIA, que es donde esta el riesgo:

  * agarrar la barra de titulo por donde no cierre el recuadro — a la derecha
    esta la X, y un arrastre que empiece ahi lo cierra en vez de moverlo;
  * no dejarlo medio fuera del canvas, porque lo que se sale no se fotografia
    y sus botones quedan donde no se pueden pulsar;
  * no arrastrar la ventana de DATOS creyendo que es un recuadro;
  * avisar cuando el arrastre no movio nada, en vez de dar por hecho que si.

Se prueba sin sesion de Forms: se sustituyen la deteccion, el canvas y el
arrastre por dobles que anotan lo que se les pide.

    python pruebas_mover.py

Codigo 0 si todo pasa, 1 si algo falla.
"""
import os
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
os.environ.setdefault("FORMS_VISION_PROYECTO", r"Z:\Projects")

import nucleo  # noqa: E402
import server  # noqa: E402
import winauto as w  # noqa: E402

fallos, hechas = [], 0


def comprobar(titulo, condicion, detalle=""):
    global hechas
    hechas += 1
    print(f"  [{'OK' if condicion else 'FALLA'}]  {titulo}"
          + (f"  {detalle}" if detalle else ""))
    if not condicion:
        fallos.append(titulo)


# ── dobles ──────────────────────────────────────────────────────────────────
CANVAS = (0, 0, 1366, 697)          # el canvas medido en este equipo
arrastres = []
estado = {"antes": None, "despues": None}

_real = {k: getattr(w, k) for k in
         ("detectar_ventana_reintentando", "canvas_de", "traer_al_frente",
          "arrastrar")}
_real_amb = server._ambiente_permitido
_real_res = server._resolver
_real_bit = server._bitacora


def instalar(antes, despues=None):
    """Prepara la pantalla falsa: el recuadro antes y despues del arrastre."""
    estado["antes"], estado["despues"] = antes, (despues if despues else antes)
    arrastres.clear()
    llamadas = {"n": 0}

    def detectar(hwnd, minimo_ancho=150, **kw):
        llamadas["n"] += 1
        return estado["antes"] if llamadas["n"] == 1 else estado["despues"]

    w.detectar_ventana_reintentando = detectar
    w.canvas_de = lambda h: (CANVAS, None)
    w.traer_al_frente = lambda h: True
    w.arrastrar = lambda *a, **k: arrastres.append(a)
    server._ambiente_permitido = lambda h: ("SAFIXDEMOS", None)
    server._resolver = lambda h=None: 1
    server._bitacora = lambda **k: None


def restaurar():
    for k, v in _real.items():
        setattr(w, k, v)
    server._ambiente_permitido = _real_amb
    server._resolver = _real_res
    server._bitacora = _real_bit


def rect(x, y, ancho, alto):
    return {"x": x, "y": y, "ancho": ancho, "alto": alto}


mover = (getattr(server.forms_mover_popup, "fn", None)
         or getattr(server.forms_mover_popup, "func", None)
         or server.forms_mover_popup)

print("=" * 70)
print("PRUEBAS — apartar el recuadro para la foto")
print("=" * 70)

try:
    server._ventana_datos.clear()

    # ── 1. destino absoluto ─────────────────────────────────────────────────
    print("\n1. Con x/y se lleva a esa esquina, y se agarra por la barra")
    # La LOV de SAFIX: 466x326, abierta encima del campo.
    instalar(rect(180, 202, 466, 326), rect(430, 10, 466, 326))
    r = mover(x=430, y=10)
    comprobar("dice de donde a donde lo movio",
              "(180,202) a (430,10)" in r, r[:80])
    comprobar("se arrastro una sola vez", len(arrastres) == 1, str(arrastres))
    if arrastres:
        x0, y0, x1, y1 = arrastres[0]
        comprobar("el punto de agarre cae DENTRO de la barra de titulo",
                  202 <= y0 <= 202 + 19, f"y0={y0}")
        comprobar("y no en la X de la derecha, que cerraria el recuadro",
                  x0 < 180 + 466 * 0.8, f"x0={x0} (borde derecho 646)")
        comprobar("ni en el icono de la izquierda",
                  x0 > 180 + 20, f"x0={x0}")
        comprobar("el desplazamiento es el pedido",
                  (x1 - x0, y1 - y0) == (250, -192), f"({x1-x0},{y1-y0})")
    comprobar("avisa de que OK/Cancel cambiaron de sitio",
              "OK/Cancel" in r and "captura nueva" in r, r[-60:])

    # ── 2. destino relativo ─────────────────────────────────────────────────
    print("\n2. Con dx/dy se desplaza desde donde esta")
    instalar(rect(180, 202, 466, 326), rect(280, 152, 466, 326))
    r = mover(dx=100, dy=-50)
    comprobar("se aplica el desplazamiento", len(arrastres) == 1
              and (arrastres[0][2] - arrastres[0][0],
                   arrastres[0][3] - arrastres[0][1]) == (100, -50),
              str(arrastres))

    # ── 3. no se queda medio fuera ──────────────────────────────────────────
    print("\n3. Un destino imposible se recorta al borde del canvas")
    instalar(rect(180, 202, 466, 326), rect(900, 371, 466, 326))
    r = mover(x=1300, y=600)
    comprobar("se recorta a la derecha: 1366-466 = 900",
              "a (900,371)" in r, r[:80])
    comprobar("y abajo: 697-326 = 371", "371" in r, r[:80])

    instalar(rect(180, 202, 466, 326), rect(0, 0, 466, 326))
    r = mover(dx=-500, dy=-500)
    comprobar("tampoco se sale por arriba ni por la izquierda",
              "a (0,0)" in r, r[:80])

    # ── 4. la ventana de datos no se arrastra ───────────────────────────────
    print("\n4. La ventana de datos no es un recuadro")
    server._ventana_datos[1] = (1092, 571)
    instalar(rect(50, 68, 1092, 571))
    r = mover(x=200, y=20)
    comprobar("se niega, y con el token de fallo", r.startswith("[FALLO]"), r[:70])
    comprobar("no se arrastro nada", not arrastres, str(arrastres))
    comprobar("y explica que hay que abrir la LOV primero",
              "Abre la LOV" in r, r[:90])
    server._ventana_datos.clear()

    # Sin referencia aprendida se decide por ancho, igual que al cerrar.
    instalar(rect(50, 68, 1092, 571))
    r = mover(x=200, y=20)
    comprobar("sin referencia, un ancho de ventana de datos tambien se niega",
              r.startswith("[FALLO]"), r[:60])

    # ── 5. nada que mover ───────────────────────────────────────────────────
    print("\n5. Los casos en que no hay nada que hacer")
    instalar(None)
    r = mover(x=200, y=20)
    comprobar("sin recuadro: FALLO y no se arrastra",
              r.startswith("[FALLO]") and not arrastres, r[:60])

    instalar(rect(430, 10, 466, 326))
    r = mover(x=430, y=10)
    comprobar("ya esta en el destino: no se arrastra ni se declara fallo",
              not arrastres and not r.startswith("[FALLO]"), r[:70])

    # ── 6. si el arrastre no surtio efecto, se avisa ─────────────────────────
    print("\n6. Un arrastre sin efecto no se da por bueno")
    instalar(rect(180, 202, 466, 326), rect(180, 202, 466, 326))
    r = mover(x=430, y=10)
    comprobar("lo dice con marca de fallo, que detiene el lote",
              r.startswith("[AVISO]") or r.startswith("[FALLO]"), r[:60])
    comprobar("y propone leer la posicion de una captura",
              "captura" in r, r[-70:])
    # El contrato de verdad es el TOKEN, no el marcador de texto: _es_fallo lo
    # mira primero. Se comprueba con la misma funcion que usa forms_secuencia
    # para decidir, en vez de con una lista de palabras.
    comprobar("forms_secuencia lo trataria como fallo y cortaria el lote",
              nucleo._es_fallo(r) is not None, nucleo._es_fallo(r))

    # Y la inversa, que es el error que ya se cometio una vez con el aviso de
    # CAMBIO MENOR: un resultado CORRECTO no puede detener el lote.
    print("\n6b. Un movimiento que SI funciono no detiene el lote")
    instalar(rect(180, 202, 466, 326), rect(430, 10, 466, 326))
    r_ok = mover(x=430, y=10)
    comprobar("el mensaje de exito no cuenta como fallo",
              nucleo._es_fallo(r_ok) is None, nucleo._es_fallo(r_ok))
    instalar(rect(430, 10, 466, 326))
    r_ya = mover(x=430, y=10)
    comprobar("ni el de 'ya estaba en su sitio'",
              nucleo._es_fallo(r_ya) is None, nucleo._es_fallo(r_ya))
finally:
    restaurar()
    server._ventana_datos.clear()

# ── 7. encadenable y con arrastre de verdad por debajo ──────────────────────
print("\n7. Esta enchufado donde hace falta")
import inspect  # noqa: E402

seq = inspect.getsource(getattr(server.forms_secuencia, "fn", None)
                        or getattr(server.forms_secuencia, "func", None)
                        or server.forms_secuencia)
comprobar("forms_secuencia acepta el paso 'mover'",
          '"mover": forms_mover_popup' in seq)
comprobar("y el docstring ensena la receta de la foto de LOV",
          "mover x=430 y=10" in seq)

arr = inspect.getsource(w.arrastrar)
comprobar("el arrastre va por pasos intermedios (AWT los necesita)",
          "for i in range(1, max(2, pasos)" in arr)
comprobar("baja el boton DESPUES de colocar el puntero",
          arr.index("MOUSEEVENTF_MOVE") < arr.index("MOUSEEVENTF_LEFTDOWN"))
comprobar("y lo suelta al final", "MOUSEEVENTF_LEFTUP" in arr
          and arr.rindex("MOUSEEVENTF_LEFTUP") > arr.index("MOUSEEVENTF_LEFTDOWN"))

print("\n" + "=" * 70)
if fallos:
    print(f"RESULTADO: {len(fallos)} FALLO(S) de {hechas}")
    for f in fallos:
        print(f"   - {f}")
else:
    print(f"RESULTADO: las {hechas} comprobaciones pasan")
print("=" * 70)
sys.exit(1 if fallos else 0)

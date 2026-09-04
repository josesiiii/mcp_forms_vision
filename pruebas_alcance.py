"""Pruebas del analisis de alcance del plan: que se puede fotografiar y que no.

Existe por un defecto que no daba ninguna senal: el plan exigia un llamador a
cada canvas y, como la PANTALLA DE APERTURA no la invoca nadie -Forms la muestra
al abrir la forma-, la clasificaba HUERFANA. El plan decia "0 fotos" y parecia
una respuesta legitima.

Medido en el modulo Portafolio: 6 de 10 formas, 148 items visibles que nunca se
habrian pedido. No salio con binmueb porque su contenido colgaba de tab pages,
que si se reconocen — es decir, la forma de destapar esto era cambiar de modulo,
y una prueba sirve mejor que la suerte.

Se prueba sin sesion de Forms y sin extracts: se sintetizan los JSON minimos que
`_analizar_rutas` necesita, incluidos los dos dialectos reales del .fmb.

    python pruebas_alcance.py

Codigo 0 si todo pasa, 1 si algo falla.
"""
import os
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
os.environ.setdefault("FORMS_VISION_PROYECTO", r"Z:\Projects")

import plan  # noqa: E402

fallos, hechas = [], 0


def comprobar(titulo, condicion, detalle=""):
    global hechas
    hechas += 1
    print(f"  [{'OK' if condicion else 'FALLA'}]  {titulo}"
          + (f"  {detalle}" if detalle else ""))
    if not condicion:
        fallos.append(titulo)


def rutas(ventanas, canvases, codigo="", bloques=None, trig_item=None):
    """Corre el analisis sobre un extract sintetico."""
    datos = {
        "01_bloques.json": bloques or [],
        "07_canvases.json": canvases,
        "11_ventanas.json": ventanas,
        "02_triggers_form.json": [{"nombre": "T", "codigo": codigo}],
        "03_triggers_bloque.json": [],
        "04_triggers_item.json": trig_item or [],
        "06_program_units.json": [],
    }
    return plan._analizar_rutas(lambda f: datos[f])


print("=" * 70)
print("PRUEBAS — alcance: que canvas se puede fotografiar")
print("=" * 70)

# ── 1. los dos dialectos reales de ventana raiz ─────────────────────────────
print("\n1. La pantalla de apertura se reconoce en los dos dialectos del .fmb")

# Dialecto A — fcalifica: la ventana raiz declara canvas_primario.
r = rutas(
    [{"nombre": "WIN_APLICACION", "canvas_primario": "CNV_CALIFICACIONES",
      "titulo": "Calificaciones Portafolio de Inversiones"}],
    [{"nombre": "CNV_CALIFICACIONES", "tipo": "Content", "ventana": "WIN_APLICACION"}])
comprobar("A) canvas_primario declarado -> es raiz",
          "CNV_CALIFICACIONES" in r["canvas_raiz"], sorted(r["canvas_raiz"]))
comprobar("   y nadie lo invoca, que es justo el caso que fallaba",
          not r["invocadores"].get("CNV_CALIFICACIONES"))

# Dialecto B — fvalora: canvas_primario vacio; la pista es colgar de la raiz.
r = rutas(
    [{"nombre": "WIN_APLICACION", "canvas_primario": "",
      "titulo": "Valoracion de Portafolio"}],
    [{"nombre": "CG$PAGE_1", "tipo": "Tab", "ventana": "WIN_APLICACION"}])
comprobar("B) canvas Tab de la ventana raiz -> es raiz",
          "CG$PAGE_1" in r["canvas_raiz"], sorted(r["canvas_raiz"]))

# ── 2. lo que NO debe colarse como raiz ─────────────────────────────────────
print("\n2. La excepcion no abre la mano con lo demas")
r = rutas(
    [{"nombre": "WIN_APLICACION", "canvas_primario": "GENERAL", "titulo": "X"},
     {"nombre": "WIN_VENTA", "canvas_primario": "VENTA", "titulo": "Venta"}],
    [{"nombre": "GENERAL", "tipo": "Tab", "ventana": "WIN_APLICACION"},
     # Un apilado de la ventana raiz SI necesita que alguien lo muestre: es el
     # caso de INFORMACION/ESTATUS/AUDITORIA en fvalora.
     {"nombre": "AUDITORIA", "tipo": "Stacked", "ventana": "WIN_APLICACION"},
     # El canvas de una ventana secundaria tampoco es raiz.
     {"nombre": "VENTA", "tipo": "Content", "ventana": "WIN_VENTA"},
     # Y un canvas suelto, sin ventana, menos.
     {"nombre": "EMAIL", "tipo": "Content", "ventana": ""}])
comprobar("apilado de la ventana raiz NO es raiz",
          "AUDITORIA" not in r["canvas_raiz"])
comprobar("canvas de ventana secundaria NO es raiz",
          "VENTA" not in r["canvas_raiz"])
comprobar("canvas sin ventana NO es raiz", "EMAIL" not in r["canvas_raiz"])
comprobar("y la raiz de verdad sigue siendo raiz", "GENERAL" in r["canvas_raiz"])

# ── 3. lo que ya funcionaba sigue funcionando ───────────────────────────────
print("\n3. ROTA, HUERFANA y ENCERRADA no se ablandan")
r = rutas(
    [{"nombre": "WIN_APLICACION", "canvas_primario": "GENERAL", "titulo": "X"},
     {"nombre": "WIN_SEC", "canvas_primario": "SEC", "titulo": "Secundaria"}],
    [{"nombre": "GENERAL", "tipo": "Tab", "ventana": "WIN_APLICACION"},
     {"nombre": "SEC", "tipo": "Content", "ventana": "WIN_SEC"},
     {"nombre": "SOLA", "tipo": "Stacked", "ventana": "WIN_APLICACION"},
     {"nombre": "ANIDADA", "tipo": "Stacked", "ventana": "WIN_SEC"}],
    codigo="begin show_view('NO_EXISTE'); show_view('ANIDADA'); end;")
comprobar("ROTA: se detecta invocar algo inexistente",
          "NO_EXISTE" in r["rotas"], sorted(r["rotas"]))
comprobar("HUERFANA: un apilado sin llamador sigue sin camino",
          not r["invocadores"].get("SOLA") and "SOLA" not in r["canvas_raiz"])
comprobar("un trigger de forma NO encierra: es alcanzable",
          r["encerrada"]("ANIDADA") is False)

# ENCERRADA de verdad: el UNICO llamador es un boton que vive en el canvas de
# una ventana secundaria, asi que hay que estar dentro de esa ventana para poder
# pulsarlo. Es el caso WIN_PREDIO <-> WIN_FECHVAL_PREDIOS de binmueb.
r = rutas(
    [{"nombre": "WIN_APLICACION", "canvas_primario": "GENERAL", "titulo": "X"},
     {"nombre": "WIN_SEC", "canvas_primario": "SEC", "titulo": "Secundaria"}],
    [{"nombre": "GENERAL", "tipo": "Tab", "ventana": "WIN_APLICACION"},
     {"nombre": "SEC", "tipo": "Content", "ventana": "WIN_SEC"},
     {"nombre": "ANIDADA", "tipo": "Stacked", "ventana": "WIN_SEC"}],
    bloques=[{"nombre": "B", "items": [
        {"nombre": "BTN_SEC", "canvas": "SEC", "tab_page": ""}]}],
    trig_item=[{"BTN_SEC": {"codigo": "begin show_view('ANIDADA'); end;"}}])
comprobar("ENCERRADA: el unico llamador esta en una ventana secundaria",
          r["encerrada"]("ANIDADA") is True,
          f"llamadores={r['invocadores'].get('ANIDADA')}")
comprobar("sin llamadores, `encerrada` responde False y no revienta",
          r["encerrada"]("NADA_DE_ESTO") is False)

# ── 4. el consumidor lo usa de verdad ───────────────────────────────────────
print("\n4. forms_plan consulta la excepcion antes de descartar")
import inspect  # noqa: E402

import server  # noqa: E402
fuente = inspect.getsource(server.forms_plan)
comprobar("forms_plan lee canvas_raiz", 'rutas["canvas_raiz"]' in fuente)
comprobar("y lo comprueba ANTES de mandar a HUERFANA",
          fuente.index("canvas_raiz") < fuente.index('"HUERFANA"'))
comprobar("la raiz se rotula como pantalla inicial, no como ventana",
          "pantalla inicial" in fuente)
comprobar("VENTANA_RAIZ tiene un solo nombre en el codigo",
          inspect.getsource(plan).count('"WIN_APLICACION"') == 1,
          f"{inspect.getsource(plan).count(chr(34) + 'WIN_APLICACION' + chr(34))} literales")

# ── 6. un canvas mostrado por su VENTANA tambien cuenta ─────────────────────
print("\n6. show_window('WIN_X') hace alcanzable al canvas que cuelga de WIN_X")
# Caso real de fclasinv, con la errata incluida: el canvas se llama
# ESTAUS_DISPONIBLES y la ventana WIN_ESTATUS_DISPONIBLES, asi que ni por
# nombre coincidian.
r = rutas(
    [{"nombre": "WIN_APLICACION", "canvas_primario": "CG$PAGE_1", "titulo": "X"},
     {"nombre": "WIN_ESTATUS_DISPONIBLES", "canvas_primario": "ESTAUS_DISPONIBLES",
      "titulo": "Estatus Disponibles"}],
    [{"nombre": "CG$PAGE_1", "tipo": "Tab", "ventana": "WIN_APLICACION"},
     {"nombre": "ESTAUS_DISPONIBLES", "tipo": "Content",
      "ventana": "WIN_ESTATUS_DISPONIBLES"}],
    codigo="begin show_window('WIN_ESTATUS_DISPONIBLES'); end;")
comprobar("la invocacion de la ventana se registra",
          bool(r["invocadores"].get("WIN_ESTATUS_DISPONIBLES")))
comprobar("y alcanza al canvas, aunque el nombre no coincida",
          bool(r["invocadores"].get("ESTAUS_DISPONIBLES")),
          r["invocadores"].get("ESTAUS_DISPONIBLES"))
comprobar("se anota que llego por la ventana, no por el canvas",
          all(i.get("via_ventana") == "WIN_ESTATUS_DISPONIBLES"
              for i in r["invocadores"].get("ESTAUS_DISPONIBLES", [])))
# Y no se regala alcance a lo que de verdad no lo tiene.
r = rutas(
    [{"nombre": "WIN_APLICACION", "canvas_primario": "CG$PAGE_1", "titulo": "X"},
     {"nombre": "WIN_NADIE", "canvas_primario": "SOLA", "titulo": "Nadie"}],
    [{"nombre": "CG$PAGE_1", "tipo": "Tab", "ventana": "WIN_APLICACION"},
     {"nombre": "SOLA", "tipo": "Content", "ventana": "WIN_NADIE"}])
comprobar("una ventana que nadie invoca deja su canvas sin alcance",
          not r["invocadores"].get("SOLA") and "SOLA" not in r["canvas_raiz"])

print("\n" + "=" * 70)
if fallos:
    print(f"RESULTADO: {len(fallos)} FALLO(S) de {hechas}")
    for f in fallos:
        print(f"   - {f}")
else:
    print(f"RESULTADO: las {hechas} comprobaciones pasan")
print("=" * 70)
sys.exit(1 if fallos else 0)

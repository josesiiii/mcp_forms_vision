"""Pruebas del parser de forms_secuencia: como se leen los `clave=valor`.

Existe por dos defectos del mismo sitio:

  * el tipo se adivinaba del ASPECTO del valor, asi que `escribir texto=01`
    se convertia en el int 1 y `w.escribir(1)` moria con "'int' object is not
    iterable". El propio ejemplo del docstring -matricula 346789097612- habria
    fallado igual. Y el fallo silencioso era peor que el ruidoso: '01' -> 1
    teclea OTRO dato en la forma, sin error.
  * un argumento mal escrito se ignoraba y el paso corria con el valor por
    defecto: una `carpeta` mal tecleada guardaba la foto en la carpeta del dia
    y no se sabia hasta ir a buscarla.

Se prueba sin sesion de Forms: se sustituyen las acciones por espias que
apuntan lo que recibieron.

    python pruebas_parser.py

Codigo 0 si todo pasa, 1 si algo falla.
"""
import os
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
os.environ.setdefault("FORMS_VISION_PROYECTO", r"Z:\Projects")

import server  # noqa: E402

fallos, hechas = [], 0
visto = {}


def comprobar(titulo, condicion, detalle=""):
    global hechas
    hechas += 1
    print(f"  [{'OK' if condicion else 'FALLA'}]  {titulo}"
          + (f"  {detalle}" if detalle else ""))
    if not condicion:
        fallos.append(titulo)


# Espias con la MISMA firma que las acciones reales: el parser se apoya en las
# anotaciones, asi que una firma distinta no probaria nada.
def espia_escribir(texto: str, hwnd: str = "") -> str:
    visto["escribir"] = {"texto": texto, "hwnd": hwnd}
    return f"Escritos {len(texto)} caracteres."


def espia_click(x: int, y: int, hwnd: str = "", boton: str = "izquierdo",
                doble: bool = False, relativo: bool = False) -> str:
    visto["click"] = {"x": x, "y": y, "doble": doble, "relativo": relativo}
    return "click ok"


def espia_esperar(segundos: float = 1.0) -> str:
    visto["esperar"] = {"segundos": segundos}
    return "esperado"


def espia_capturar(nombre: str = "", hwnd: str = "", x: int = -1, y: int = -1,
                   ancho: int = -1, alto: int = -1, incluir_marco: bool = False,
                   carpeta: str = "", auto: bool = False,
                   comparar_con: str = "") -> str:
    visto["capturar"] = {"nombre": nombre, "carpeta": carpeta, "auto": auto}
    return "captura ok"


def correr(pasos):
    """Ejecuta forms_secuencia con las acciones espiadas."""
    visto.clear()
    fn = server.forms_secuencia
    fn = getattr(fn, "fn", None) or getattr(fn, "func", None) or fn
    reales = (server.forms_escribir, server.forms_click,
              server.forms_esperar, server.forms_capturar)
    server.forms_escribir, server.forms_click = espia_escribir, espia_click
    server.forms_esperar, server.forms_capturar = espia_esperar, espia_capturar
    try:
        return fn(pasos)
    finally:
        (server.forms_escribir, server.forms_click,
         server.forms_esperar, server.forms_capturar) = reales


print("=" * 70)
print("PRUEBAS — parser de forms_secuencia")
print("=" * 70)

# ── 1. el caso que fallaba ──────────────────────────────────────────────────
print("\n1. Texto que PARECE numero llega como texto")
out = correr("escribir texto=01")
comprobar("`texto=01` llega como '01', no como 1",
          visto.get("escribir", {}).get("texto") == "01",
          repr(visto.get("escribir", {}).get("texto")))
comprobar("y el paso no revienta", "[X]" not in out, out.splitlines()[0])

out = correr("escribir texto=346789097612")
comprobar("la matricula del docstring tampoco se rompe",
          visto.get("escribir", {}).get("texto") == "346789097612",
          repr(visto.get("escribir", {}).get("texto")))

# El cero a la izquierda es lo que hace esto grave: '01' -> 1 no da error, da
# OTRO dato. Un fallo silencioso que teclea mal en un ERP.
out = correr("escribir texto=007")
comprobar("no se pierde el cero a la izquierda",
          visto.get("escribir", {}).get("texto") == "007",
          repr(visto.get("escribir", {}).get("texto")))

# ── 2. lo que SI debe convertirse, se convierte ─────────────────────────────
print("\n2. Los numeros de verdad siguen siendo numeros")
correr("click x=289 y=114 relativo=true")
comprobar("x/y llegan como int", visto["click"]["x"] == 289
          and isinstance(visto["click"]["x"], int), visto["click"])
comprobar("relativo=true llega como bool True",
          visto["click"]["relativo"] is True)
comprobar("doble sin declarar se queda en False",
          visto["click"]["doble"] is False)
correr("esperar segundos=0.6")
comprobar("segundos llega como float 0.6",
          visto["esperar"]["segundos"] == 0.6
          and isinstance(visto["esperar"]["segundos"], float))

# ── 3. rutas con espacios, que fue el defecto anterior ──────────────────────
print("\n3. Las rutas con espacios siguen enteras")
correr('capturar nombre=lov_tipo auto=true '
       r'carpeta=C:\Users\x\Documents\testeo mcp\Portafolio\FCALIFICA')
comprobar("carpeta sin comillas conserva los espacios",
          visto["capturar"]["carpeta"].endswith(r"testeo mcp\Portafolio\FCALIFICA"),
          visto["capturar"]["carpeta"])
comprobar("y auto sigue siendo bool", visto["capturar"]["auto"] is True)

# ── 4. un argumento mal escrito DETIENE el lote ─────────────────────────────
print("\n4. Un argumento que la accion no acepta detiene el lote")
out = correr("capturar nombre=x carpetta=D:\\fotos\nescribir texto=NOTOCAR")
comprobar("el paso se marca como fallo", "[X]" in out or "[FALLO]" in out,
          out.splitlines()[0][:60])
comprobar("dice cual es el argumento malo", "carpetta" in out)
comprobar("y enumera los que si acepta", "comparar_con" in out)
comprobar("el paso siguiente NO se ejecuta", "escribir" not in visto,
          list(visto))

out = correr("click x=uno y=2")
comprobar("un int que no es numero tambien detiene",
          "[X]" in out or "[FALLO]" in out)
comprobar("y dice que se esperaba un int", "int" in out, out.splitlines()[0][:70])

# ── 5. la firma es la fuente del tipo, no una tabla aparte ──────────────────
print("\n5. El tipo sale de la firma de la accion")
import inspect  # noqa: E402
fuente = inspect.getsource(
    getattr(server.forms_secuencia, "fn", None)
    or getattr(server.forms_secuencia, "func", None)
    or server.forms_secuencia)
comprobar("el parser lee inspect.signature", "inspect.signature" in fuente)
comprobar("y ya no adivina con int(v) a ciegas",
          "kwargs[k] = int(v)\n                except ValueError" not in fuente)

print("\n" + "=" * 70)
if fallos:
    print(f"RESULTADO: {len(fallos)} FALLO(S) de {hechas}")
    for f in fallos:
        print(f"   - {f}")
else:
    print(f"RESULTADO: las {hechas} comprobaciones pasan")
print("=" * 70)
sys.exit(1 if fallos else 0)

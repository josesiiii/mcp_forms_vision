"""Pruebas de los AVISOS que guian la pasada de fotos.

Un aviso mal redactado no rompe nada y por eso no se nota: simplemente deja
que quien captura se equivoque igual. Estos son los tres sitios donde de
verdad se equivoco alguien, medidos sobre las formas de Portafolio:

  * IDENTICAS decia solo "nada cambio", y tres veces se dio una LOV por
    bloqueada cuando abria por otra via. Ahora lleva la escalera de gestos.
  * CAMBIO MENOR se leyo como "no paso nada" y casi se descarto un registro
    que SI habia cargado: en una ventana grande, un registro entero da 1,4%.
  * Una captura de region se uso como si fuera del canvas -50 px de mas en x,
    68 en y- y el click cayo en el campo de al lado. Dos veces. Ahora cada
    captura dice de que coordenadas es.

    python pruebas_avisos.py

Codigo 0 si todo pasa, 1 si algo falla.
"""
import inspect
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


def fuente(fn):
    return inspect.getsource(getattr(fn, "fn", None)
                             or getattr(fn, "func", None) or fn)


def plano(s):
    """Une el texto en una sola linea.

    Una prueba que audita fuente NO puede buscar subcadenas literales: el
    salto de linea de un mensaje largo las parte por la mitad y la prueba
    falla aunque el codigo este bien. Paso con dos de las de aqui.
    """
    return " ".join(s.split())


print("=" * 70)
print("PRUEBAS — los avisos que guian la pasada")
print("=" * 70)

cap = fuente(server.forms_capturar)
capp = plano(cap)

# ── 1. IDENTICAS: el unico negativo fiable, y con salida ────────────────────
print("\n1. IDENTICAS detiene el lote Y dice que probar")
comprobar("sigue siendo un _aviso (corta forms_secuencia)",
          '_aviso(' in cap.split('d["veredicto"] == "IDENTICAS"')[1][:900])
for paso in ("FLECHA", "CAMPO", "Ctrl+L", "F9", "doble click"):
    comprobar(f"la escalera nombra {paso!r}", paso in cap)
comprobar("avisa de no generalizar por zona de la pantalla",
          "generalices" in cap and "CAMPO POR CAMPO" in cap)
comprobar("y de mirar si la tabla tiene filas antes de llamarlo defecto",
          "filas antes de llamarlo defecto" in cap)

# ── 2. CAMBIO MENOR: no es un negativo ──────────────────────────────────────
print("\n2. CAMBIO MENOR deja claro que SI pudo pasar algo")
comprobar("dice explicitamente que no significa 'no paso nada'",
          "NO significa que no pasara nada" in cap)
comprobar("da los numeros medidos que lo demuestran",
          "1,4%" in cap and "1,2%" in cap)
comprobar("y remata que solo IDENTICAS es fiable",
          "Solo IDENTICAS" in cap)

# ── 3. de que coordenadas es la imagen ──────────────────────────────────────
print("\n3. Cada captura dice en que coordenadas esta")
comprobar("distingue el canvas completo de un recorte",
          "esta imagen ES el canvas" in cap
          and "empieza en el canvas" in cap)
comprobar("y dice que hay que SUMAR el origen", "SUMALE" in cap)
comprobar("el aviso se anade SIEMPRE, no solo al comparar",
          "avisos.append(marco)" in cap)
comprobar("y menciona relativo=True como alternativa",
          "relativo=True" in cap)

# ── 4. lo que se creia y era falso, corregido ───────────────────────────────
print("\n4. Las afirmaciones falsas de la propia herramienta, corregidas")
cerrar = fuente(server.forms_cerrar_popup)
comprobar("ya NO afirma que ESC no cierra las LOV",
          "ESC no cierra las LOVs" not in cerrar)
comprobar("y recomienda probar ESC primero", "PRUEBA ESC PRIMERO" in cerrar)
comprobar("comparar_con avisa de no comparar una LOV contra otra",
          "no contra la foto anterior de otra LOV" in capp)

# ── 5. el duplicado se sigue cazando ────────────────────────────────────────
print("\n5. Lo que ya funcionaba sigue en su sitio")
comprobar("la deteccion de foto repetida sigue antes del retorno",
          cap.count("_foto_repetida(") == 1 and "os.remove(ruta)" in cap)
comprobar("y el marco no se cuela en el aviso de repetida",
          cap.index("_foto_repetida(") > cap.index("marco ="))

print("\n" + "=" * 70)
if fallos:
    print(f"RESULTADO: {len(fallos)} FALLO(S) de {hechas}")
    for f in fallos:
        print(f"   - {f}")
else:
    print(f"RESULTADO: las {hechas} comprobaciones pasan")
print("=" * 70)
sys.exit(1 if fallos else 0)

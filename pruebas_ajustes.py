"""Pruebas de ajustes.json: que se relea en caliente y que aguante basura.

Lo que se comprueba es exactamente lo que justifica el archivo: cambiarlo NO
debe exigir reiniciar la app, y editarlo mal NO debe dejar la herramienta
inservible en mitad de una corrida.

    python pruebas_ajustes.py

Codigo 0 si todo pasa, 1 si algo falla.
"""
import io
import json
import os
import shutil
import sys
import time

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
os.environ.setdefault("FORMS_VISION_PROYECTO", r"Z:\Projects")

import server  # noqa: E402
import winauto as w  # noqa: E402

RUTA = os.path.join(AQUI, "ajustes.json")
RESPALDO = RUTA + ".prueba-bak"

fallos, hechas = [], 0


def comprobar(titulo, condicion, detalle=""):
    global hechas
    hechas += 1
    print(f"  [{'OK' if condicion else 'FALLA'}]  {titulo}"
          + (f"  {detalle}" if detalle else ""))
    if not condicion:
        fallos.append(titulo)


def escribir(d):
    io.open(RUTA, "w", encoding="utf-8", newline="\n").write(
        json.dumps(d, ensure_ascii=False, indent=2))
    # El cache se invalida por fecha de modificacion: en discos con
    # granularidad de 1 s hay que separar las escrituras.
    time.sleep(0.05)
    os.utime(RUTA, (time.time() + 1, time.time() + 1))


print("=" * 70)
print("PRUEBAS — ajustes.json")
print("=" * 70)
shutil.copy2(RUTA, RESPALDO)
original = json.load(io.open(RUTA, encoding="utf-8"))

try:
    # ── 1. arranque ─────────────────────────────────────────────────────────
    print("\n1. Los valores del archivo llegan al codigo")
    a = w.ajustes()
    comprobar("las 9 claves estan", len(
        [k for k in w.AJUSTES_DEFECTO if k in a]) == 9, f"{len(a)} claves")
    comprobar("sin avisos al leer el archivo bueno",
              w.ajustes_aviso() == "", repr(w.ajustes_aviso()))

    # ── 2. recarga en caliente ──────────────────────────────────────────────
    print("\n2. Un cambio se aplica SIN reiniciar")
    d = dict(original)
    d["rejilla_minima"] = 99
    escribir(d)
    comprobar("rejilla_minima releida", w.ajustes()["rejilla_minima"] == 99,
              str(w.ajustes()["rejilla_minima"]))

    checks = [{"clase": "CHECK?", "etiqueta": f"c{i}"} for i in range(10)]
    comprobar("y el codigo la USA: 10 casillas ya no son rejilla",
              len(server._colapsar_rejilla(list(checks))) == 10)

    d["rejilla_minima"] = 8
    escribir(d)
    comprobar("al volver a 8, 10 casillas si son rejilla",
              len(server._colapsar_rejilla(list(checks))) == 1)

    # ── 3. marcadores de fallo ──────────────────────────────────────────────
    print("\n3. Los marcadores de fallo tambien")
    d["marcas_fallo"] = [["pumpum", "marcador de prueba"]]
    escribir(d)
    comprobar("un marcador nuevo detiene el lote",
              server._es_fallo("todo bien pero pumpum") == "marcador de prueba")
    comprobar("y los viejos ya no, si se quitaron",
              server._es_fallo("OJO foco EQUIVOCADO") is None)
    d["marcas_fallo"] = original["marcas_fallo"]
    escribir(d)
    comprobar("restaurados, OJO vuelve a detener",
              server._es_fallo("OJO foco EQUIVOCADO") is not None)

    # ── 4. umbral del diff ──────────────────────────────────────────────────
    print("\n4. El umbral del diff sale del archivo")
    d["menor_pixeles"] = 1
    escribir(d)
    comprobar("menor_pixeles releido", w.ajustes()["menor_pixeles"] == 1)
    d["menor_pixeles"] = original["menor_pixeles"]
    escribir(d)

    # ── 5. aguante ante basura ──────────────────────────────────────────────
    print("\n5. Un archivo mal editado NO rompe la herramienta")
    io.open(RUTA, "w", encoding="utf-8").write("{ esto no es json ")
    os.utime(RUTA, (time.time() + 2, time.time() + 2))
    a = w.ajustes()
    comprobar("con JSON invalido se usan los valores por defecto",
              a is w.AJUSTES_DEFECTO)
    comprobar("y se avisa del problema", "no se puede leer" in w.ajustes_aviso(),
              w.ajustes_aviso()[:52])
    comprobar("el codigo sigue funcionando",
              server._es_fallo("OJO algo") is not None)

    d = dict(original)
    d["clave_inventada"] = 1
    d["rejilla_minima"] = "ocho"
    escribir(d)
    a = w.ajustes()
    comprobar("una clave desconocida se ignora",
              "clave_inventada" not in a)
    comprobar("un tipo equivocado se ignora y se conserva el bueno",
              a["rejilla_minima"] == original["rejilla_minima"],
              str(a["rejilla_minima"]))
    comprobar("y se dice que se ignoro", "ignorado" in w.ajustes_aviso(),
              w.ajustes_aviso()[:60])

    os.remove(RUTA)
    comprobar("sin archivo, valores por defecto",
              w.ajustes() is w.AJUSTES_DEFECTO)

finally:
    shutil.copy2(RESPALDO, RUTA)
    os.remove(RESPALDO)
    os.utime(RUTA, None)
    w.ajustes()
    print(f"\n  (ajustes.json restaurado; aviso: {w.ajustes_aviso()!r})")

print("\n" + "=" * 70)
if fallos:
    print(f"RESULTADO: {len(fallos)} FALLO(S) de {hechas}")
    for f in fallos:
        print(f"   - {f}")
else:
    print(f"RESULTADO: las {hechas} comprobaciones pasan")
print("=" * 70)
sys.exit(1 if fallos else 0)

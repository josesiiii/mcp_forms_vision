"""Pruebas de lo que existe para NO gastar de mas: duplicados y escala.

Las dos cosas que se prueban aqui salieron de medir el gasto real de una
sesion de fotos, no de imaginarlo:

  * En fmovimie se abrio 'Plan de Cuentas' DOS veces, desde dos campos
    distintos -CGFK$CUENTAS y LOV_TCPLANCUENTAS, dos LOV del .fmb que pintan
    la misma lista de 2.768 filas-. No se supo hasta comparar hashes al final,
    con la forma ya cerrada. Ahora se sabe al guardar.
  * El icono de un boton mide 24x22 px y a ese tamano no se ve. Habia que
    sacarlo a un temporal, ampliarlo por fuera con PIL y volver a guardarlo:
    tres viajes por icono, cinco iconos por modulo.

Se prueba sin sesion de Forms: se sintetizan las imagenes.

    python pruebas_gasto.py

Codigo 0 si todo pasa, 1 si algo falla.
"""
import os
import shutil
import sys
import tempfile

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
os.environ.setdefault("FORMS_VISION_PROYECTO", r"Z:\Projects")

from PIL import Image  # noqa: E402

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


print("=" * 70)
print("PRUEBAS — duplicados y escala")
print("=" * 70)

tmp = tempfile.mkdtemp(prefix="fv_gasto_")
try:
    # ── 1. detectar la foto repetida ────────────────────────────────────────
    print("\n1. Una foto identica a otra de la misma carpeta se detecta")

    def png(nombre, color, tam=(60, 40)):
        p = os.path.join(tmp, nombre)
        Image.new("RGB", tam, color).save(p)
        return p

    a = png("01_lista.png", (10, 60, 120))
    b = png("02_otra_lista.png", (10, 60, 120))      # identica a la anterior
    c = png("03_distinta.png", (200, 30, 30))

    comprobar("la segunda se reconoce como copia de la primera",
              server._foto_repetida(b) == "01_lista.png",
              server._foto_repetida(b))
    comprobar("y la primera tambien apunta a la segunda (simetrico)",
              server._foto_repetida(a) == "02_otra_lista.png",
              server._foto_repetida(a))
    comprobar("una distinta no se marca", server._foto_repetida(c) is None,
              server._foto_repetida(c))

    # Mismo tamano de archivo pero contenido distinto: el atajo por tamano no
    # debe dar un falso positivo.
    d = png("04_casi.png", (10, 60, 121))
    comprobar("dos del mismo peso pero distinto contenido NO son copia",
              server._foto_repetida(d) is None,
              f"{os.path.getsize(d)} vs {os.path.getsize(a)} bytes")

    # Lo que no es .png se ignora, y un archivo que no existe no revienta.
    with open(os.path.join(tmp, "notas.txt"), "wb") as f:
        f.write(open(a, "rb").read())
    comprobar("un .txt con los mismos bytes no cuenta",
              server._foto_repetida(a) == "02_otra_lista.png")
    comprobar("una ruta inexistente devuelve None y no revienta",
              server._foto_repetida(os.path.join(tmp, "nada.png")) is None)

    # Las capturas de TRABAJO empiezan por '_' y es normal que salgan iguales:
    # una base del estado cerrado es identica a la anterior si nada cambio.
    # Tratarlas como duplicado paraba el lote sin motivo.
    borrador = png("_base.png", (10, 60, 120))     # identica a 01_lista.png
    comprobar("una captura de trabajo (empieza por '_') NO se marca",
              server._foto_repetida(borrador) is None,
              server._foto_repetida(borrador))
    comprobar("y tampoco cuenta como gemela de un entregable",
              server._foto_repetida(a) == "02_otra_lista.png",
              server._foto_repetida(a))

    # ── 2. la escala amplia de verdad ───────────────────────────────────────
    print("\n2. La escala amplia la imagen antes de guardarla")
    real = w._grab
    w._grab = lambda l, t, an, al: Image.new("RGB", (an, al), (30, 90, 160))
    try:
        p1 = os.path.join(tmp, "icono_x1.png")
        r, aw1, ah1, av1 = w.capturar_region(0, 0, 34, 32, p1)
        comprobar("sin escala se guarda al tamano real",
                  (aw1, ah1) == (34, 32), (aw1, ah1))
        comprobar("y avisa de RECORTE MINUSCULO",
                  any("MINUSCULO" in x for x in av1))

        p2 = os.path.join(tmp, "icono_x5.png")
        r, aw2, ah2, av2 = w.capturar_region(0, 0, 34, 32, p2, escala=5)
        comprobar("con escala=5 el archivo mide 5 veces mas",
                  (aw2, ah2) == (170, 160), (aw2, ah2))
        comprobar("ya no avisa de recorte minusculo: el archivo no es diminuto",
                  not any("MINUSCULO" in x for x in av2), av2)
        comprobar("y pesa mas que el original",
                  os.path.getsize(p2) > os.path.getsize(p1),
                  f"{os.path.getsize(p2)} vs {os.path.getsize(p1)}")

        p3 = os.path.join(tmp, "icono_x99.png")
        r, aw3, ah3, _ = w.capturar_region(0, 0, 34, 32, p3, escala=99)
        comprobar("la escala se topa en 10 para no generar un PNG absurdo",
                  (aw3, ah3) == (340, 320), (aw3, ah3))

        p4 = os.path.join(tmp, "icono_x0.png")
        r, aw4, ah4, _ = w.capturar_region(0, 0, 34, 32, p4, escala=0.5)
        comprobar("una escala menor que 1 se ignora, no encoge",
                  (aw4, ah4) == (34, 32), (aw4, ah4))
    finally:
        w._grab = real

    # ── 3. forms_capturar usa las dos cosas ─────────────────────────────────
    print("\n3. forms_capturar tiene las dos puestas")
    import inspect  # noqa: E402
    fn = (getattr(server.forms_capturar, "fn", None)
          or getattr(server.forms_capturar, "func", None)
          or server.forms_capturar)
    firma = inspect.signature(fn).parameters
    comprobar("expone el argumento escala", "escala" in firma)
    comprobar("y lo pasa a capturar_region",
              "escala=escala" in inspect.getsource(fn))
    fuente = inspect.getsource(fn)
    comprobar("consulta _foto_repetida", "_foto_repetida(" in fuente)
    comprobar("borra la copia nueva, no la que ya estaba",
              "os.remove(ruta)" in fuente)
    comprobar("y lo devuelve como AVISO, que detiene el lote",
              fuente.index("_foto_repetida") < fuente.index("_aviso(")
              or "_aviso(" in fuente.split("_foto_repetida")[1])
finally:
    shutil.rmtree(tmp, ignore_errors=True)

print("\n" + "=" * 70)
if fallos:
    print(f"RESULTADO: {len(fallos)} FALLO(S) de {hechas}")
    for f in fallos:
        print(f"   - {f}")
else:
    print(f"RESULTADO: las {hechas} comprobaciones pasan")
print("=" * 70)
sys.exit(1 if fallos else 0)

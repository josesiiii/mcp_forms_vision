"""Pruebas de la deteccion por color y de la comparacion de capturas.

Se corren SIN sesion de Forms abierta, con imagenes sintetizadas aqui. Existen
porque las dos piezas que verifican estan puestas justamente para cazar fallos
silenciosos, y una verificacion que se creyera a si misma no serviria de nada:

    python pruebas_deteccion.py

Codigo 0 si todo pasa, 1 si algo falla.
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PIL import Image  # noqa: E402

import winauto as w  # noqa: E402

fallos = []
corridas = 0


def comprobar(titulo, condicion, detalle=""):
    global corridas
    corridas += 1
    print(f"  [{'OK' if condicion else 'FALLA'}]  {titulo}"
          + (f"  {detalle}" if detalle else ""))
    if not condicion:
        fallos.append(titulo)


FONDO = (212, 208, 200)      # gris del canvas de Forms
BLANCO = (255, 255, 255)     # campo habilitado
AMARILLO = (255, 255, 190)   # campo con el foco
GRIS = (192, 192, 192)       # campo deshabilitado


def lienzo(w_, h_, color=FONDO):
    return Image.new("RGB", (w_, h_), color)


def caja(img, x, y, a, al, color):
    for yy in range(y, y + al):
        for xx in range(x, x + a):
            img.putpixel((xx, yy), color)


print("=" * 72)
print("PRUEBAS — deteccion por color y comparacion de capturas")
print("=" * 72)

# ── 1. _rects_por_color separa campos blancos del fondo ──────────────────────
print("\n1. Deteccion de campos blancos")
img = lienzo(400, 200)
caja(img, 20, 30, 120, 20, BLANCO)
caja(img, 20, 70, 120, 20, BLANCO)
caja(img, 200, 30, 60, 20, GRIS)      # deshabilitado: NO debe salir


def blanco(c):
    return c[0] >= 246 and c[1] >= 246 and c[2] >= 246


r = w._rects_por_color(img.load(), 400, 200, blanco, 40, 10)
comprobar("encuentra los 2 campos habilitados", len(r) == 2, f"{len(r)} rects")
comprobar("no confunde el campo gris con uno habilitado",
          all(x < 200 for x, _, _, _ in r))
comprobar("acierta posicion y tamano", (20, 30, 120, 20) in r,
          str(sorted(r)))

# ── 2. El resalte del foco se distingue del blanco ───────────────────────────
print("\n2. Deteccion del foco por su resalte")
img = lienzo(400, 200)
caja(img, 20, 30, 120, 20, BLANCO)
caja(img, 20, 70, 120, 20, AMARILLO)   # este tiene el foco


def resalte(c):
    r_, g_, b_ = c
    return r_ >= 200 and g_ >= 185 and b_ <= min(r_, g_) - 35


f = w._rects_por_color(img.load(), 400, 200, resalte, 25, 9)
comprobar("encuentra exactamente 1 resalte", len(f) == 1, f"{len(f)} rects")
comprobar("es el campo amarillo, no el blanco",
          bool(f) and f[0][1] == 70, str(f))
comprobar("un campo blanco NO cuenta como foco", not resalte(BLANCO))
comprobar("un campo gris NO cuenta como foco", not resalte(GRIS))
comprobar("el fondo del canvas NO cuenta como foco", not resalte(FONDO))

# ── 3. diferencia_png mide el cambio, no solo lo detecta ─────────────────────
print("\n3. Comparacion de capturas")
tmp = tempfile.mkdtemp(prefix="fv_pruebas_")


def guardar(img_, nombre):
    p = os.path.join(tmp, nombre)
    img_.save(p)
    return p


base = lienzo(400, 200)
caja(base, 20, 30, 120, 20, BLANCO)
a = guardar(base, "a.png")

igual = base.copy()
b = guardar(igual, "b.png")
d = w.diferencia_png(a, b)
comprobar("dos capturas iguales -> IDENTICAS", d["veredicto"] == "IDENTICAS",
          str(d["veredicto"]))

menor = base.copy()
caja(menor, 20, 30, 120, 20, GRIS)     # un campo se pone gris: 2400 px de 80000
c = guardar(menor, "c.png")
d = w.diferencia_png(a, c)
comprobar("un campo que cambia -> CAMBIO MENOR",
          d["veredicto"] == "CAMBIO MENOR",
          f"{d['veredicto']} {d['fraccion'] * 100:.2f}%")

grande = base.copy()
caja(grande, 0, 100, 400, 100, BLANCO)  # aparece un panel: la mitad del area
e = guardar(grande, "e.png")
d = w.diferencia_png(a, e)
comprobar("un panel que aparece -> CAMBIO ESTRUCTURAL",
          d["veredicto"] == "CAMBIO ESTRUCTURAL",
          f"{d['veredicto']} {d['fraccion'] * 100:.2f}%")

otro = lienzo(300, 150)
g = guardar(otro, "g.png")
d = w.diferencia_png(a, g)
comprobar("tamanos distintos -> NO COMPARABLES, sin excepcion",
          d["veredicto"] == "NO COMPARABLES" and not d["comparable"],
          str(d["veredicto"]))

# Un cambio de 1 solo pixel NO puede pasar por identico: seria el peor fallo,
# porque el aviso 'nada cambio' es el que detiene el lote.
casi = base.copy()
caja(casi, 300, 150, 6, 6, (0, 0, 0))
h = guardar(casi, "h.png")
d = w.diferencia_png(a, h)
comprobar("un cambio minusculo NO se reporta como IDENTICAS",
          d["veredicto"] != "IDENTICAS", f"{d['veredicto']} {d['pixeles']} px")

# ── 4. El veredicto NO puede depender del tamano de la ventana ───────────────
# Esta es la prueba que hizo falta: con un umbral porcentual, el MISMO cambio
# (un campo que se pone gris) salia CAMBIO MENOR en la ventana de datos y
# CAMBIO ESTRUCTURAL en un recuadro de LOV. El veredicto decide si se toman
# una o dos fotos, asi que no puede depender de donde ocurra.
print("\n4. El veredicto es independiente del tamano")
for etiqueta, (W_, H_) in (("ventana de datos 1300x700", (1300, 700)),
                           ("recuadro de LOV 466x326", (466, 326)),
                           ("lienzo chico 400x200", (400, 200))):
    p0 = lienzo(W_, H_)
    caja(p0, 20, 30, 120, 20, BLANCO)
    r0 = guardar(p0, f"t0_{W_}.png")

    p1 = p0.copy()
    caja(p1, 20, 30, 120, 20, GRIS)          # un campo se deshabilita
    r1 = guardar(p1, f"t1_{W_}.png")
    d1 = w.diferencia_png(r0, r1)

    p2 = p0.copy()
    caja(p2, 0, H_ // 2, W_, H_ // 2, BLANCO)  # aparece un panel
    r2 = guardar(p2, f"t2_{W_}.png")
    d2 = w.diferencia_png(r0, r2)

    comprobar(f"{etiqueta}: un campo -> MENOR",
              d1["veredicto"] == "CAMBIO MENOR",
              f"{d1['veredicto']} {d1['pixeles']} px "
              f"({d1['fraccion'] * 100:.2f}%)")
    comprobar(f"{etiqueta}: un panel -> ESTRUCTURAL",
              d2["veredicto"] == "CAMBIO ESTRUCTURAL",
              f"{d2['veredicto']} {d2['pixeles']} px "
              f"({d2['fraccion'] * 100:.2f}%)")

for n in os.listdir(tmp):
    os.remove(os.path.join(tmp, n))
os.rmdir(tmp)

print("\n" + "=" * 72)
if fallos:
    print(f"RESULTADO: {len(fallos)} FALLO(S) de {corridas} comprobaciones")
    for f_ in fallos:
        print(f"   - {f_}")
else:
    print(f"RESULTADO: las {corridas} comprobaciones pasan")
print("=" * 72)
sys.exit(1 if fallos else 0)

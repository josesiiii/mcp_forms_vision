"""Calibracion: unidades del .fmb -> pixeles de la ventana.

Capa 2. Se ajusta por MEJOR ENCAJE contra los campos blancos detectados,
porque medir dos puntos a ojo deja +-5 px que se propagan y desvian un click
11 px — suficiente para fallar una flecha de LOV de 12 px.
"""

import datetime as dt
import json
import os

import winauto as w
from nucleo import RAIZ, _extract_de, _fallo


CALIBRACIONES = os.path.join(RAIZ, "calibraciones.json")


def _calib_leer():
    if os.path.exists(CALIBRACIONES):
        try:
            return json.load(open(CALIBRACIONES, encoding="utf-8"))
        except (OSError, ValueError):
            return {}
    return {}


# Tamano de la ventana de DATOS por hwnd, aprendido al calibrar (calibrar solo
# tiene sentido sobre la ventana de datos, nunca sobre un recuadro).
#
# Existe por un fallo que costo tres capturas basura: quedo un mensaje encima,
# y click_item calculo el pixel del item respecto al MENSAJE en vez de a la
# ventana de datos. El click se fue a (1014,490), la forma respondio "El campo
# no se puede actualizar", y las tres capturas siguientes se guardaron con
# nombre de LOV. Las coordenadas de un item solo significan algo si delante
# esta la ventana de datos.
_ventana_datos = {}


def _exigir_ventana_datos(hwnd, minimo=0.8):
    """Motivo por el que NO se puede pulsar por coordenadas, o None."""
    v = w.detectar_ventana_reintentando(hwnd)
    if v is None:
        return "no se detecta ninguna ventana activa: no se pulsa a ciegas"
    esperada = _ventana_datos.get(hwnd)
    if esperada is None:
        return None                      # sin referencia todavia: se confia
    area, area_esp = v["ancho"] * v["alto"], esperada[0] * esperada[1]
    if area < area_esp * minimo:
        return (f"hay un recuadro encima ({v['ancho']}x{v['alto']}, y la "
                f"ventana de datos mide {esperada[0]}x{esperada[1]}). Las "
                f"coordenadas del item no valen contra un recuadro: cierralo "
                f"con forms_cerrar_popup y reintenta")
    return None


def _calib_clave(forma, canvas, tab, estado=""):
    """Clave de la calibracion, con el ESTADO dentro.

    El estado va en la clave porque la calibracion se ajusta contra los
    rectangulos BLANCOS de los campos habilitados, y un checkbox que
    deshabilita medio bloque cambia ese juego de referencias. Sin el estado,
    la misma entrada cachearia dos geometrias distintas y los clicks de la
    segunda pasada caerian desplazados, sin ningun error visible.
    """
    return f"{forma.lower()}|{canvas}|{tab}" + (f"|{estado}" if estado else "")


def _calib_guardar(forma, canvas, tab, cal, estado=""):
    d = _calib_leer()
    d[_calib_clave(forma, canvas, tab, estado)] = cal
    with open(CALIBRACIONES, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)


def _items_de(forma, canvas, tab):
    fuera = []
    for b in json.load(open(os.path.join(_extract_de(forma), "01_bloques.json"),
                            encoding="utf-8")):
        for it in (b.get("items") or []):
            if (it.get("canvas") or "") != canvas:
                continue
            if (it.get("tab_page") or "") != tab:
                continue
            if (it.get("visible") or "true").lower() == "false":
                continue
            fuera.append(it)
    return fuera


def _calibrar(forma, canvas, tab, hwnd, estado=""):
    """Ajusta unidades del .fmb -> pixeles buscando el MEJOR ENCAJE.

    Se detectan los campos blancos de la pantalla y se busca la escala y el
    desplazamiento que hacen coincidir el maximo de items declarados, usando
    el residuo como desempate.

    Por que asi y no midiendo dos puntos a mano: medir a ojo deja +-5 px de
    error que se propagan y desvian un click 11 px — suficiente para fallar
    una flecha de LOV de 12 px. Con este ajuste el residuo baja a 0.5 px.

    El ancho se compara con tolerancia AMPLIA: el area blanca no incluye el
    borde del campo, asi que es mas estrecha que el ancho declarado. Lo que
    ajusta es la posicion.
    """
    v = w.detectar_ventana_reintentando(hwnd)
    if v is None:
        return None, _fallo("no se detecta la ventana activa: no se puede "
                            "calibrar.")
    # OJO con el ORDEN: la referencia de "ventana de datos" se apunta al FINAL,
    # cuando el ajuste ya salio bien. Apuntarla aqui envenenaba la guarda: con
    # un mensaje de 321x155 delante, la calibracion fallaba por falta de campos
    # PERO ya habia registrado 321x155 como la ventana de datos, y a partir de
    # ahi forms_cerrar_popup contestaba "delante esta la ventana de datos" con
    # el mensaje encima. Paso el 2026-09-03.
    campos = w.detectar_campos(hwnd, v)
    if len(campos) < 3:
        return None, _fallo(f"solo {len(campos)} campos blancos detectados; hacen falta "
                      "al menos 3. Puede que la seccion no tenga campos "
                      "editables en este estado.")

    esperados = []
    for it in _items_de(forma, canvas, tab):
        try:
            x, y, a = int(it["x"]), int(it["y"]), int(it.get("ancho") or 0)
        except (ValueError, KeyError, TypeError):
            continue
        if a >= 40:
            esperados.append((x, y, a))
    if len(esperados) < 3:
        return None, _fallo("el .fmb declara menos de 3 campos anchos en esta "
                            "seccion.")

    def puntuar(escala, ox, oy):
        aciertos, residuo = 0, 0.0
        for x, y, a in esperados:
            px_, py_, pa = ox + x * escala, oy + y * escala, a * escala
            for cx, cy, ca, _ in campos:
                if abs(cx - px_) <= 3 and abs(cy - py_) <= 4 and abs(ca - pa) <= 30:
                    aciertos += 1
                    residuo += abs(cx - px_) + abs(cy - py_)
                    break
        return aciertos, (residuo / aciertos if aciertos else 1e9)

    mejor = (0, 1e9, None, None, None)
    for e in range(1280, 1400, 5):
        escala = e / 1000.0
        for ox in range(-20, 60):
            for oy in range(20, 130):
                n, res = puntuar(escala, ox, oy)
                if n and ((n > mejor[0]) or (n == mejor[0] and res < mejor[1])):
                    mejor = (n, res, escala, ox, oy)

    n, res, escala, ox, oy = mejor
    if n < 3 or res > 3:
        return None, _fallo(f"ajuste pobre: {n} encajes con residuo {res:.1f} px. "
                      "No se usa para no pulsar a ciegas.")
    cal = {"escala": escala, "off_x": ox, "off_y": oy,
           "encajes": n, "de": len(esperados), "residuo": round(res, 2),
           "fecha": dt.datetime.now().isoformat(timespec="seconds")}
    _calib_guardar(forma, canvas, tab, cal, estado)
    # Ahora si: el ajuste encajo, asi que esta ES la ventana de datos. Se
    # guarda la de MAYOR AREA vista, porque una ventana secundaria puede ser
    # mas ancha (Componentes mide 666x423) pero no mas grande.
    previa = _ventana_datos.get(hwnd)
    if previa is None or v["ancho"] * v["alto"] > previa[0] * previa[1]:
        _ventana_datos[hwnd] = (v["ancho"], v["alto"])
    return cal, None



def _contrastar_calibracion(forma, canvas, tab, estado, cal):
    """Compara el ajuste nuevo con los del mismo canvas y avisa si discrepa."""
    todas = _calib_leer()
    mia = _calib_clave(forma, canvas, tab, estado)
    prefijo = f"{forma.lower()}|{canvas}|"
    otras = [(k, v) for k, v in todas.items()
             if k.startswith(prefijo) and k != mia]
    if not otras:
        return ""
    k, mejor = max(otras, key=lambda kv: kv[1].get("encajes", 0))
    desvia = (abs(mejor["off_x"] - cal["off_x"]) > 3
              or abs(mejor["off_y"] - cal["off_y"]) > 3
              or abs(mejor["escala"] - cal["escala"]) > 0.005)
    if not desvia:
        return ""
    if (cal["encajes"] < w.ajustes()["encajes_fiables"]
            and mejor["encajes"] > cal["encajes"]):
        _calib_guardar(forma, canvas, tab, mejor, estado)
        return ("  OJO: este ajuste discrepa de los demas del canvas y se apoya "
                f"en solo {cal['encajes']} encajes. Se GUARDO en su lugar el de "
                f"'{k}' (escala {mejor['escala']}, off {mejor['off_x']},"
                f"{mejor['off_y']}, {mejor['encajes']} encajes), que es el que "
                "concuerda. Un desplazamiento mal ajustado desvia todos los "
                "clicks sin dar ningun error.")
    return (f"  OJO: discrepa de '{k}' (escala {mejor['escala']}, off "
            f"{mejor['off_x']},{mejor['off_y']}). Comprueba un click antes de "
            "encadenar capturas.")



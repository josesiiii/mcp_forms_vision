"""Nucleo de forms-vision: configuracion, rutas del extract y el contrato de
exito/fallo de los pasos.

Capa 1. Solo depende de winauto (capa 0). Aqui vive lo que necesitan tanto
las herramientas como los modulos de planificacion y calibracion, y por eso
esta separado: si viviera en server.py, plan.py tendria que importar server y
server importar plan.
"""

import glob
import json
import os

import winauto as w


# ── configuracion ────────────────────────────────────────────────────────────

RAIZ = os.path.dirname(os.path.abspath(__file__))
# La raiz del proyecto NO se deduce de la ubicacion del servidor: este puede vivir
# fuera del repo (p.ej. en Z:\J\...), y ahi subir tres niveles da una ruta absurda.
# Se declara con FORMS_VISION_PROYECTO; el salto de tres niveles queda solo como
# respaldo para cuando el servidor si esta dentro del repo.
PROYECTO = os.environ.get(
    "FORMS_VISION_PROYECTO",
    os.path.abspath(os.path.join(RAIZ, "..", "..", "..")))
SALIDA = os.environ.get(
    "FORMS_VISION_SALIDA",
    os.path.join(PROYECTO, "06-frontend", "forms", "_capturas"))
JNLP = os.environ.get("FORMS_VISION_JNLP", r"C:\Scripdominio\SAFIXV4.jnlp")

TECLAS_BLOQUEADAS = {
    t.strip().upper()
    for t in os.environ.get("FORMS_VISION_TECLAS_BLOQUEADAS", "F10,CTRL+S").split(",")
    if t.strip()
}


# Sin esto GetWindowRect miente en pantallas con escalado != 100%, y todas las
# coordenadas de esta herramienta saldrian desplazadas. Se hace al importar el
# nucleo, no en server.py, para que valga tambien cuando se importan los
# modulos desde una prueba.
w.set_dpi_awareness()



def _extract_de(forma):
    """Localiza la carpeta _extract_<forma>_fmb producida por extraer_forma.py."""
    f = forma.lower().removesuffix(".fmb").removesuffix("_fmb")
    patron = os.path.join(PROYECTO, "06-frontend", "forms", "**",
                          f"_extract_{f}_fmb", "01_bloques.json")
    hits = glob.glob(patron, recursive=True)
    if not hits:
        raise FileNotFoundError(
            f"No hay extract de '{forma}'. Genera uno con:\n"
            f"  python 06-frontend/forms/extraer_forma.py <ruta>/{f}.xml")
    return os.path.dirname(hits[0])


def _cargar_items(forma):
    ruta = os.path.join(_extract_de(forma), "01_bloques.json")
    bloques = json.load(open(ruta, encoding="utf-8"))
    items = []
    for b in bloques:
        for it in (b.get("items") or []):
            items.append({**it, "bloque": b.get("nombre")})
    return items, ruta


def _num(valor, defecto=None):
    """Los atributos del .fmb llegan como texto y pueden venir vacios."""
    try:
        return float(str(valor).strip())
    except (TypeError, ValueError):
        return defecto



# ── el contrato: exito y fallo se DECLARAN, no se adivinan del texto ─────────
#
# Las herramientas devuelven texto porque quien las lee es un modelo, no un
# programa. El problema era que devolvian texto TAMBIEN al fallar, asi que el
# lote tenia que adivinar por subcadenas si un paso habia salido bien. Eso
# costo tres defectos reales en un solo dia:
#
#   * la calibracion fallo, el click_item se nego, CTRL+L disparo a ciegas y la
#     captura se guardo con el nombre de una lista que nunca se abrio
#   * el marcador decia "No se detecta" y el mensaje "no se detecto": una
#     tilde de diferencia y el lote siguio
#   * un recuadro no se cerro y los tres pasos siguientes fueron contra el
#
# Ahora cada fallo va prefijado con TOKEN_FALLO y cada aviso que invalida lo
# que venga detras con TOKEN_AVISO. Los tokens son imposibles de producir por
# accidente, y `_es_fallo` los mira antes que cualquier marcador de texto.
#
# La lista de `marcas_fallo` de ajustes.json se queda como RED DE SEGURIDAD:
# cubre lo que no lleve token todavia, y avisa de que lo detecto asi.

TOKEN_FALLO = "[FALLO]"
TOKEN_AVISO = "[AVISO]"


def _fallo(motivo):
    """Un paso que NO se ejecuto o no se pudo completar."""
    return f"{TOKEN_FALLO} {motivo}"


def _aviso(motivo):
    """Un paso que se ejecuto pero invalida lo que venga detras."""
    return f"{TOKEN_AVISO} {motivo}"


def _es_fallo(salida):
    """Motivo por el que un paso cuenta como fallo, o None si fue bien.

    Se mira PRIMERO el token explicito, que es el contrato de verdad. La lista
    de marcadores por texto queda solo de red de seguridad para lo que aun no
    lo lleve, y para los avisos que vienen dentro de una salida por lo demas
    correcta.
    """
    for token, clase in ((TOKEN_FALLO, "fallo"), (TOKEN_AVISO, "aviso")):
        i = salida.find(token)
        if i != -1:
            resto = salida[i + len(token):].strip()
            primera = resto.splitlines()[0] if resto else ""
            return primera[:140] or clase
    bajo = salida.lower()
    for marca, motivo in w.ajustes()["marcas_fallo"]:
        if marca in bajo:
            return f"{motivo} (por marcador de texto, sin token)"
    return None


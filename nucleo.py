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


# ── separacion de ambientes ──────────────────────────────────────────────────
#
# Anexo A 8.31 de ISO/IEC 27001:2022 — separacion de los entornos de
# desarrollo, prueba y produccion. Hasta ahora esto era una frase en el README,
# y una advertencia no impide nada: cualquier click habria entrado igual en
# produccion.
#
# El control lee el ambiente del TITULO de la ventana, no de la configuracion:
# la configuracion dice a que ambiente se quiso apuntar, el titulo dice en cual
# se esta. Y falla CERRADO — si no se puede leer, no se actua.
#
# Deja pasar solo la INSPECCION (forms_ventanas), porque para saber en que
# ambiente estas hay que poder mirar. Todo lo que inyecte entrada o capture
# pantalla pasa por aqui.

def _ambiente_permitido(hwnd):
    """(ambiente, motivo). El motivo es None si se puede actuar."""
    titulo = w._texto(hwnd)
    amb = w.ambiente_de(titulo)
    permitidos = [a.strip().upper()
                  for a in w.ajustes()["ambientes_permitidos"] if a.strip()]
    if not permitidos:
        return amb, ("no hay ningun ambiente permitido en ajustes.json: la "
                     "herramienta queda inhabilitada a proposito")
    if amb is None:
        # Medido el 2026-09-04: SAFIX solo rotula el ambiente en el titulo una
        # vez completado el inicio de sesion con empresa y periodo. Antes de
        # eso el titulo es "XENCO - Administracion del Sistema" y no dice nada.
        # Es una precondicion de trabajo, no un fallo del control.
        return None, (
            f"el titulo de la ventana no declara el ambiente ({titulo[:52]!r}). "
            "No se actua sin saber contra que base se trabaja. SAFIX lo rotula "
            "-como [XENCO/Safix@AMBIENTE/periodo]- cuando el inicio de sesion "
            "esta completo con empresa y periodo: complétalo y reintenta")
    if amb not in permitidos:
        return amb, (
            f"la sesion esta en el ambiente '{amb}' y solo se permite actuar "
            f"en {', '.join(permitidos)}. Esta herramienta inyecta entrada "
            "real: no toca un ambiente no autorizado")
    return amb, None


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


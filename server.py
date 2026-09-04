"""
forms-vision — servidor MCP para ver y manejar Oracle Forms (SAFIX) en Windows.

Que resuelve
------------
El runtime de Forms 12c/14c corre como aplicacion Java (Web Start). Para Windows
es un SunAwtFrame con UN solo hijo, un SunAwtCanvas opaco: no hay arbol de items
que recorrer. Verificado en este equipo el 2026-09-01 con probe_forms.py.

De ahi el reparto de trabajo, que conviene tener claro antes de leer el resto:

    el EXTRACT dice   que existe, como se llega y que es peligroso
    la PANTALLA dice  como se llama cada cosa y si de verdad se dibuja

Los nombres de pestanas, radios y campos se leen de la CAPTURA, no del .fmb:
el extract trae las tab pages con etiqueta vacia, asi que "Basica" o
"Consolidado Niif" no estan ahi — solo los nombres internos (BASICA_E).

Herramientas
------------
  Planificacion  forms_plan · forms_pendientes
  Inspeccion     forms_ventanas · forms_items · forms_tabs
  Sesion         forms_abrir · forms_foco
  Captura        forms_capturar
  Navegacion     forms_click · forms_escribir · forms_tecla · forms_secuencia

Las capturas se guardan en disco y las herramientas devuelven la RUTA, no la
imagen: una imagen en linea cuesta muchisimo contexto y casi siempre basta con
abrir la que interesa.

Guardas
-------
  * Toda inyeccion de entrada exige que la ventana Forms este en primer plano.
    Evita escribir en la aplicacion equivocada.
  * Las teclas de guardado estan BLOQUEADAS por defecto (ver TECLAS_BLOQUEADAS).
    Es una decision conservadora de esta herramienta, no una regla de Forms:
    ajustala con la variable de entorno FORMS_VISION_TECLAS_BLOQUEADAS.
"""

import datetime as dt
import glob
import inspect
import json
import os
import re
import subprocess
import time

from mcp.server.mcpserver import MCPServer  # mcp 2.x: antes se llamaba FastMCP

import winauto as w


from nucleo import (JNLP, PROYECTO, RAIZ, SALIDA, TECLAS_BLOQUEADAS,
                    TOKEN_AVISO, TOKEN_FALLO, _ambiente_permitido, _aviso,
                    _cargar_items, _extract_de, _es_fallo, _fallo, _num)
import plan
import calibra
from plan import (_analizar_rutas, _clasificar, _clase_control,
                  _colapsar_rangos, _colapsar_rejilla,
                  _elementos_de_seccion, _probablemente_obvio, _slug,
                  _visibilidad_tabs)
from calibra import (CALIBRACIONES, _calib_clave, _calib_guardar,
                     _calib_leer, _calibrar, _contrastar_calibracion,
                     _exigir_ventana_datos, _items_de,
                     _ventana_datos)

# El servidor MCP se declara AQUI, en la capa que expone las herramientas.
# nucleo.py no lo conoce a proposito: asi plan.py y calibra.py se pueden
# importar desde una prueba sin levantar nada de MCP.
mcp = MCPServer("forms-vision")

# La ventana con la que se trabaja, recordada entre llamadas para no exigir el
# hwnd en cada una.
_ultimo_hwnd = None


# ── utilidades ───────────────────────────────────────────────────────────────

def _resolver(hwnd=None):
    """Devuelve el hwnd a usar, recordando el ultimo si no se especifica."""
    global _ultimo_hwnd
    if hwnd:
        _ultimo_hwnd = int(hwnd)
        return _ultimo_hwnd
    wins = w.ventanas_java()
    if not wins:
        raise RuntimeError(
            "No hay ninguna ventana de Forms visible. Abrela con forms_abrir, "
            "o comprueba que la sesion no este minimizada.")
    if _ultimo_hwnd and any(v["hwnd"] == _ultimo_hwnd for v in wins):
        return _ultimo_hwnd
    # Preferir la que esta en primer plano; luego una no minimizada; luego
    # la mas grande. Las minimizadas se incluyen a proposito para poder
    # restaurarlas, pero no son la primera opcion.
    elegida = (next((v for v in wins if v["primer_plano"]), None)
               or next((v for v in wins if not v.get("minimizada")), None)
               or max(wins, key=lambda v: v["ancho"] * v["alto"]))
    _ultimo_hwnd = elegida["hwnd"]
    return _ultimo_hwnd


def _exigir_frente(hwnd):
    # ISO/IEC 27001:2022 A.8.31 — separacion de ambientes. Se comprueba ANTES
    # de traer la ventana al frente: no hay razon para tocar una sesion en la
    # que no se puede actuar. Es el paso obligado de todo lo que inyecta
    # entrada, asi que el control esta en un solo sitio.
    amb, motivo = _ambiente_permitido(hwnd)
    _AMBIENTE_VISTO["v"] = amb or "sin-declarar"
    if motivo:
        _bitacora(accion="RECHAZADO", detalle=f"entrada: {motivo[:70]}",
                  nivel="falla")
        raise RuntimeError(f"AMBIENTE NO AUTORIZADO: {motivo}.")
    if w.traer_al_frente(hwnd):
        return
    if w.escritorio_bloqueado():
        raise RuntimeError(
            "La sesión de Windows está BLOQUEADA. Ni se puede teclear ni se "
            "puede capturar: desbloquea el equipo y reintenta.")
    fg = w.ventana_al_frente()
    detalle = f" La ventana al frente es {fg['exe']} ({fg['titulo']!r})." if fg else ""
    raise RuntimeError(
        f"No se pudo poner en primer plano la ventana 0x{hwnd:X}.{detalle} "
        "No se inyecta entrada a ciegas: se abortó para no escribir en otra "
        "aplicación.")


def _foto_repetida(ruta):
    """Nombre de una foto ya guardada IDENTICA a la de `ruta`, o None.

    Existe porque abrir dos veces la misma lista es el gasto mas facil de
    cometer y el mas tarde en notarse: en fmovimie se abrio 'Plan de Cuentas'
    desde dos campos distintos -CGFK$CUENTAS y LOV_TCPLANCUENTAS, dos LOV del
    .fmb que pintan la MISMA lista de 2.768 filas- y no se supo hasta comparar
    los hashes al final, con la forma ya cerrada.
    """
    import hashlib
    try:
        with open(ruta, "rb") as f:
            mio = hashlib.sha256(f.read()).digest()
    except OSError:
        return None
    carpeta = os.path.dirname(os.path.abspath(ruta))
    yo = os.path.basename(ruta)
    try:
        vecinos = sorted(os.listdir(carpeta))
    except OSError:
        return None
    for n in vecinos:
        if n == yo or not n.lower().endswith(".png"):
            continue
        p = os.path.join(carpeta, n)
        try:
            if os.path.getsize(p) != os.path.getsize(ruta):
                continue          # el tamano descarta casi todo sin leer
            with open(p, "rb") as f:
                if hashlib.sha256(f.read()).digest() == mio:
                    return n
        except OSError:
            continue
    return None


def _ruta_salida(nombre=None, sub=None, carpeta=None):
    """Ruta del PNG. Con `carpeta` se guarda ahi; si no, en la carpeta del dia."""
    if carpeta:
        destino = os.path.abspath(carpeta)
    else:
        hoy = dt.date.today().isoformat()
        destino = os.path.join(SALIDA, hoy, sub) if sub else os.path.join(SALIDA, hoy)
    os.makedirs(destino, exist_ok=True)
    base = nombre or f"captura_{dt.datetime.now():%H%M%S_%f}"
    if not base.lower().endswith(".png"):
        base += ".png"
    return os.path.join(destino, base)


BITACORA = os.environ.get(
    "FORMS_VISION_BITACORA",
    os.path.join(SALIDA, "_bitacora"))

# Quien y donde, para el registro de eventos (A.8.15). El usuario sale del
# entorno de Windows: no hay autenticacion propia en esta herramienta, y
# pretender que la hay seria peor que no tenerla.
_QUIEN = os.environ.get("USERNAME") or os.environ.get("USER") or "?"
_PID = os.getpid()
# Ultimo ambiente comprobado, para que cada linea diga contra que base se
# actuo sin volver a leer el titulo en cada anotacion.
_AMBIENTE_VISTO = {"v": "sin-verificar"}

# Ultimo fallo al ESCRIBIR la bitacora.
#
# La escritura se traga sus excepciones a proposito: una captura no debe morir
# porque el log falle. Pero tragarlas EN SILENCIO significaba que la bitacora
# podia estar sin escribir nada y la herramienta seguir diciendo que todo iba
# bien — paso: la ruta apuntaba a una carpeta inexistente y se perdieron todas
# las anotaciones sin una sola senal.
#
# Para A.8.15 eso es un defecto del control, no un detalle: un registro cuyo
# fallo no se puede detectar no sirve como registro. Asi que se traga, pero se
# ANOTA, y forms_ventanas lo saca a la vista.
_BITACORA_FALLO = {"v": ""}


def _bitacora(accion, detalle="", resultado="", avisos=None, nivel="ok"):
    """Anota una linea por accion en un .log del dia.

    Existe porque una corrida de ~90 fotos es larga y desatendida: sin
    registro no hay forma de saber DESPUES que se pidio, que salio y que
    quedo a medias. Escribir la bitacora no debe poder tumbar una captura,
    asi que cualquier fallo aqui se traga a proposito.

    ISO/IEC 27001:2022 A.8.15 — registro de eventos. Cada linea lleva QUIEN
    (usuario de Windows), en QUE SESION (pid del servidor, para separar dos
    corridas del mismo dia) y CONTRA QUE AMBIENTE. Un registro que no dice
    quien ni donde no sirve para reconstruir lo que paso, que es justo para lo
    que se pide un registro.
    """
    try:
        os.makedirs(BITACORA, exist_ok=True)
        ruta = os.path.join(BITACORA, f"{dt.date.today().isoformat()}.log")
        marca = {"ok": "  ", "aviso": "! ", "falla": "XX"}.get(nivel, "  ")
        linea = (f"{dt.datetime.now():%H:%M:%S} {marca} "
                 f"{_QUIEN} pid={_PID} {_AMBIENTE_VISTO['v']:<12} "
                 f"{accion:<14} {detalle}")
        if resultado:
            linea += f"  -> {os.path.basename(str(resultado))}"
        with open(ruta, "a", encoding="utf-8") as f:
            f.write(linea + "\n")
            for a in (avisos or []):
                f.write(f"{'':>9} ..  {a}\n")
        _BITACORA_FALLO["v"] = ""
    except Exception as e:
        # Se traga para no tumbar la captura, pero queda anotado y visible.
        _BITACORA_FALLO["v"] = f"{type(e).__name__}: {e}"


def bitacora_estado():
    """(ruta, problema). El problema es cadena vacia si la bitacora escribe."""
    return BITACORA, _BITACORA_FALLO["v"]



# ── inspeccion ───────────────────────────────────────────────────────────────

@mcp.tool()
def forms_ventanas() -> str:
    """Estado de la sesion de Forms: ventanas, canvas y la ventana MDI activa.

    Es la herramienta de diagnostico: dice si hay sesion, si esta minimizada
    o bloqueada, cual es el origen de coordenadas y donde esta la ventana de
    datos que forms_capturar(auto=True) va a recortar.
    """
    if w.escritorio_bloqueado():
        return _fallo("la sesión de Windows está BLOQUEADA. Desbloquea el equipo: "
                "sin escritorio activo no hay pixeles que leer.")
    wins = w.ventanas_java()
    if not wins:
        return _fallo("no hay ventanas de Forms visibles.")

    out = []
    # A.8.15: la RUTA de la bitacora se muestra SIEMPRE, no solo cuando hay
    # error. El modo de fallo real no es una excepcion: es escribir en el sitio
    # equivocado sin queja. Con FORMS_VISION_SALIDA sin declarar, la ruta se
    # deduce y `os.makedirs` crea alegremente un arbol entero donde no debia —
    # medido: se creo Z:\NoExisteEsteProyecto\06-frontend\... y el registro
    # quedo ahi. Un control de registro tiene que decir DONDE registra.
    ruta_log, problema_log = bitacora_estado()
    out.append(f"bitacora : {ruta_log}")
    if problema_log:
        out.append(f"{TOKEN_AVISO} la bitacora NO escribe ({problema_log}).")
    out.append("")
    for v in wins:
        (cl, ct, cr, cb), _ = w.canvas_de(v["hwnd"])
        amb, motivo = _ambiente_permitido(v["hwnd"])
        lineas = [f"hwnd=0x{v['hwnd']:X}  pid={v['pid']}  {v['clase']}",
                  f"  titulo : {v['titulo']}",
                  f"  ambiente: {amb or '(el titulo no lo declara)'}"
                  + ("   AUTORIZADO" if not motivo else "   NO AUTORIZADO"),
                  f"  frame  : {v['rect']}  ({v['ancho']}x{v['alto']} px)"]
        if motivo:
            lineas.append(f"  {TOKEN_FALLO} {motivo}.")
            lineas.append("  Solo se permite inspeccionar. Ni capturas ni "
                          "clicks ni teclas.")
        if v.get("minimizada"):
            lineas.append("  MINIMIZADA — forms_foco la restaura")
        else:
            lineas.append(f"  canvas : [{cl}, {ct}, {cr}, {cb}]  "
                          f"({cr-cl}x{cb-ct} px)  <- origen de coordenadas")
            det = w.detectar_ventana(v["hwnd"]) if v["primer_plano"] else None
            if det:
                lineas.append(f"  ventana activa : x={det['x']} y={det['y']} "
                              f"{det['ancho']}x{det['alto']}  "
                              f"(lo que recorta auto=True)")
                tabs = w.detectar_tabs(v["hwnd"], det)
                if tabs:
                    lineas.append(f"  tira de pestanas: {len(tabs)} blancos de "
                                  f"click en y={tabs[0]['y']} (relativo)")
        lineas.append(f"  primer plano: {'si' if v['primer_plano'] else 'no'}")
        out.append("\n".join(lineas))
    return "\n\n".join(out)


@mcp.tool()
def forms_items(forma: str, canvas: str = "", contiene: str = "",
                solo_visibles: bool = True) -> str:
    """Inventario de items de una forma, leido del .fmb ya extraido.

    Fuente: 06-frontend/forms/**/_extract_<forma>_fmb/01_bloques.json.
    Si la forma no tiene extract, genera uno antes con extraer_forma.py.

    Args:
        forma: nombre del modulo, p.ej. 'jbieninmueble' (con o sin .fmb).
        canvas: filtra por CanvasName exacto.
        contiene: filtra por subcadena en el nombre del item.
        solo_visibles: excluye los items con Visible=false.
    """
    items, ruta = _cargar_items(forma)
    sel = [
        it for it in items
        if (not canvas or (it.get("canvas") or "").upper() == canvas.upper())
        and (not contiene or contiene.upper() in (it.get("nombre") or "").upper())
        and (not solo_visibles or (it.get("visible") or "true").lower() != "false")
    ]
    if not sel:
        canvases = sorted({it.get("canvas") or "(sin canvas)" for it in items})
        return (f"Ningun item coincide.\nFuente: {ruta}\n"
                f"Canvases disponibles: {', '.join(canvases)}")

    filas = [f"{'ITEM':<28} {'TIPO':<16} {'CANVAS':<16} {'TAB':<14} "
             f"{'ETIQUETA EN PANTALLA':<26} {'LOV':<22}",
             "-" * 126]
    for it in sorted(sel, key=lambda i: (i.get("canvas") or "", _num(i.get("y"), 0),
                                         _num(i.get("x"), 0))):
        # Se muestra el PROMPT, que es la etiqueta que el usuario ve, porque de
        # ahi sale el nombre del archivo de la foto. Las coordenadas del .fmb ya
        # no se muestran: la ventana se detecta por pixeles y no hacen falta.
        # Truncar: hay tipos largos ('ActiveX Control (Obsolete)') que descuadran.
        filas.append(
            f"{(it.get('nombre') or '')[:28]:<28} {(it.get('tipo_visual') or '')[:16]:<16} "
            f"{(it.get('canvas') or '')[:16]:<16} {(it.get('tab_page') or '')[:14]:<14} "
            f"{(it.get('prompt') or '').strip(': ')[:26]:<26} "
            f"{(it.get('lov_name') or '')[:22]:<22}")
    filas.append(f"\n{len(sel)} items.  Fuente: {ruta}")
    filas.append("La ETIQUETA es el prompt del .fmb: suele coincidir con lo que se "
                 "ve, pero manda la pantalla.")
    return "\n".join(filas)


# ── sesion ───────────────────────────────────────────────────────────────────

@mcp.tool()
def forms_abrir(jnlp: str = "", espera_seg: int = 90) -> str:
    """Lanza SAFIX por Java Web Start y espera a que aparezca la ventana.

    NO responde por ti los dialogos de seguridad ni el aviso de actualizacion
    del JNLP (este .jnlp trae update policy='prompt-run' y all-permissions):
    esos los confirmas tu. Tampoco escribe usuario ni clave.

    Args:
        jnlp: ruta al .jnlp. Por defecto el configurado (FORMS_VISION_JNLP).
        espera_seg: cuanto esperar a que aparezca una ventana Forms nueva.
    """
    ruta = jnlp or JNLP
    if not os.path.exists(ruta):
        return _fallo(f"no existe el archivo JNLP: {ruta}")

    previas = {v["hwnd"] for v in w.ventanas_java()}

    javaws = next(iter(glob.glob(r"C:\Program Files*\Java\jre*\bin\javaws.exe")), None)
    if javaws:
        subprocess.Popen([javaws, ruta], close_fds=True)
        lanzado = javaws
    else:
        os.startfile(ruta)  # deja que Windows resuelva el manejador de .jnlp
        lanzado = "manejador registrado de .jnlp"

    limite = time.time() + espera_seg
    while time.time() < limite:
        time.sleep(1.5)
        nuevas = [v for v in w.ventanas_java() if v["hwnd"] not in previas]
        reales = [v for v in nuevas if v["clase"].startswith("SunAwtFrame")]
        if reales:
            v = reales[0]
            _resolver(v["hwnd"])
            return (f"Ventana Forms lista.\n  hwnd  : 0x{v['hwnd']:X}\n"
                    f"  titulo: {v['titulo']}\n  lanzado con: {lanzado}\n"
                    "Inicia sesion tu mismo; luego usa forms_capturar para ver el estado.")

    return (f"Pasaron {espera_seg}s sin ventana Forms nueva.\n"
            f"Lanzado con: {lanzado}\n"
            "Lo normal es que haya un dialogo de Java Web Start esperando "
            "confirmacion. Atiendelo y vuelve a llamar forms_ventanas.")


@mcp.tool()
def forms_foco(hwnd: str = "") -> str:
    """Trae al frente la ventana de Forms. Obligatorio antes de capturar o teclear.

    Args:
        hwnd: identificador en hex ('0x607F6') o decimal. Vacio = la ultima usada.
    """
    h = _resolver(int(hwnd, 0) if hwnd else None)
    if w.traer_al_frente(h):
        return f"Ventana 0x{h:X} en primer plano."
    # Diagnosticar en vez de dar un mensaje generico: el bloqueo de Windows
    # se confundia con "hay un dialogo modal encima" y costaba vueltas.
    if w.escritorio_bloqueado():
        return ("La sesión de Windows está BLOQUEADA. Desbloquea el equipo: "
                "sin escritorio activo no hay foco que ganar ni pixeles que "
                "capturar.")
    fg = w.ventana_al_frente()
    detalle = f" Tiene el foco {fg['exe']} ({fg['titulo']!r})." if fg else ""
    return _fallo(f"no se logro enfocar 0x{h:X}.{detalle} Puede haber un "
                  "diálogo modal encima, o otra aplicación reteniendo el foco.")


def forms_esperar(segundos: float = 1.0) -> str:
    """Pausa. Util tras una consulta pesada (F8) o al abrir una LOV."""
    segundos = max(0.0, min(float(segundos), 120.0))
    time.sleep(segundos)
    return f"Esperado {segundos}s."


# ── captura ──────────────────────────────────────────────────────────────────

@mcp.tool()
def forms_capturar(nombre: str = "", hwnd: str = "",
                   x: int = -1, y: int = -1, ancho: int = -1, alto: int = -1,
                   incluir_marco: bool = False, carpeta: str = "",
                   auto: bool = False, comparar_con: str = "",
                   escala: float = 1.0) -> str:
    """Fotografia la ventana de Forms, o una zona de ella, y guarda un PNG.

    USA auto=True para las fotos de manual: recorta exactamente la ventana
    MDI activa (pestana, dialogo, LOV o ventana secundaria) sin que tengas
    que medir nada. Es la opcion por defecto recomendada.

    Sin auto y sin x/y/ancho/alto captura toda la superficie de dibujo
    (SunAwtCanvas). Con x/y/ancho/alto captura ese rectangulo, en
    coordenadas RELATIVAS al canvas (0,0 = esquina superior izquierda del
    area de dibujo, no del frame).

    El resultado trae un diagnostico del encuadre (imagen negra, sin
    contraste, barra de titulo completa) para que NO haga falta abrir el
    PNG solo para comprobar que sirve.

    Args:
        nombre: nombre del archivo. Por defecto uno con hora.
        hwnd: ventana objetivo. Vacio = la ultima usada.
        x, y, ancho, alto: recorte en pixeles relativos al canvas. -1 = todo.
        incluir_marco: captura el frame completo con barra de titulo y bordes.
        carpeta: carpeta destino. Vacio = la carpeta del dia bajo FORMS_VISION_SALIDA.
        auto: detecta y recorta la ventana MDI activa. Ignora x/y/ancho/alto.
        comparar_con: ruta de una captura anterior. Mide cuanto cambio la
            pantalla y lo dice: IDENTICAS / CAMBIO MENOR / CAMBIO ESTRUCTURAL.
            Con eso se decide si un control necesita las dos versiones, y se
            caza el caso en que el control NO se movio.
        escala: amplia la imagen antes de guardarla (1..10). Para el ICONO de
            un boton, que mide 24x22 px y a ese tamano no se ve: escala=5.
            Antes habia que sacarlo a un temporal, ampliarlo por fuera y
            volver a guardarlo, tres viajes por icono.

    Si la foto sale IDENTICA a otra que ya esta en la misma carpeta, NO se
    guarda y se avisa con el nombre de la que ya existe. Abrir dos veces la
    misma lista es el gasto mas facil de cometer, y asi se sabe en el momento
    y no al final.
    """
    h = _resolver(int(hwnd, 0) if hwnd else None)
    # A.8.31 + A.8.12: una captura de un ambiente no autorizado saca datos de
    # ese ambiente a un PNG que acaba en un manual. Se comprueba igual que la
    # inyeccion de entrada.
    amb, motivo = _ambiente_permitido(h)
    _AMBIENTE_VISTO["v"] = amb or "sin-declarar"
    if motivo:
        _bitacora(accion="RECHAZADO", detalle="captura: " + motivo[:70],
                  nivel="falla")
        return _fallo(f"ambiente no autorizado: {motivo}.")
    if not w.traer_al_frente(h):
        if w.escritorio_bloqueado():
            return _fallo("la sesión de Windows está BLOQUEADA: solo se capturaria la "
                    "pantalla de bloqueo. Desbloquea el equipo y reintenta.")
        return _fallo("no se pudo poner la ventana en primer plano; la captura saldria "
                "tapada o negra. Cierra el dialogo que este encima y reintenta.")

    (cl, ct, cr, cb), _ = w.canvas_de(h)
    if incluir_marco:
        cl, ct, cr, cb = w.rect(h)

    if auto:
        r = w.rect_ventana_activa(h)
        if r is None:
            return _fallo("no se pudo detectar la ventana activa dentro del canvas. "
                    "La causa mas frecuente NO es la deteccion: es que SAFIX "
                    "este en el menu, sin forma cargada — el menu no tiene "
                    "recuadro que recortar. Abre la forma y reintenta; si ya "
                    "esta abierta, pasa x/y/ancho/alto a mano o captura el "
                    "canvas completo.")
        x, y, ancho, alto = r

    if x >= 0 and y >= 0 and ancho > 0 and alto > 0:
        left, top, ww, hh = cl + x, ct + y, ancho, alto
        # Recortar contra los limites reales del canvas.
        ww = min(ww, cr - left)
        hh = min(hh, cb - top)
        etiqueta = (f"ventana activa ({x},{y}) {ww}x{hh}" if auto
                    else f"zona ({x},{y}) {ww}x{hh}")
    else:
        left, top, ww, hh = cl, ct, cr - cl, cb - ct
        etiqueta = "frame completo" if incluir_marco else "canvas completo"

    destino = _ruta_salida(nombre, carpeta=carpeta or None)
    ruta, aw, ah, avisos = w.capturar_region(left, top, ww, hh, destino,
                                             escala=escala)

    if comparar_con:
        if not os.path.exists(comparar_con):
            avisos.append(f"no se pudo comparar: no existe {comparar_con}")
        else:
            d = w.diferencia_png(comparar_con, ruta)
            if not d["comparable"]:
                avisos.append(f"comparacion: {d['veredicto']} — {d['detalle']}")
            else:
                pct = d["fraccion"] * 100
                avisos.append(
                    f"comparacion contra {os.path.basename(comparar_con)}: "
                    f"{d['veredicto']} ({pct:.2f}% de la superficie)")
                if d["veredicto"] == "IDENTICAS":
                    avisos.append(_aviso(
                        "nada cambio. Si esperabas un cambio, el control NO se "
                        "movio: no sigas la pasada."))
                elif d["veredicto"] == "CAMBIO MENOR":
                    avisos.append("cambio de uno o dos campos: basta UNA foto; "
                                  "el detalle va en el texto del manual.")
                else:
                    avisos.append("cambia lo que el usuario puede hacer: "
                                  "van LAS DOS versiones, con el estado en el nombre.")

    gemela = _foto_repetida(ruta)
    if gemela:
        # Se borra la recien hecha, no la que ya estaba: la primera lleva el
        # nombre que se decidio con la pantalla delante.
        try:
            os.remove(ruta)
        except OSError:
            pass
        _bitacora(accion="capturar", detalle=etiqueta,
                  resultado=f"REPETIDA de {gemela}", nivel="aviso")
        return _aviso(
            f"ESTA FOTO YA LA TENIAS: es identica, pixel a pixel, a "
            f"{gemela}. No se guarda una segunda copia.\n"
            f"  Lo que acabas de abrir ya estaba fotografiado — no vuelvas a "
            f"abrirlo. Dos LOV distintas del .fmb pueden pintar la MISMA "
            f"lista: paso con 'Plan de Cuentas' en fmovimie, que sale de "
            f"CGFK$CUENTAS y de LOV_TCPLANCUENTAS.\n"
            f"  Anotalo como redundante en el .txt de pendientes y sigue.")

    _bitacora(accion="capturar", detalle=etiqueta, resultado=ruta, avisos=avisos)
    cola = ("\n  " + "\n  ".join(avisos)) if avisos else ""
    return f"{etiqueta} -> {ruta}  ({aw}x{ah} px){cola}"


# ── navegacion ───────────────────────────────────────────────────────────────

@mcp.tool()
def forms_click(x: int, y: int, hwnd: str = "", boton: str = "izquierdo",
                doble: bool = False, relativo: bool = False) -> str:
    """Click dentro de la forma.

    Mueve el puntero fisico: es entrada real, porque AWT ignora los mensajes
    sinteticos. Exige que la ventana quede en primer plano.

    USA relativo=True para todo lo que este DENTRO de la ventana de datos
    (pestanas, campos, botones, checkboxes). La ventana MDI se mueve sola
    cuando la forma se reinicializa, y unas coordenadas de canvas tomadas
    antes de ese salto pulsan en el sitio equivocado — pasa de verdad, no es
    teorico. Con relativo=True el origen se recalcula en cada click.

    Deja relativo=False solo para lo que vive FUERA de la ventana de datos:
    la barra de herramientas, la barra de menu o la barra de estado.

    Args:
        x, y: pixeles. Desde la esquina de la ventana activa si relativo=True;
            desde la esquina del canvas si no.
        hwnd: ventana objetivo. Vacio = la ultima usada.
        boton: 'izquierdo' o 'derecho'.
        doble: doble click.
        relativo: interpreta x/y respecto a la ventana MDI activa.
    """
    h = _resolver(int(hwnd, 0) if hwnd else None)
    _exigir_frente(h)
    (cl, ct, cr, cb), _ = w.canvas_de(h)
    if relativo:
        r = w.rect_ventana_activa(h)
        if r is None:
            return ("relativo=True pero no se detecto la ventana activa. "
                    "No se hizo click: seria a ciegas.")
        cl, ct = cl + r[0], ct + r[1]
    sx, sy = cl + int(x), ct + int(y)
    if not (cl <= sx < cr and ct <= sy < cb):
        return (f"({x},{y}) cae fuera del canvas, que mide {cr-cl}x{cb-ct} px. "
                "No se hizo click.")
    w.click(sx, sy, boton=boton, doble=doble)
    time.sleep(0.15)
    marco = "ventana" if relativo else "canvas"
    return (f"Click {boton}{' doble' if doble else ''} en {marco} ({x},{y})"
            f" / pantalla ({sx},{sy}).")


@mcp.tool()
def forms_escribir(texto: str, hwnd: str = "") -> str:
    """Escribe texto en el item que tenga el foco dentro de la forma.

    Escribe caracteres Unicode directamente, asi que no depende de la
    distribucion del teclado. No pulsa Enter ni Tab: usa forms_tecla.
    """
    h = _resolver(int(hwnd, 0) if hwnd else None)
    _exigir_frente(h)
    w.escribir(texto)
    time.sleep(0.1)
    return f"Escritos {len(texto)} caracteres."


@mcp.tool()
def forms_tecla(combinacion: str, repeticiones: int = 1, hwnd: str = "") -> str:
    """Pulsa una tecla o combinacion: 'TAB', 'F8', 'CTRL+S', 'SHIFT+TAB'.

    Teclas validas: F1..F12, ENTER, TAB, ESC, SPACE, BACKSPACE, DELETE,
    INSERT, HOME, END, PAGEUP, PAGEDOWN, UP, DOWN, LEFT, RIGHT, y los
    modificadores CTRL, SHIFT, ALT.

    Hay combinaciones bloqueadas por precaucion (por defecto F10 y CTRL+S,
    candidatas a confirmar/guardar). Es una guarda de esta herramienta, no
    de Forms: se cambia con FORMS_VISION_TECLAS_BLOQUEADAS.

    Sobre el SEMAFORO de la barra de herramientas (aclarado por el usuario
    el 2026-09-02): NO condiciona escribir en los campos. Se puede digitar
    en cualquier momento y en cualquier parte. Lo que importa es el momento
    de GUARDAR, ACTUALIZAR o CAMBIAR DE PAGINA habiendo digitado:

        rojo  -> modo edicion/creacion: guardar MODIFICA los datos
        verde -> modo consulta: lo digitado solo sirve de criterio de busqueda

    Por eso la guarda no esta en el teclear, sino en las teclas de guardado.
    """
    combo = "+".join(p.strip().upper() for p in combinacion.split("+") if p.strip())
    if combo in TECLAS_BLOQUEADAS:
        return (f"'{combo}' esta bloqueada: puede confirmar o guardar cambios en la "
                f"base de datos. Bloqueadas: {', '.join(sorted(TECLAS_BLOQUEADAS))}. "
                "Si de verdad la necesitas, cambia FORMS_VISION_TECLAS_BLOQUEADAS "
                "en la configuracion del MCP y reinicia.")

    h = _resolver(int(hwnd, 0) if hwnd else None)
    _exigir_frente(h)
    n = max(1, min(int(repeticiones), 50))
    for _ in range(n):
        w.pulsar(combo)
        time.sleep(0.08)
    return f"Pulsada {combo}{f' x{n}' if n > 1 else ''}."


@mcp.tool()
def forms_plan(forma: str, seccion: str = "") -> str:
    """Plan COMPLETO de fotos de una forma, decidido solo con el extract.

    Existe para que las decisiones se tomen ANTES de tocar la forma: lee
    todos los JSON de _extract_<forma>_fmb y devuelve exactamente que fotos
    hacen falta, como llegar a cada una, que NO necesita foto y por que, y
    que botones no se pueden pulsar porque escriben en la base de datos.

    Politica de no redundancia aplicada:
      * una foto por tab page con items visibles
      * una foto por canvas apilado con items visibles
      * una foto por ventana secundaria con titulo propio
      * UNA foto representativa de LOV — la ventana de lista de valores es
        estructuralmente identica en todas; el resto se documenta en la
        tabla de campos, no con 50 dialogos iguales
      * los mensajes alcanzables sin escribir, uno por texto distinto
    """
    ruta = _extract_de(forma)
    def cargar(n):
        return json.load(open(os.path.join(ruta, n), encoding="utf-8"))

    bloques = cargar("01_bloques.json")
    canvases = cargar("07_canvases.json")
    ventanas = cargar("11_ventanas.json")
    t_item = cargar("04_triggers_item.json")

    # items visibles agrupados por (canvas, tab)
    destino = {}
    lovs = {}
    for b in bloques:
        for it in (b.get("items") or []):
            if not it.get("canvas") or (it.get("visible") or "true").lower() == "false":
                continue
            destino.setdefault((it["canvas"], it.get("tab_page") or ""), []).append(it)
            if it.get("lov_name"):
                lovs.setdefault(it["lov_name"], []).append(it["nombre"])

    tipo_canvas = {c["nombre"]: c["tipo"] for c in canvases}
    ventana_de = {c["nombre"]: c.get("ventana") or "" for c in canvases}
    titulo_ventana = {v["nombre"]: (v.get("titulo") or "") for v in ventanas}

    # botones y su riesgo
    botones = []
    for bloque, items in t_item.items():
        for item, trs in items.items():
            for tr in trs:
                if "BUTTON-PRESSED" not in (tr.get("nombre") or "").upper():
                    continue
                riesgo, motivo = _clasificar(tr.get("codigo") or "")
                botones.append((item, riesgo, motivo))

    riesgo_boton = {i: (r, m) for i, r, m in botones}
    lov_titulo = {l["nombre"]: (l.get("titulo") or "")
                  for l in cargar("05_lovs.json")}

    # ── detalle de UNA seccion ───────────────────────────────────────────────
    if seccion:
        s = seccion.strip().upper()
        claves = [(cv, tab) for (cv, tab) in destino
                  if s in (cv.upper(), tab.upper())]
        if not claves:
            disponibles = sorted({tab or cv for (cv, tab) in destino})
            return (f"No hay seccion '{seccion}' en {forma}.\n"
                    f"Secciones: {', '.join(disponibles)}")
        det = [f"DETALLE DE SECCION — {forma} · {s}", f"fuente: {ruta}", "",
               "Los nombres son PROPUESTAS a partir del prompt del .fmb.",
               "La etiqueta que manda es la de la PANTALLA: verificala en la captura.",
               ""]
        for cv, tab in sorted(claves):
            elems = _elementos_de_seccion(bloques, lov_titulo, riesgo_boton, cv, tab)
            base = _slug(tab or cv)
            det.append(f"[{cv}{'/' + tab if tab else ''}]  "
                       f"{len(destino[(cv, tab)])} items visibles, "
                       f"{len([e for e in elems if e['clase'] != 'PELIGRO'])} "
                       "elementos que pueden abrir algo")
            det.append(f"   foto de la seccion:  NN_{base}_principal.png")
            det.append("")
            det.append(f"   {'CLASE':<8} {'ETIQUETA EN PANTALLA':<26} "
                       f"{'ARCHIVO PROPUESTO':<40} NOTA")
            det.append("   " + "-" * 108)
            for e in sorted(elems, key=lambda x: (x["clase"], x["etiqueta"])):
                arch = ("—" if e["archivo"] == "—"
                        else f"NN_{base}_{e['archivo']}.png")
                marca = "  [¿OBVIO? omitible]" if e["obvio"] else ""
                det.append(f"   {e['clase']:<8} {e['etiqueta'][:26]:<26} "
                           f"{arch[:40]:<40} {e['nota']}{marca}")
            det.append("")
        det.append("Reglas de nombre (nomenclatura XENCO):")
        det.append("  · el nombre es la RUTA acumulada: pestana_radio_prefijo_elemento")
        det.append("  · del boton NO se fotografia el boton, sino LO QUE ABRE")
        det.append("  · una LOV se nombra por el CAMPO que la abrio, no por el")
        det.append("    titulo del recuadro; si la columna no tiene nombre, se usa")
        det.append("    el titulo del cuadro o lo mas cercano")
        det.append("  · [¿OBVIO?] es solo una sugerencia: si el contenido se adivina")
        det.append("    por la etiqueta del campo, se puede omitir. Decide mirando.")
        return "\n".join(det)

    out = [f"PLAN DE FOTOS — {forma}", f"fuente: {ruta}", ""]

    tabs = [(cv, tab) for (cv, tab) in destino if tab]
    apilados = [(cv, tab) for (cv, tab) in destino
                if not tab and tipo_canvas.get(cv) == "Stacked"]
    contenido = [(cv, tab) for (cv, tab) in destino
                 if not tab and tipo_canvas.get(cv) == "Content"]

    out.append("RESUMEN")
    out.append(f"  bloques {len(bloques)} · tab pages con items {len(tabs)} · "
               f"canvas apilados {len(apilados)} · canvas de ventana {len(contenido)}")
    out.append(f"  LOVs en uso {len(lovs)} · botones con codigo {len(botones)}")
    out.append("")

    # Tab pages que el codigo prende/apaga: no se pueden pedir todas a la vez.
    textos = []
    for archivo in ("02_triggers_form.json", "03_triggers_bloque.json",
                    "04_triggers_item.json", "06_program_units.json"):
        def recolectar(o):
            if isinstance(o, dict):
                for k, v in o.items():
                    if k in ("codigo", "cuerpo") and isinstance(v, str):
                        textos.append(v)
                    else:
                        recolectar(v)
            elif isinstance(o, list):
                for v in o:
                    recolectar(v)
        recolectar(cargar(archivo))
    conmutadas = _visibilidad_tabs(textos)

    n = 0
    out.append("FOTOS REQUERIDAS")
    out.append(f"  {'#':>3}  {'archivo propuesto':<44} {'como llegar':<34} items")
    out.append("  " + "-" * 92)
    condicionales = []
    for cv, tab in sorted(tabs, key=lambda k: k[1]):
        if tab.upper() in conmutadas:
            condicionales.append((cv, tab))
            continue
        n += 1
        out.append(f"  {n:>3}  {(tab.lower()):<44} {'tab ' + tab:<34} "
                   f"{len(destino[(cv, tab)])}")
    rutas = _analizar_rutas(cargar)
    descartadas = []
    for cv, tab in sorted(apilados) + sorted(contenido):
        clave = cv.upper()
        invs = rutas["invocadores"].get(clave, [])
        es_win = (cv, tab) in contenido
        etiqueta = ("win_" if es_win else "apilado_") + cv.lower()
        cuantos = len(destino[(cv, tab)])

        # La pantalla de apertura no la invoca nadie, y exigirle un llamador la
        # mandaba a HUERFANA: la foto que mas falta hacia era justo la que no se
        # pedia. Se comprueba ANTES que la ausencia de invocadores.
        es_raiz = clave in rutas["canvas_raiz"]

        if not invs and not es_raiz:
            descartadas.append((etiqueta, cuantos, "HUERFANA",
                                "existe pero NADIE la invoca en el extract"))
            continue
        if rutas["encerrada"](clave):
            dentro = ", ".join(sorted({i["item"] for i in invs})[:3])
            descartadas.append((etiqueta, cuantos, "ENCERRADA",
                                f"solo se invoca desde otra ventana secundaria ({dentro})"))
            continue

        n += 1
        origen = sorted({f"{i['item']}@{i['tab'] or i['canvas'] or '-'}" for i in invs})
        vt = titulo_ventana.get(ventana_de.get(cv, ""), "") or ventana_de.get(cv, "")
        if es_raiz:
            # Se dice "pantalla inicial" y no "ventana X" porque no hay nada que
            # pulsar para llegar: es lo que se ve al abrir la forma.
            como = f"pantalla inicial{(' — ' + vt) if vt else ''}"
        elif es_win:
            como = f"ventana {vt}"
        else:
            como = f"desde {origen[0]}"
        out.append(f"  {n:>3}  {etiqueta:<44} {como[:34]:<34} {cuantos}")
    out.append("")
    out.append(f"  TOTAL DE SECCIONES EN EL ESTADO BASE: {n}")
    out.append("  Cada seccion lleva ADEMAS una foto por elemento que abra algo.")
    out.append(f"  Pide el detalle con  forms_plan('{forma}', seccion='<TAB o CANVAS>')")
    out.append("")

    if condicionales:
        out.append("FOTOS CONDICIONADAS — la tab solo existe en cierto estado")
        out.append("  El codigo prende y apaga estas tab pages, asi que NO se pueden")
        out.append("  fotografiar todas en la misma pasada. Condicion segun el IF mas")
        out.append("  cercano en el PL/SQL (heuristica sobre el texto, no analisis real):")
        out.append("")
        for cv, tab in sorted(condicionales, key=lambda k: k[1]):
            reglas = conmutadas[tab.upper()]
            visible_si = {(c, r) for c, r, v in reglas if v}
            oculta_si = {(c, r) for c, r, v in reglas if not v}
            out.append(f"  {tab.lower():<22} ({len(destino[(cv, tab)])} items)")
            for c, r in sorted(visible_si):
                out.append(f"      se VE     cuando  {c}   [rama {r}]")
            for c, r in sorted(oculta_si):
                out.append(f"      se OCULTA cuando  {c}   [rama {r}]")
        out.append("")
        out.append(f"  TOTAL CONDICIONADAS: {len(condicionales)} fotos "
                   "(hay que provocar el estado)")
        out.append("")

    if descartadas:
        out.append("DESCARTADAS SIN IR A LA FORMA — no hay camino que seguir")
        for etiqueta, cuantos, clase, motivo in descartadas:
            out.append(f"  [{clase:<9}] {etiqueta:<34} ({cuantos} items)")
            out.append(f"               {motivo}")
        out.append("")

    if rutas["rotas"]:
        out.append("REFERENCIAS ROTAS — la forma invoca objetos que NO existen")
        out.append("  Son defectos del .fmb: producen error en pantalla, no fotos.")
        for objetivo, invs in sorted(rutas["rotas"].items()):
            quien = ", ".join(sorted({i["item"] for i in invs})[:3])
            verbo = invs[0]["verbo"]
            out.append(f"  {objetivo:<22} invocado con {verbo}() desde {quien}")
        out.append("")

    out.append("NO REQUIEREN FOTO (con motivo)")
    out.append(f"  · de las {len(lovs)} LOVs en uso se omiten solo las OBVIAS: aquellas "
               "cuyo contenido")
    out.append("    se adivina por la etiqueta del campo (campo 'Ciudad' -> lista de "
               "ciudades).")
    out.append("    El detalle por seccion las marca con [¿OBVIO?]; la decision es de "
               "quien captura.")
    sin_items = [c["nombre"] for c in canvases
                 if not any(cv == c["nombre"] for (cv, _) in destino)]
    if sin_items:
        out.append(f"  · canvas sin items visibles: {', '.join(sin_items)}")
    out.append("  · barra de menu y barra de herramientas: van en la ayuda general "
               "compartida del modulo, no en el manual de la forma")
    out.append("")

    out.append("NO TOCAR — botones que escriben o lanzan procesos")
    hay = False
    for item, riesgo, motivo in sorted(botones):
        if riesgo == "NO TOCAR":
            out.append(f"  {item:<32} {motivo}")
            hay = True
    if not hay:
        out.append("  ninguno")
    out.append("")
    otras = sorted({(i, m) for i, r, m in botones if r == "otra forma"})
    if otras:
        out.append("ABREN OTRA FORMA — fuera del alcance de este manual")
        for item, motivo in otras:
            out.append(f"  {item:<32} -> {motivo}")
    return "\n".join(out)


# ── ejecucion por lotes ──────────────────────────────────────────────────────

# Las herramientas devuelven sus fallos como TEXTO, no como excepcion, para
# que se puedan leer. El precio es que un lote los tomaba por exito: paso una
# vez que la calibracion fallo, el click_item se nego por falta de calibracion,
# el CTRL+L siguiente disparo a ciegas y la captura se guardo con el nombre de
# una LOV que no estaba abierta. Es el defecto de la foto 56 de IFACTURAOPT,
# producido por la propia herramienta. Estos marcadores lo detienen.

@mcp.tool()
def forms_secuencia(pasos: str) -> str:
    """Ejecuta VARIOS pasos en UNA sola llamada. Evita un viaje por click.

    Un paso por linea, con la forma `accion clave=valor ...`:

        click x=289 y=114
        esperar segundos=0.6
        capturar nombre=ubicacion auto=true carpeta=D:\\fotos
        tecla combinacion=F11
        escribir texto=346789097612

    Acciones: click · click_item · calibrar · tecla · escribir · esperar ·
    capturar · cerrar. Lo normal es `calibrar` una vez y luego encadenar
    `click_item`, que pulsa por NOMBRE del .fmb en vez de por pixel adivinado.

    Para decidir si un control necesita las dos versiones, comparar contra la
    captura de antes:

        capturar nombre=antes auto=true
        click_item forma=binmueb item=FRESHIJO
        capturar nombre=despues auto=true comparar_con=...\\antes.png

    Se detiene en el primer error Y ante cualquier aviso que empiece por OJO:
    un foco que no se movio o una pantalla que no cambio invalidan todo lo que
    venga detras, y seguir solo produciria fotos mal rotuladas.
    Las teclas bloqueadas siguen bloqueadas.
    """
    acciones = {"click": forms_click, "tecla": forms_tecla,
                "escribir": forms_escribir, "esperar": forms_esperar,
                "capturar": forms_capturar, "click_item": forms_click_item,
                "calibrar": forms_calibrar, "cerrar": forms_cerrar_popup}
    log = []
    # Quitar la marca de orden de bytes: PowerShell 5.1 escribe UTF-8 CON BOM
    # y el primer paso llegaba como '﻿click', que no coincide con nada.
    pasos = pasos.lstrip("﻿")
    for crudo in pasos.splitlines():
        linea = crudo.lstrip("﻿").strip()
        if not linea or linea.startswith("#"):
            continue
        nombre, _, cola = linea.partition(" ")
        nombre = nombre.lower()
        if nombre not in acciones:
            log.append(f"[X] accion desconocida: {nombre!r} "
                       f"(validas: {', '.join(acciones)})")
            break
        # Se parsea con regex y no con shlex: las rutas de las ayudas llevan
        # espacios ("Bienes e inmuebles", "testeo mcp") y shlex partia
        # carpeta="Z:\...\Bienes e inmuebles\X" en tres tokens, con lo que
        # llegaba un argumento llamado 'e'. La clave es siempre un
        # identificador, asi que el valor es todo lo que va hasta la siguiente
        # clave o hasta el final — entre comillas o sin ellas.
        #
        # Ese "o sin ellas" era mentira hasta 2026-09-04: el patron acababa en
        # (\S*), que corta en el primer espacio, y una ruta sin comillas se
        # truncaba EN SILENCIO -"...\testeo mcp\FCALIFICA" quedaba en
        # "...\testeo"- guardando las fotos en otro sitio. Ahora el valor
        # termina donde empieza la siguiente clave, que es lo que decia el
        # comentario.
        # El tipo se toma de la FIRMA de la accion, no del aspecto del valor.
        # Adivinandolo por el texto, `escribir texto=01` se convertia en int 1 y
        # `w.escribir(1)` moria con "'int' object is not iterable" — y el propio
        # ejemplo de este docstring, `escribir texto=346789097612`, habria
        # fallado igual. Los codigos de SAFIX son texto que PARECE numero
        # ('01', una matricula, un NIT), y perder el cero de la izquierda al
        # teclear en la forma es peor todavia que el error: escribe otro dato.
        firma = inspect.signature(acciones[nombre]).parameters
        kwargs, sobran = {}, []
        for k, v_ent, v_com in re.findall(
                r'([A-Za-z_][A-Za-z0-9_]*)='
                r'(?:"([^"]*)"|(.*?))'
                r'(?=\s+[A-Za-z_][A-Za-z0-9_]*=|\s*$)', cola):
            v = (v_ent if v_ent else v_com).strip()
            p = firma.get(k)
            if p is None:
                sobran.append(k)
                continue
            tipo = p.annotation
            try:
                if tipo is bool:
                    kwargs[k] = v.strip().lower() in ("true", "1", "si", "yes")
                elif tipo is int:
                    kwargs[k] = int(v)
                elif tipo is float:
                    kwargs[k] = float(v)
                else:
                    kwargs[k] = v          # str y todo lo demas, tal cual
            except ValueError:
                sobran.append(f"{k} (se esperaba {getattr(tipo, '__name__', tipo)})")
        if sobran:
            # Un argumento mal escrito se ignoraba en silencio y el paso corria
            # con el valor por defecto: `carpeta` mal tecleada guardaba la foto
            # en la carpeta del dia y nadie se enteraba hasta buscarla.
            log.append(_fallo(f"{linea}\n     argumento no valido para "
                              f"'{nombre}': {', '.join(sobran)}. "
                              f"Acepta: {', '.join(firma)}"))
            break
        try:
            salida = str(acciones[nombre](**kwargs))
        except Exception as e:
            log.append(f"[X] {linea}\n     {type(e).__name__}: {e}")
            break
        fallo = _es_fallo(salida)
        log.append(f"{'[X]' if fallo else '[OK]'} {linea}\n     {salida}")
        if fallo:
            log.append(f"[!] LOTE DETENIDO: {fallo}. Lo que siguiera saldria "
                       "mal rotulado o pulsaria a ciegas.")
            break
    return "\n".join(log) if log else "Nada que ejecutar."


# Calibraciones por (forma, canvas, tab). Son relativas a la ventana, asi que
# sobreviven a que la ventana se mueva. Se guardan en disco para que valgan
# entre invocaciones y se puedan inspeccionar.
@mcp.tool()
def forms_calibrar(forma: str, canvas: str = "CNV_TAB", tab: str = "",
                   hwnd: str = "", estado: str = "") -> str:
    """Ajusta la conversion unidades del .fmb -> pixeles de la seccion visible.

    Hay que llamarla UNA vez por seccion antes de usar forms_click_item. La
    calibracion es relativa a la ventana, asi que sigue valiendo si la ventana
    se mueve; hay que repetirla al cambiar de pestana o de estado, porque
    cambia el juego de campos visibles.
    """
    h = _resolver(int(hwnd, 0) if hwnd else None)
    _exigir_frente(h)
    cal, err = _calibrar(forma, canvas, tab, h, estado)
    if err:
        return err

    salida = (f"Calibrada {forma} · {canvas}/{tab or '(sin tab)'}\n"
              f"  escala {cal['escala']}  off_x {cal['off_x']}  "
              f"off_y {cal['off_y']}\n"
              f"  {cal['encajes']} de {cal['de']} campos encajan en "
              f"{cal.get('niveles', '?')} altura(s) distinta(s) · "
              f"residuo medio {cal['residuo']} px\n"
              "  Los que no encajan suelen ser campos deshabilitados: en gris "
              "no hay area blanca que detectar.")
    # Una sola altura explicada = el desplazamiento en y sigue siendo ambiguo.
    # Es el caso de la rejilla: 13 filas iguales encajan igual de bien y el
    # residuo no lo delata. Se dice, en vez de devolver un numero con aire de
    # certeza.
    if cal.get("niveles", 0) < 2:
        salida = _aviso(
            f"la calibracion encaja en UNA sola altura del .fmb, asi que el "
            f"off_y ({cal['off_y']}) puede estar desplazado un numero entero de "
            f"filas y los clicks caerian en la fila de al lado sin dar error. "
            f"Comprueba un elemento conocido con capturar(comparar_con=...) "
            f"antes de fiarte.\n" + salida)
    aviso = _contrastar_calibracion(forma, canvas, tab, estado, cal)
    return salida + aviso if not aviso else salida + "\n" + aviso


# Un ajuste con POCOS encajes puede cuadrar en un optimo falso y ensenar un
# residuo bueno: el residuo solo mide los puntos que encajaron, no si el
# desplazamiento es el correcto. Medido el 2026-09-03 en IMAGENES: 3 encajes de
# 4 dieron off_y=82 con residuo 0.63 px, cuando el valor real de CNV_TAB es 64
# (cuatro calibraciones independientes coincidieron). Los clicks salian 27 px
# abajo y el boton no se pulsaba — sin ningun error.
# encajes_fiables vive en ajustes.json


@mcp.tool()
def forms_click_item(forma: str, item: str, canvas: str = "CNV_TAB",
                     tab: str = "", hwnd: str = "", doble: bool = False,
                     estado: str = "") -> str:
    """Pulsa un control POR SU NOMBRE del .fmb, calculando su pixel.

    Es la alternativa a adivinar donde esta una flecha de LOV de 12 px. Exige
    haber llamado antes a forms_calibrar para esa seccion.

    Se NIEGA a pulsar los controles cuyo WHEN-BUTTON-PRESSED escribe en la
    base de datos o lanza procesos, con el mismo criterio que forms_plan.
    """
    h = _resolver(int(hwnd, 0) if hwnd else None)
    todas = _calib_leer()
    cal = todas.get(_calib_clave(forma, canvas, tab, estado))
    prestada = ""
    if cal is None:
        # La escala y el desplazamiento son de la VENTANA, no de la pestana:
        # todas las calibraciones de binmueb dieron 1.335 / 6 / 64, en las dos
        # pestanas y en los tres estados. Una seccion pobre (PLANO tiene 2
        # items y un solo campo blanco) no puede calibrarse por si misma, y
        # exigirselo la dejaba fuera del alcance sin necesidad. Se toma
        # prestada la de otra seccion del mismo canvas, DICIENDOLO.
        prefijo = f"{forma.lower()}|{canvas}|"
        candidatas = [(k, v) for k, v in todas.items()
                      if k.startswith(prefijo)]
        if candidatas:
            # La de mejor ajuste: mas encajes y menor residuo.
            k, cal = min(candidatas,
                         key=lambda kv: (-kv[1].get("encajes", 0),
                                         kv[1].get("residuo", 99)))
            prestada = (f"  calibracion PRESTADA de '{k}' "
                        f"({cal['encajes']} encajes, residuo "
                        f"{cal['residuo']} px): esta seccion no tiene "
                        f"suficientes campos blancos propios.\n")
    if cal is None:
        return _fallo(f"falta calibrar {canvas}/{tab or '(sin tab)'}"
                + (f" en el estado '{estado}'" if estado else "") + ". "
                + f"Llama primero a forms_calibrar('{forma}', tab='{tab}'"
                + (f", estado='{estado}'" if estado else "") + ").")

    # Un radio individual se pide como 'GRUPO.RADIO': el .fmb los declara como
    # hijos del Radio Group, con su propia x/y, y son la via para cambiar de
    # panel apilado sin adivinar el pixel.
    radio = None
    if "." in item:
        item, radio = item.split(".", 1)

    objetivo = next((i for i in _items_de(forma, canvas, tab)
                     if i["nombre"].upper() == item.upper()), None)
    if objetivo is not None and radio:
        rb = next((r for r in (objetivo.get("radio_buttons") or [])
                   if (r.get("nombre") or "").upper() == radio.upper()), None)
        if rb is None:
            disponibles = [r.get("nombre") for r in
                           (objetivo.get("radio_buttons") or [])]
            return _fallo(f"'{item}' no tiene el radio '{radio}'. "
                    f"Tiene: {', '.join(disponibles) or '(ninguno)'}")
        # Un radio es un circulo pequeno con su etiqueta a la derecha: el
        # punto de click va sobre el circulo, no en el centro de la etiqueta.
        objetivo = {**objetivo, "x": rb.get("x"), "y": rb.get("y"),
                    "ancho": 8, "alto": 8,
                    "tipo_visual": f"Radio '{rb.get('label') or radio}'"}
    if objetivo is None:
        nombres = [i["nombre"] for i in _items_de(forma, canvas, tab)
                   if item.upper() in i["nombre"].upper()][:8]
        return _fallo(f"no existe '{item}' en {canvas}/{tab}."
                + (f" Parecidos: {', '.join(nombres)}" if nombres else ""))

    # Guarda de riesgo: se mira el codigo real del boton, no su nombre.
    t_item = json.load(open(os.path.join(_extract_de(forma),
                                         "04_triggers_item.json"), encoding="utf-8"))
    for bloque, items in t_item.items():
        for nombre, trs in items.items():
            if nombre.upper() != item.upper():
                continue
            for tr in trs:
                if "BUTTON-PRESSED" not in (tr.get("nombre") or "").upper():
                    continue
                riesgo, motivo = _clasificar(tr.get("codigo") or "")
                if riesgo == "NO TOCAR":
                    return _fallo(
                        f"no se pulsa '{item}': su codigo contiene {motivo}. "
                        "Escribe en la base de datos o lanza un proceso.")

    try:
        fx, fy = int(objetivo["x"]), int(objetivo["y"])
    except (ValueError, KeyError, TypeError):
        return _fallo(f"'{item}' no declara posicion en el .fmb; no se puede "
                      "calcular.")
    fa = int(objetivo.get("ancho") or 0) or 14
    fh = int(objetivo.get("alto") or 0) or 14

    estorbo = _exigir_ventana_datos(h)
    if estorbo:
        return _fallo(f"no se pulsa '{item}': {estorbo}.")

    e, ox, oy = cal["escala"], cal["off_x"], cal["off_y"]
    cx = int(ox + (fx + fa / 2) * e)
    cy = int(oy + (fy + fh / 2) * e)
    r = forms_click(x=cx, y=cy, hwnd=hwnd, doble=doble, relativo=True)

    salida = (prestada
              + f"{item} ({objetivo.get('tipo_visual')}) en .fmb ({fx},{fy}) "
              f"{fa}x{fh} -> ventana ({cx},{cy})\n  {r}")

    # El foco solo se verifica sobre lo que PUEDE recibirlo. Un push button de
    # Forms dispara su trigger SIN mover el cursor de texto, asi que el resalte
    # amarillo se queda en el campo anterior y la comprobacion gritaba "foco
    # EQUIVOCADO" cuando el click habia funcionado perfectamente. Paso con
    # BTN_COMPONENTES: el boton se pulso, la forma respondio, y el lote se
    # detuvo por una falsa alarma mia.
    parent = (objetivo.get("parent_name") or "").upper()
    SIN_FOCO = ("PBUTTON_ICONIC", "PBUTTON_LIST", "PBUTTON_CALENDAR",
                "PC_LINK", "CHECK_BOX")
    if radio or parent in SIN_FOCO:
        veredicto = ("no se verifica el foco: este control no lo recibe. "
                     "Para saber si funciono, compara la pantalla con "
                     "capturar(comparar_con=...)")
        nivel = "ok"
    else:
        veredicto = _verificar_foco(h, cx, cy)
        nivel = "aviso" if veredicto.startswith("OJO") else "ok"

    salida += f"\n  {veredicto}"
    _bitacora(accion="click_item", detalle=f"{item} -> ({cx},{cy})",
              avisos=[veredicto], nivel=nivel)
    return salida


def _verificar_foco(hwnd, cx, cy, tolerancia=6, espera=0.4):
    """Comprueba que el foco quedo donde se pulso, mirando el resalte.

    Un click que no mueve el foco no produce ningun error: el cursor se queda
    en el campo anterior y el `Ctrl+L` siguiente abre la lista de OTRO campo.
    Asi pedi 'Centro Costos' y me salio 'Barrios', y la foto se guardo con el
    nombre equivocado sin una sola senal de alarma. Este es el unico chequeo
    que lo caza, y por eso se hace SIEMPRE, no a peticion.

    Devuelve una frase, no un booleano: quien llama tiene que leerla.

    Se espera antes de leer: Forms tarda en repintar el resalte, y leerlo al
    instante daba "foco EQUIVOCADO" senalando el campo ANTERIOR cuando el
    click habia funcionado. Un falso positivo aqui detiene el lote sin motivo.
    """
    time.sleep(espera)
    f = w.detectar_foco(hwnd)
    if f is None:
        return ("foco: no se ve resalte. Este control puede no recibir foco "
                "(boton, etiqueta); si esperabas un campo, NO uses Ctrl+L.")
    dentro = (f["x"] - tolerancia <= cx <= f["x"] + f["ancho"] + tolerancia and
              f["y"] - tolerancia <= cy <= f["y"] + f["alto"] + tolerancia)
    donde = f"({f['x']},{f['y']}) {f['ancho']}x{f['alto']} color {f['color']}"
    if dentro:
        return f"foco OK: el resalte cubre el punto pulsado — {donde}"
    return _aviso("foco EQUIVOCADO: el resalte esta en " + donde +
            f", no en ({cx},{cy}). El click no movio el foco: un Ctrl+L ahora "
            "abriria la lista de otro campo. Repite el click o salta el elemento.")


@mcp.tool()
def forms_cerrar_popup(hwnd: str = "", ancho_datos: int = 0,
                       intentos: int = 3) -> str:
    """Cierra el recuadro que este encima (LOV, mensaje) y deja la forma libre.

    ESC no cierra las LOVs de Forms de forma fiable, y dejar una abierta
    arruina todo lo que venga despues: el click de la pestana siguiente se
    va a la LOV y las capturas salen todas iguales. Paso de verdad.

    NO es un click a ciegas: primero se detecta el recuadro y su TAMANO dice
    de que tipo es, y de ahi sale la posicion del boton. Medido en SAFIX:

        LOV      466x326  ->  Cancel  en (74.7%, 93.6%)
        mensaje  ~x155    ->  Aceptar en (84%, 84%)

    Si lo que hay delante ya es la ventana de datos, no hace nada. La ventana
    de datos se reconoce por su TAMANO APRENDIDO al calibrar, no por un umbral
    de ancho: `ancho_datos` es solo el respaldo para cuando no se ha calibrado.
    Con el umbral fijo de 600 px, la ventana secundaria 'Componentes' (666x423,
    MAS ANCHA que la de datos) se tomaba por la principal y esta herramienta
    decia "no hay recuadro que cerrar" con la ventana encima. El click de la
    pestana siguiente se iba dentro de ella.
    """
    # Una LOV sin valores apila DOS mensajes en SAFIX ("No existen valores
    # para la lista" y despues "No hay lista de valores disponible"), asi que
    # cerrar una vez no basta. Se itera RE-DETECTANDO en cada vuelta: no es
    # clicar a ciegas, cada iteracion identifica el recuadro por su tamano.
    cerrados = []
    for i in range(max(1, intentos)):
        r = _cerrar_uno(hwnd, ancho_datos or None)
        if r.startswith("Cerrado"):
            cerrados.append(r)
            continue
        if cerrados and ("no hay recuadro que cerrar" in r
                         or "nada que cerrar" in r):
            return (f"{len(cerrados)} recuadro(s) cerrado(s): "
                    + " | ".join(x.replace("Cerrado el ", "") for x in cerrados))
        return r if not cerrados else f"{' | '.join(cerrados)} — y luego: {r}"
    return " | ".join(cerrados) or r


def _cerrar_uno(hwnd, ancho_datos=None):
    h = _resolver(int(hwnd, 0) if hwnd else None)
    _exigir_frente(h)
    aj = w.ajustes()
    if ancho_datos is None:
        ancho_datos = aj["ancho_datos_respaldo"]
    v = w.detectar_ventana_reintentando(h)
    if v is None:
        return "no se detecta ningun recuadro; nada que cerrar."

    datos = _ventana_datos.get(h)
    if datos:
        es_datos = (abs(v["ancho"] - datos[0]) <= 8
                    and abs(v["alto"] - datos[1]) <= 8)
        if not es_datos and v["ancho"] * v["alto"] > datos[0] * datos[1]:
            return (f"Delante hay una ventana MAS GRANDE que la de datos "
                    f"({v['ancho']}x{v['alto']} contra {datos[0]}x{datos[1]}): "
                    "es una ventana secundaria, no un recuadro. Cierrala por su "
                    "propio boton de salida; aqui no se adivina donde esta.")
    else:
        es_datos = v["ancho"] >= ancho_datos

    if es_datos:
        return (f"Delante esta la ventana de datos ({v['ancho']}x{v['alto']}): "
                "no hay recuadro que cerrar.")
    # Las posiciones de los botones viven en ajustes.json: son del look&feel de
    # SAFIX, no del codigo. El 0,697 de Cancel ya fallo una vez por UN pixel.
    if v["alto"] > aj["popup_alto_lov"]:
        fx, fy = aj["popup_lov_cancel"]
        tipo, boton = "LOV", "Cancel"
    else:
        fx, fy = aj["popup_mensaje_aceptar"]
        tipo, boton = "mensaje", "Aceptar"
    cx, cy = int(v["ancho"] * fx), int(v["alto"] * fy)
    forms_click(x=cx, y=cy, hwnd=hwnd, relativo=True)
    time.sleep(1.2)
    v2 = w.detectar_ventana_reintentando(h)
    sigue = (v2 and abs(v2["ancho"] - datos[0]) > 8 if datos
             else v2 and v2["ancho"] < ancho_datos)
    if sigue:
        return _aviso(f"se pulso {boton} del {tipo} pero sigue habiendo un recuadro "
                f"({v2['ancho']}x{v2['alto']}). Miralo antes de seguir.")
    return f"Cerrado el {tipo} ({v['ancho']}x{v['alto']}) con {boton}."


@mcp.tool()
def forms_tabs(hwnd: str = "") -> str:
    """Blancos de click de la tira de pestanas, detectados por pixeles.

    No depende de cuantas pestanas tenga la forma ni de como se llamen: se
    localiza la banda de la tira y se devuelven puntos donde pulsar, en
    coordenadas RELATIVAS a la ventana (usar con forms_click relativo=True).

    Aviso: son blancos de click, NO limites de pestana. El texto de cada
    etiqueta parte la deteccion, asi que una pestana ancha puede dar dos
    puntos y aparecer duplicada. No se informa cual esta activa porque
    distinguirlo por pixeles no resulto fiable — para saber donde estas,
    compara la captura.
    """
    h = _resolver(int(hwnd, 0) if hwnd else None)
    if not w.traer_al_frente(h):
        return forms_foco(hwnd)
    v = w.detectar_ventana_reintentando(h)
    if v is None:
        return _fallo("no se detecto la ventana activa.")
    tabs = w.detectar_tabs(h, v)
    if not tabs:
        return _fallo("no se detecto tira de pestanas. Puede que esta forma no "
                "tenga tab canvas, o que la ventana este muy estrecha.")
    filas = [f"ventana: x={v['x']} y={v['y']} {v['ancho']}x{v['alto']}",
             f"tira detectada en y={tabs[0]['y']} (relativo a la ventana)",
             f"{len(tabs)} blancos de click:"]
    for i, t in enumerate(tabs, 1):
        filas.append(f"  {i:>2}  x={t['x']:<5} y={t['y']:<5} ancho={t['ancho']}")
    filas.append("Uso: forms_click x=<x> y=<y> relativo=true")
    return "\n".join(filas)


@mcp.tool()
def forms_pendientes(forma: str, carpeta_fotos: str, carpeta_pendientes: str) -> str:
    """Escribe el .txt de pendientes cruzando el plan con las fotos en disco.

    Antes este archivo se redactaba a mano, que es justo lo que no escala.
    Aqui se genera: lo que el plan pide, lo que hay en disco, y lo que el
    analisis estatico ya descarto con su motivo.

    Args:
        forma: modulo, p.ej. 'binmueb'. Da nombre al archivo <FORMA>.txt.
        carpeta_fotos: donde estan los PNG tomados.
        carpeta_pendientes: donde escribir el .txt.
    """
    plan = forms_plan(forma)
    try:
        fotos = sorted(f for f in os.listdir(carpeta_fotos)
                       if f.lower().endswith(".png"))
    except OSError as e:
        return _fallo(f"no se pudo leer {carpeta_fotos}: {e}")

    os.makedirs(carpeta_pendientes, exist_ok=True)
    destino = os.path.join(carpeta_pendientes, f"{forma.upper()}.txt")

    # Del plan solo se necesitan los bloques ya redactados por forms_plan:
    # se copian tal cual para no mantener dos versiones del mismo texto.
    def seccion(titulo):
        lineas, dentro = [], False
        for l in plan.splitlines():
            if l.startswith(titulo):
                dentro = True
            elif dentro and l and not l.startswith(" "):
                break
            if dentro:
                lineas.append(l)
        return "\n".join(lineas)

    cuerpo = [
        f"PENDIENTES DE FOTOS — FORMA {forma}",
        f"Generado automaticamente por forms_pendientes: "
        f"{dt.datetime.now():%Y-%m-%d %H:%M}",
        f"Extract : {_extract_de(forma)}",
        f"Imagenes: {carpeta_fotos}",
        "",
        f"FOTOS EN DISCO ({len(fotos)})",
    ]
    cuerpo += [f"  {f}" for f in fotos] or ["  (ninguna)"]
    cuerpo += ["", seccion("FOTOS CONDICIONADAS"),
               "", seccion("DESCARTADAS SIN IR A LA FORMA"),
               "", seccion("REFERENCIAS ROTAS"),
               "", seccion("NO TOCAR"),
               "",
               "COMO LEER ESTE ARCHIVO",
               "  CONDICIONADAS  hay que provocar el estado y volver a pasar.",
               "  DESCARTADAS    no hay camino en el .fmb: no se intentan.",
               "  ROTAS          defectos de la forma; producen error, no foto.",
               "  NO TOCAR       botones que escriben en la base de datos.",
               ]
    with open(destino, "w", encoding="utf-8") as f:
        f.write("\n".join(cuerpo) + "\n")
    return (f"Escrito {destino}\n  {len(fotos)} fotos en disco registradas.\n"
            "  Secciones copiadas del plan: condicionadas, descartadas, "
            "rotas, no tocar.")


if __name__ == "__main__":
    mcp.run()

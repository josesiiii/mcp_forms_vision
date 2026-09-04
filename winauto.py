"""
Capa Win32 para forms-vision: ventanas, captura e inyeccion de entrada.

Todo con ctypes contra user32/kernel32 — sin pywin32, que a la fecha no tiene
rueda estable para Python 3.14 en este equipo.

Decisiones que NO son arbitrarias y conviene no revertir sin leer esto:

  * La captura se toma de PANTALLA, no con PrintWindow. Sobre ventanas Java
    (SunAwtFrame/SunAwtCanvas) PrintWindow suele devolver un frame negro.
    Precio: la ventana debe estar al frente y sin nada encima.
  * La entrada se inyecta con SendInput (entrada real), no con PostMessage.
    AWT ignora buena parte de los mensajes sinteticos. Precio: el mouse fisico
    se mueve y el foco es real.
  * El sistema de referencia para clicks y recortes es el SunAwtCanvas, no el
    frame: es la superficie donde Forms dibuja, y no se mueve cuando cambian
    los bordes o la barra de titulo.
"""

import ctypes
import ctypes.wintypes as wt
import json
import os
import time

# ── ajustes que se afinan probando ───────────────────────────────────────────
#
# Viven en ajustes.json y se releen en CADA llamada, asi que cambiarlos NO
# exige reiniciar la app. Solo el codigo (.py) lo exige: el proceso del MCP
# tiene los modulos cargados en memoria y Python no recarga nada por su cuenta.
#
# Los valores de aqui son el RESPALDO: si el archivo falta o esta mal formado
# se usan estos, para que una edicion torpe del JSON no deje la herramienta
# inservible. El lector vive en esta capa y no en server.py porque winauto
# tambien los necesita, y no puede importar server sin volverlo circular.

AJUSTES_DEFECTO = {
    "menor_pixeles": 8000,
    "menor_tope": 0.05,
    "marcas_fallo": [
        ["ojo", "aviso de foco o de pantalla sin cambiar"],
        ["sigue habiendo un recuadro", "quedo un recuadro encima"],
        ["hay un recuadro encima", "quedo un recuadro encima"],
        ["no se hizo click", "el click no se ejecuto"],
        ["no se ve resalte", "el foco no quedo en un campo"],
        ["no se detect", "no se detecto la ventana"],
        ["no se pudo", "la accion no se pudo completar"],
        ["falta calibrar", "seccion sin calibrar"],
        ["no se pulsa", "control bloqueado por riesgo"],
        ["no existe '", "el item no existe en esa seccion"],
        ["no tiene el radio", "radio inexistente"],
        ["no declara posicion", "el item no tiene coordenadas en el .fmb"],
        ["negra", "captura negra"],
        ["plana", "captura sin contraste"],
        ["recorte minusculo", "recorte del tamano de un icono"],
        ["ajuste pobre", "calibracion sin encaje suficiente"],
        ["bloqueada", "sesion de Windows bloqueada"],
    ],
    "clase_por_parent": {
        "CHECK_BOX": "CHECK", "POPLIST": "LISTA", "PBUTTON_LIST": "LOV",
        "PBUTTON_ICONIC": "BOTON", "PBUTTON_CALENDAR": "OMITIR_CALENDARIO",
        "TEXT_READ_ONLY": "OMITIR_GRIS", "TEXT_NORMAL": "OMITIR_TEXTO",
        "PC_LINK": "OMITIR_ESPEJO", "PC_VALOR": "OMITIR_TEXTO",
        "PC_CANTIDAD": "OMITIR_TEXTO", "PC_PORCENTAJE": "OMITIR_TEXTO",
        "PC_CANT_SIN_DECIMAL": "OMITIR_TEXTO",
        "TEXT_COMMENTS": "OMITIR_TEXTO", "RADIO_OPTION": "OMITIR_HIJO_RADIO",
    },
    "prefijo": {
        "RADIO": "radio_btn_", "CHECK": "check_box_",
        "LISTA": "select_list_", "LOV": "lov_", "BOTON": "btn_",
        "LINK": "link_",
    },
    "sufijos_rango": ["_inicial", "_final", "_ini", "_fin", "_inicia",
                      "_desde", "_hasta"],
    "rejilla_minima": 8,
    "encajes_fiables": 5,
    # Donde estan los botones de los recuadros de SAFIX, en FRACCION del
    # recuadro. Son del look&feel (Oracle, colorScheme SWAN): otra instalacion
    # con otro tema los tendria en otro sitio, y por eso son datos y no codigo.
    #
    # Medido en el recuadro de 466x326: Cancel ocupa x 303..347, centro 325 =
    # 69,7%. La primera version usaba 74,7% (x 348), UN PIXEL fuera del borde:
    # cerraba unas veces y otras no, y una LOV que se queda abierta se lleva
    # por delante todo lo que venga detras.
    #
    # NUNCA se pulsa OK/Aceptar de una LOV: eso SELECCIONA un valor y lo
    # escribe en el campo.
    "popup_lov_cancel": [0.697, 0.936],
    "popup_mensaje_aceptar": [0.84, 0.84],
    # Por encima de este alto, el recuadro es una LOV; por debajo, un mensaje.
    "popup_alto_lov": 250,
    # Ancho minimo para tomar un recuadro por la ventana de datos, SOLO cuando
    # todavia no se ha calibrado y no hay tamano aprendido con el que comparar.
    "ancho_datos_respaldo": 600,
    # Ambientes de SAFIX en los que esta herramienta puede actuar.
    #
    # El titulo de la ventana declara el ambiente:
    #     Administracion del Sistema [XENCO/Safix@SAFIXDEMOS/2026-09]
    #                                              ^^^^^^^^^^
    # Hasta ahora la separacion de ambientes era una advertencia en el README.
    # Una advertencia no es un control: no impide nada. Ahora se lee el titulo
    # y se RECHAZA actuar si el ambiente no esta en esta lista.
    #
    # Falla CERRADO: si el ambiente no se puede leer, tampoco se actua. Es la
    # misma regla que el proyecto ya exige en PL/SQL (OWASP A10).
    "ambientes_permitidos": ["SAFIXDEMOS"],
    "verbos_peligrosos": [
        "COMMIT", "DELETE_RECORD", "FORMS_DDL", "PU_HEREDAR",
        "CREAR_ENCUESTA", "RUN_PRODUCT", "APU_REPORTES",
        "INSERT ", "UPDATE ", "DELETE FROM",
    ],
}

_AJUSTES_RUTA = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "ajustes.json")
_ajustes_cache = {"mtime": None, "valor": None, "aviso": ""}


def ajustes():
    """Los ajustes vigentes, releidos si el archivo cambio en disco.

    Se cachea por fecha de modificacion para no leer el JSON en cada click,
    pero se recarga en cuanto el archivo cambia: eso es lo que evita reiniciar
    la app para afinar un umbral o un marcador.
    """
    try:
        m = os.path.getmtime(_AJUSTES_RUTA)
    except OSError:
        _ajustes_cache["aviso"] = (
            f"no hay {os.path.basename(_AJUSTES_RUTA)}: se usan los valores "
            "por defecto de winauto.py")
        return AJUSTES_DEFECTO

    if _ajustes_cache["mtime"] != m:
        try:
            with open(_AJUSTES_RUTA, encoding="utf-8") as f:
                leido = json.load(f)
        except (OSError, ValueError) as e:
            _ajustes_cache["aviso"] = (
                f"{os.path.basename(_AJUSTES_RUTA)} no se puede leer "
                f"({type(e).__name__}): se usan los valores por defecto")
            return AJUSTES_DEFECTO

        # Solo se aceptan claves CONOCIDAS y del MISMO TIPO que el respaldo: un
        # typo no puede introducir una clave fantasma, ni cambiar un entero por
        # una cadena y reventar en mitad de una corrida de 90 fotos.
        fusion, ignoradas = dict(AJUSTES_DEFECTO), []
        for k, v in leido.items():
            if k.startswith("_"):
                continue
            if k not in AJUSTES_DEFECTO:
                ignoradas.append(f"{k} (clave desconocida)")
            elif not isinstance(v, type(AJUSTES_DEFECTO[k])) and not (
                    isinstance(v, (int, float))
                    and isinstance(AJUSTES_DEFECTO[k], (int, float))):
                ignoradas.append(f"{k} (tipo {type(v).__name__})")
            else:
                fusion[k] = v
        _ajustes_cache.update(
            mtime=m, valor=fusion,
            aviso=("ignorado de ajustes.json: " + ", ".join(ignoradas)
                   if ignoradas else ""))
    return _ajustes_cache["valor"]


def ajustes_aviso():
    """Ultimo problema al leer ajustes.json, o cadena vacia si fue bien."""
    ajustes()
    return _ajustes_cache["aviso"]


user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

ULONG_PTR = ctypes.c_size_t
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

SW_RESTORE = 9
SM_XVIRTUALSCREEN, SM_YVIRTUALSCREEN = 76, 77
SM_CXVIRTUALSCREEN, SM_CYVIRTUALSCREEN = 78, 79

INPUT_MOUSE, INPUT_KEYBOARD = 0, 1
MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP = 0x0002, 0x0004
MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP = 0x0008, 0x0010
MOUSEEVENTF_ABSOLUTE, MOUSEEVENTF_VIRTUALDESK = 0x8000, 0x4000
KEYEVENTF_KEYUP, KEYEVENTF_UNICODE = 0x0002, 0x0004

PROCESOS_JAVA = ("java.exe", "javaw.exe", "jp2launcher.exe", "javaws.exe")


# ── estructuras SendInput ────────────────────────────────────────────────────

class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", wt.LONG), ("dy", wt.LONG), ("mouseData", wt.DWORD),
                ("dwFlags", wt.DWORD), ("time", wt.DWORD), ("dwExtraInfo", ULONG_PTR)]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wt.WORD), ("wScan", wt.WORD), ("dwFlags", wt.DWORD),
                ("time", wt.DWORD), ("dwExtraInfo", ULONG_PTR)]


class _INPUTUNION(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT)]


class INPUT(ctypes.Structure):
    _anonymous_ = ("u",)
    _fields_ = [("type", wt.DWORD), ("u", _INPUTUNION)]


def _enviar(*inputs):
    n = len(inputs)
    arr = (INPUT * n)(*inputs)
    enviados = user32.SendInput(n, arr, ctypes.sizeof(INPUT))
    if enviados != n:
        raise OSError(f"SendInput envio {enviados}/{n} eventos "
                      f"(error {ctypes.get_last_error()}). "
                      f"Causa tipica: una ventana elevada tiene el foco.")


# ── DPI ──────────────────────────────────────────────────────────────────────

def set_dpi_awareness():
    """Sin esto GetWindowRect miente en pantallas con escalado != 100%."""
    try:
        user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))  # per-monitor v2
        return "per-monitor-v2"
    except Exception:
        try:
            ctypes.WinDLL("shcore").SetProcessDpiAwareness(2)
            return "per-monitor-v1"
        except Exception:
            user32.SetProcessDPIAware()
            return "system"


# ── ventanas ─────────────────────────────────────────────────────────────────

ENUMPROC = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)


def _texto(hwnd):
    n = user32.GetWindowTextLengthW(hwnd)
    buf = ctypes.create_unicode_buffer(n + 1)
    user32.GetWindowTextW(hwnd, buf, n + 1)
    return buf.value


def _clase(hwnd):
    buf = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, buf, 256)
    return buf.value


def rect(hwnd):
    r = wt.RECT()
    if not user32.GetWindowRect(hwnd, ctypes.byref(r)):
        raise OSError(f"GetWindowRect fallo para hwnd 0x{hwnd:X}")
    return (r.left, r.top, r.right, r.bottom)


def _proceso(pid):
    h = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not h:
        return "?"
    try:
        buf = ctypes.create_unicode_buffer(1024)
        size = wt.DWORD(1024)
        if kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
            return os.path.basename(buf.value)
        return "?"
    finally:
        kernel32.CloseHandle(h)


def ventanas_java():
    """Frames top-level visibles pertenecientes a un proceso Java."""
    found = []

    def cb(hwnd, _):
        # Una ventana MINIMIZADA no es "visible" para Windows. Si se filtra
        # aqui, la herramienta se queda ciega y no puede recuperarla — paso
        # de verdad: SAFIX minimizado parecia cerrado. Se incluye marcada.
        iconica = bool(user32.IsIconic(hwnd))
        if not user32.IsWindowVisible(hwnd) and not iconica:
            return True
        pid = wt.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        pname = _proceso(pid.value).lower()
        if pname in PROCESOS_JAVA:
            l, t, r, b = rect(hwnd)
            if iconica or (r - l > 50 and b - t > 50):
                found.append({
                    "hwnd": hwnd, "pid": pid.value, "proceso": pname,
                    "clase": _clase(hwnd), "titulo": _texto(hwnd),
                    "rect": [l, t, r, b], "ancho": r - l, "alto": b - t,
                    "minimizada": iconica,
                    "primer_plano": hwnd == user32.GetForegroundWindow(),
                })
        return True

    user32.EnumWindows(ENUMPROC(cb), 0)
    return found


def ambiente_de(titulo):
    """El ambiente que DECLARA el titulo de la ventana de SAFIX, o None.

    El frame de SAFIX rotula el ambiente en su titulo:

        Administracion del Sistema [XENCO/Safix@SAFIXDEMOS/2026-09]

    Se lee de ahi y no de la configuracion a proposito: la configuracion dice
    a que ambiente se QUISO apuntar, el titulo dice en cual se esta de verdad.
    Un control que se cree la configuracion no protege de una sesion abierta
    por error contra otra base.

    Devuelve None si el titulo no lo declara — y quien llame debe tratar eso
    como "no autorizado", no como "adelante".
    """
    import re as _re
    m = _re.search(r"@([A-Za-z0-9_.\-]+)", titulo or "")
    return m.group(1).upper() if m else None


def canvas_de(hwnd):
    """Rect en pantalla del SunAwtCanvas: la superficie real de dibujo.

    Es el origen de coordenadas para clicks y recortes. Si no aparece
    (la ventana aun no termino de pintar), se cae al rect del frame.
    """
    encontrado = []

    def cb(child, _):
        if _clase(child).startswith("SunAwtCanvas") and user32.IsWindowVisible(child):
            encontrado.append(child)
        return True

    user32.EnumChildWindows(hwnd, ENUMPROC(cb), 0)
    if not encontrado:
        return rect(hwnd), None
    # El canvas de mayor area es la superficie principal.
    mejor = max(encontrado, key=lambda c: (lambda r: (r[2] - r[0]) * (r[3] - r[1]))(rect(c)))
    return rect(mejor), mejor


def proceso_de_ventana(hwnd):
    """(pid, nombre_exe) de la ventana indicada."""
    pid = wt.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return pid.value, _proceso(pid.value)


def ventana_al_frente():
    """(hwnd, clase, titulo, pid, exe) de la ventana en primer plano."""
    fg = user32.GetForegroundWindow()
    if not fg:
        return None
    pid, exe = proceso_de_ventana(fg)
    return {"hwnd": fg, "clase": _clase(fg), "titulo": _texto(fg),
            "pid": pid, "exe": exe}


def escritorio_bloqueado():
    """True si la sesion de Windows esta bloqueada.

    Con la pantalla de bloqueo encima no hay foco que ganar ni pixeles que
    capturar: conviene decirlo con claridad en vez de fallar por foco.
    """
    fg = ventana_al_frente()
    return bool(fg and fg["exe"].lower() in ("lockapp.exe", "logonui.exe"))


def traer_al_frente(hwnd, espera=0.35, intentos=4):
    """Pone la ventana en primer plano, insistiendo.

    Windows niega SetForegroundWindow a un proceso que no tiene ya el foco.
    Se combinan los dos rodeos habituales, en este orden:

      1. AttachThreadInput a la cola del hilo en primer plano + SetForegroundWindow.
      2. SwitchToThisWindow, que no esta sujeto al bloqueo de foco.

    Deliberadamente NO se usa el truco de inyectar un ALT: en una aplicacion
    Java ALT abre la barra de menu, y aqui eso seria una pulsacion fantasma
    dentro de la forma del usuario.
    """
    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, SW_RESTORE)
    if user32.GetForegroundWindow() == hwnd:
        return True

    # Un popup de la propia forma (menu desplegado, LOV, dialogo modal) es una
    # ventana distinta del frame pero del MISMO proceso Java. Ahi el frame nunca
    # sera el foreground, y forzarlo cerraria el popup: se da por bueno.
    objetivo_pid, _ = proceso_de_ventana(hwnd)
    fg = ventana_al_frente()
    if fg and fg["pid"] == objetivo_pid:
        return True

    hilo_actual = kernel32.GetCurrentThreadId()

    for intento in range(intentos):
        actual = user32.GetForegroundWindow()
        hilo_frente = user32.GetWindowThreadProcessId(actual, None) if actual else 0

        enganchado = False
        if hilo_frente and hilo_frente != hilo_actual:
            enganchado = bool(user32.AttachThreadInput(hilo_actual, hilo_frente, True))
        try:
            user32.BringWindowToTop(hwnd)
            user32.SetForegroundWindow(hwnd)
        finally:
            if enganchado:
                user32.AttachThreadInput(hilo_actual, hilo_frente, False)

        time.sleep(espera)
        if user32.GetForegroundWindow() == hwnd:
            return True

        # Segundo rodeo: no pasa por el bloqueo de foco.
        user32.SwitchToThisWindow(hwnd, True)
        time.sleep(espera)
        if user32.GetForegroundWindow() == hwnd:
            return True

    return False


# ── captura ──────────────────────────────────────────────────────────────────

def _grab(left, top, width, height):
    """Captura una region a memoria, como imagen PIL."""
    import mss
    from PIL import Image

    with mss.mss() as sct:
        raw = sct.grab({"left": int(left), "top": int(top),
                        "width": int(width), "height": int(height)})
    return Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")


# Valores de arranque medidos en SAFIX (look&feel Oracle, colorScheme SWAN).
# NO se usan como verdad: solo como pista si el aprendizaje automatico falla.
# La deteccion real APRENDE los colores de la ventana viva, porque cambian con
# el lookAndFeel y el colorScheme del .jnlp y no pueden quedar fijos aqui.
COLOR_TITULO_SUGERIDO = (45, 132, 197)
COLOR_BORDE_SUGERIDO = (72, 100, 141)


def _cerca(c, r, tol=10):
    return all(abs(a - b) <= tol for a, b in zip(c, r))


def _saturado(c, minimo=40):
    """True si el color tiene color de verdad (no gris, no casi blanco).

    Sirve para reconocer una barra de titulo sin saber de que color es: el
    fondo de la forma y los campos son grises o blancos; la barra no.
    """
    return max(c) - min(c) >= minimo


def _rachas(px, y, ancho, predicado):
    """Rachas horizontales contiguas en la fila y que cumplen el predicado."""
    fuera, ini = [], None
    for x in range(ancho + 1):
        hay = x < ancho and predicado(px[x, y])
        if hay and ini is None:
            ini = x
        elif not hay and ini is not None:
            fuera.append((ini, x - 1))
            ini = None
    return fuera


def detectar_ventana(hwnd, minimo_ancho=150):
    """Detecta la ventana MDI activa APRENDIENDO sus colores de la imagen.

    Generaliza a cualquier forma y a cualquier tema: no compara contra
    constantes de color, sino que busca la primera banda horizontal larga de
    un color UNIFORME y SATURADO en la parte de arriba del canvas — eso es
    una barra de titulo, sea del color que sea.

    Devuelve un dict con el recuadro en coordenadas del canvas y los colores
    aprendidos, o None si no encuentra ninguna ventana.
    """
    (cl, ct, cr, cb), _ = canvas_de(hwnd)
    W, H = cr - cl, cb - ct
    if W <= 0 or H <= 0:
        return None
    img = _grab(cl, ct, W, H)
    px = img.load()

    # 1. Fila mas alta que empieza una BANDA: racha larga de un color
    #    saturado que se repite varias filas hacia abajo.
    #    La altura es lo que distingue una barra de titulo de un BORDE: el
    #    borde de la ventana tambien es una racha larga y saturada, pero mide
    #    1 px. Sin esta comprobacion se mide la ventana equivocada.
    ALTO_MINIMO_BANDA = 6
    candidatos = []
    for y in range(H - ALTO_MINIMO_BANDA):
        # Una banda que toca el borde superior del canvas esta CORTADA: es una
        # ventana que quedo fuera de vista porque el area MDI esta desplazada.
        # Tomarla mide la ventana equivocada — pasa al abrir una LOV con el
        # canvas scrolleado.
        if y <= 1:
            continue
        conteo = {}
        for x in range(W):
            c = px[x, y]
            if _saturado(c):
                conteo[c] = conteo.get(c, 0) + 1
        if not conteo:
            continue
        color, veces = max(conteo.items(), key=lambda kv: kv[1])
        if veces < minimo_ancho:
            continue
        rachas = _rachas(px, y, W, lambda c, r=color: _cerca(c, r, 12))
        if not rachas:
            continue
        ini, fin = max(rachas, key=lambda r: r[1] - r[0])
        if fin - ini + 1 < minimo_ancho:
            continue
        cx = (ini + fin) // 2
        if all(_cerca(px[cx, y + d], color, 25) for d in range(ALTO_MINIMO_BANDA)):
            candidatos.append({"y": y, "izq": ini, "der": fin, "color": color})
    if not candidatos:
        return None

    # Cual de las bandas es la ventana ACTIVA: la de color mas SATURADO.
    # Windows/Java pintan la barra de la ventana con foco en su color pleno y
    # las de atras en un tono lavado. Medido en SAFIX: activa (45,132,197),
    # saturacion 152; inactiva (158,193,223), saturacion 65.
    #
    # Sin esta preferencia se tomaba la banda MAS ALTA, que al abrir una LOV es
    # la de la forma de atras — y esa resolvia un recuadro absurdo de todo el
    # canvas en vez de la LOV que se queria fotografiar.
    candidatos.sort(key=lambda c: (-(max(c["color"]) - min(c["color"])), c["y"]))
    for titulo in candidatos:
        r = _resolver_recuadro(px, W, H, titulo, minimo_ancho)
        if r:
            r["canvas"] = (cl, ct, cr, cb)
            return r
    return None


def _resolver_recuadro(px, W, H, titulo, minimo_ancho):
    """Del banda de titulo al recuadro completo, o None si no se puede."""

    izq, der, y_tit = titulo["izq"], titulo["der"], titulo["y"]
    color_titulo = titulo["color"]

    # 2. El borde exterior es la fila justo encima de la barra de titulo.
    if y_tit > 0:
        color_borde = px[izq + 5, y_tit - 1]
        top = y_tit - 1
    else:
        color_borde = color_titulo
        top = y_tit

    # Los bordes reales se toman de la LINEA DE BORDE, no de la racha de
    # color del titulo: el icono de la ventana y el texto del titulo cortan
    # esa racha y dejan el ancho subestimado (se vio 578 donde eran 612), lo
    # que despues hacia descartar el borde inferior por "demasiado ancho".
    if top < y_tit:
        for ini, fin in _rachas(px, top, W, lambda c: _cerca(c, color_borde, 20)):
            if ini <= izq and der <= fin:
                izq, der = ini, fin
                break

    # 3. Fin de la barra de titulo: ultima fila donde el color de titulo
    #    sigue dominando el ancho. NO se puede bajar por el centro porque
    #    ahi esta el TEXTO del titulo y corta el color a media barra.
    fin_titulo = y_tit
    mitad = (der - izq + 1) // 2
    for y in range(y_tit, H):
        if sum(1 for x in range(izq, der + 1)
               if _cerca(px[x, y], color_titulo, 25)) < mitad:
            break
        fin_titulo = y

    # 4. Base: primera linea de color_borde que cruza el ancho y TERMINA en
    #    los bordes. Una ventana mas ancha por detras sigue siendo borde por
    #    fuera, y hay que descartarla o se mide la ventana equivocada.
    ancho = der - izq + 1
    umbral = int(ancho * 0.8)
    base = None
    for y in range(fin_titulo + 10, H):
        if sum(1 for x in range(izq, der + 1)
               if _cerca(px[x, y], color_borde, 20)) < umbral:
            continue
        # Descartar el borde de una ventana MAS ANCHA que este por detras.
        # Muestrear un solo pixel a los lados no sirve: dos ventanas MDI
        # pueden compartir casi el mismo borde izquierdo y quedar a 3 px.
        # Lo que las distingue es CUANTO se extiende la linea.
        rachas = _rachas(px, y, W, lambda c: _cerca(c, color_borde, 20))
        if rachas:
            mas_larga = max(r[1] - r[0] + 1 for r in rachas)
            if mas_larga > ancho + 20:
                continue
        # Se guarda la ULTIMA fila valida, no la primera: dentro de la ventana
        # hay lineas internas del mismo color (el separador de la cabecera de
        # una LOV, por ejemplo) que cruzan todo el ancho, y quedarse con la
        # primera truncaba la captura — una LOV de 326 px salio en 100.
        # Las ventanas mas anchas de detras ya quedaron fuera por la longitud
        # de la racha, asi que bajar hasta el final es seguro.
        base = y
    if base is None:
        return None

    # Un recuadro que abarca casi todo el canvas NO es una ventana de datos:
    # es lo que sale cuando el area MDI esta desplazada y la barra de titulo de
    # la forma quedo cortada, dejando solo una franja de fondo que resuelve
    # cualquier cosa. Mejor devolver None y decirlo que recortar de mas.
    if izq <= 2 and ancho >= W * 0.95:
        return None

    # Tamano minimo plausible de una ventana de datos. Sin esto, con la barra
    # de titulo de la forma fuera de vista el detector se agarraba del CAMPO
    # AMARILLO enfocado (que tambien es una banda saturada y ancha) y recortaba
    # un trozo de 153x57 dandolo por bueno.
    if ancho < 200 or base - top + 1 < 100:
        return None

    return {
        "x": izq, "y": top, "ancho": ancho, "alto": base - top + 1,
        "y_fin_titulo": fin_titulo,
        "color_titulo": color_titulo, "color_borde": color_borde,
    }


def detectar_tabs(hwnd, ventana=None, alto_tira=34):
    """Posicion de cada pestana de la tira, detectada por pixeles.

    Generaliza: no depende de cuantas pestanas tenga la forma, de como se
    llamen ni de donde esten. Se mira la banda inmediatamente debajo de la
    barra de titulo y se buscan bloques claros separados por lineas.

    Devuelve lista de dicts con x/y RELATIVOS a la ventana, mas 'activa'
    para la pestana seleccionada (la que sobresale hacia arriba).
    """
    v = ventana or detectar_ventana_reintentando(hwnd)
    if v is None:
        return []
    cl, ct, cr, cb = v["canvas"]
    img = _grab(cl + v["x"], ct + v["y"], v["ancho"], v["alto"])
    px = img.load()

    def cara_de_tab(c):
        # Las pestanas son claras y poco saturadas; los separadores y el
        # borde son oscuros. Se distingue por luminosidad, no por color,
        # para no depender del tema.
        return (c[0] + c[1] + c[2]) / 3.0 > 150 and not _saturado(c, 60)

    ANCHO_MINIMO_TAB = 22

    def bloques(y):
        return [r for r in _rachas(px, y, v["ancho"], cara_de_tab)
                if r[1] - r[0] + 1 >= ANCHO_MINIMO_TAB]

    # La tira es la fila con MAS bloques separados. Buscarla en vez de
    # asumir un desplazamiento fijo bajo el titulo: ese desplazamiento
    # cambia con la forma, con el tema y con el alto del titulo.
    y0 = v["y_fin_titulo"] - v["y"] + 1
    mejor_y, mejor = None, []
    for y in range(max(y0 - 12, 1), min(y0 + alto_tira + 24, v["alto"] - 1)):
        b = bloques(y)
        if len(b) > len(mejor):
            mejor_y, mejor = y, b
    if mejor_y is None or len(mejor) < 2:
        return []

    # Los bloques detectados son BLANCOS DE CLICK, no limites de pestana:
    # el texto oscuro de cada etiqueta parte la racha clara, asi que una
    # pestana ancha puede dar dos bloques. No importa — cualquier punto del
    # bloque cae sobre la pestana, y los duplicados se descartan despues
    # comparando la captura resultante.
    #
    # NO se informa cual esta activa: distinguirlo por pixeles no resulto
    # fiable (el fondo sobre las pestanas inactivas tambien es claro) y es
    # mejor no afirmarlo que afirmarlo mal. Para saber donde estas, compara
    # la captura.
    return [{"x": (ini + fin) // 2, "y": mejor_y, "ancho": fin - ini + 1}
            for ini, fin in mejor]


def detectar_ventana_reintentando(hwnd, minimo_ancho=150, intentos=3,
                                  espera=0.25):
    """detectar_ventana con reintento: el fallo observado es TRANSITORIO.

    Medido el 2026-09-03: la misma ventana dio None en una llamada y se
    detecto bien 20 segundos despues, sin que nada cambiara en pantalla —
    un repintado a medias basta. Un None transitorio es peor que uno
    permanente, porque el paso siguiente actua a ciegas.
    """
    for i in range(intentos):
        v = detectar_ventana(hwnd, minimo_ancho)
        if v is not None:
            return v
        if i + 1 < intentos:
            time.sleep(espera)
    return None


def rect_ventana_activa(hwnd, minimo_ancho=150):
    """(x, y, ancho, alto) de la ventana activa, en coordenadas del canvas."""
    v = detectar_ventana_reintentando(hwnd, minimo_ancho)
    return None if v is None else (v["x"], v["y"], v["ancho"], v["alto"])



def _rects_por_color(px, W, H, predicado, ancho_minimo, alto_minimo):
    """Rectangulos macizos del color que cumpla el predicado.

    Agrupa rachas horizontales que se apilan con la misma extension en filas
    consecutivas. Lo usan la deteccion de campos (blanco) y la del foco
    (amarillo): el mecanismo es el mismo, solo cambia el color que se busca.

    Devuelve [(x, y, ancho, alto)] relativos a la imagen recibida.
    """
    por_fila = {}
    for y in range(H):
        por_fila[y] = [r for r in _rachas(px, y, W, predicado)
                       if r[1] - r[0] + 1 >= ancho_minimo]

    usados = set()
    fuera = []
    for y in range(H):
        for i, (ini, fin) in enumerate(por_fila[y]):
            if (y, i) in usados:
                continue
            alto, yy = 1, y
            while yy + 1 < H:
                siguiente = None
                for j, (i2, f2) in enumerate(por_fila[yy + 1]):
                    if abs(i2 - ini) <= 2 and abs(f2 - fin) <= 2:
                        siguiente = j
                        break
                if siguiente is None:
                    break
                usados.add((yy + 1, siguiente))
                alto += 1
                yy += 1
            if alto >= alto_minimo:
                fuera.append((ini, y, fin - ini + 1, alto))
    return fuera


def _imagen_ventana(hwnd, ventana=None):
    """(imagen, ventana) de la ventana MDI activa, o (None, None)."""
    v = ventana or detectar_ventana_reintentando(hwnd)
    if v is None:
        return None, None
    cl, ct, _, _ = v["canvas"]
    return _grab(cl + v["x"], ct + v["y"], v["ancho"], v["alto"]), v


def detectar_campos(hwnd, ventana=None, ancho_minimo=40, alto_minimo=10):
    """Rectangulos de los campos EDITABLES de la ventana, por pixeles.

    Un campo habilitado de Forms se pinta casi blanco sobre un fondo gris
    claro, asi que se detecta sin saber nada de la forma. Sirve de referencia
    para calibrar la conversion de unidades del .fmb a pixeles: los campos
    son los objetos cuyo tamano y posicion el .fmb declara con exactitud.

    Devuelve [(x, y, ancho, alto)] en coordenadas RELATIVAS a la ventana.
    """
    img, v = _imagen_ventana(hwnd, ventana)
    if img is None:
        return []

    def blanco(c):
        return c[0] >= 246 and c[1] >= 246 and c[2] >= 246

    return _rects_por_color(img.load(), img.size[0], img.size[1], blanco,
                            ancho_minimo, alto_minimo)


def detectar_foco(hwnd, ventana=None, ancho_minimo=25, alto_minimo=9):
    """Rectangulo del campo QUE TIENE EL FOCO, por su color de resalte.

    Existe por un fallo que no daba ninguna senal: un click que no movia el
    foco dejaba el cursor en el campo anterior, y el `Ctrl+L` siguiente abria
    la lista de OTRO campo. Pedi 'Centro Costos' y salio 'Barrios', sin un
    solo error por ningun lado. Verificar el foco ANTES de pulsar Ctrl+L es la
    unica forma de cazarlo.

    El color no esta fijo: se reconoce por su FIRMA (claro y con el azul muy
    por debajo del rojo y el verde), que es lo que hace amarillo a un amarillo
    en cualquier tema. Devuelve el rectangulo mas grande que la cumpla, con el
    color medido, o None.
    """
    img, v = _imagen_ventana(hwnd, ventana)
    if img is None:
        return None

    def resalte(c):
        r, g, b = c
        return r >= 200 and g >= 185 and b <= min(r, g) - 35

    rects = _rects_por_color(img.load(), img.size[0], img.size[1], resalte,
                             ancho_minimo, alto_minimo)
    if not rects:
        return None
    x, y, a, al = max(rects, key=lambda r: r[2] * r[3])
    px = img.load()
    return {"x": x, "y": y, "ancho": a, "alto": al,
            "color": px[x + a // 2, y + al // 2],
            "cuantos": len(rects)}


# Un cambio "menor" se mide en PIXELES, no en porcentaje del area. Un campo
# de Forms ocupa unos 2.400 px, asi que tres campos caben en 8.000; el mismo
# cambio es 0,26% de la ventana de datos y 3% de un recuadro pequeno, y con un
# umbral porcentual la MISMA diferencia se clasificaba distinto segun donde
# ocurriera. La fraccion se queda solo como tope de cordura, para que en una
# ventana diminuta no se llame "menor" a algo que la cubre entera.
#
# Los dos umbrales viven en ajustes.json: son de los que se afinan probando.


def diferencia_png(ruta_a, ruta_b, umbral=24,
                   menor_pixeles=None, menor_tope=None):
    """Compara dos capturas y dice CUANTO cambio, no solo si cambio.

    Es lo que vuelve medible la regla de los dos estados: en vez de que yo
    juzgue si mover un control 'cambio algo importante', se mide el area que
    cambio. Un panel que aparece mueve mucha superficie; un campo que se pone
    gris, casi nada.

    Y de paso caza el fallo inverso: si la imagen NO cambia cuando se esperaba
    que cambiara, el control no se movio y todo lo que venga despues saldria
    mal PARECIENDO correcto.
    """
    from PIL import Image, ImageChops

    aj = ajustes()
    if menor_pixeles is None:
        menor_pixeles = aj["menor_pixeles"]
    if menor_tope is None:
        menor_tope = aj["menor_tope"]

    a = Image.open(ruta_a).convert("RGB")
    b = Image.open(ruta_b).convert("RGB")
    if a.size != b.size:
        return {"comparable": False,
                "veredicto": "NO COMPARABLES",
                "detalle": f"tamanos distintos: {a.size} vs {b.size}"}

    mascara = ImageChops.difference(a, b).convert("L") \
                        .point(lambda v: 255 if v >= umbral else 0)
    distintos = mascara.histogram()[255]
    total = a.size[0] * a.size[1]
    fraccion = distintos / total if total else 0.0
    caja = mascara.getbbox()

    if distintos == 0:
        veredicto = "IDENTICAS"
    elif distintos <= menor_pixeles and fraccion < menor_tope:
        veredicto = "CAMBIO MENOR"
    else:
        veredicto = "CAMBIO ESTRUCTURAL"

    return {"comparable": True, "veredicto": veredicto,
            "fraccion": round(fraccion, 5), "pixeles": distintos,
            "caja": caja, "tamano": a.size}


def capturar_region(left, top, width, height, destino):
    """Guarda un PNG de la region de pantalla indicada.

    Devuelve (ruta, ancho, alto, diagnostico) donde `diagnostico` es una
    lista de avisos legibles. La idea es que quien llama NO tenga que abrir
    la imagen para saber si sirve: abrir cada PNG para verificarlo era el
    mayor gasto de contexto del proceso.
    """
    if width <= 0 or height <= 0:
        raise ValueError(f"Region invalida: {width}x{height}")

    os.makedirs(os.path.dirname(os.path.abspath(destino)), exist_ok=True)
    img = _grab(left, top, width, height)
    img.save(destino, optimize=True)

    avisos = []
    gris = img.convert("L")
    lo, hi = gris.getextrema()
    if (lo, hi) == (0, 0):
        avisos.append("NEGRA: ventana tapada, minimizada o escritorio bloqueado")
    elif hi - lo < 12:
        avisos.append("PLANA: casi sin contraste, probablemente no es la ventana")

    # Un recorte del tamano de un icono es lo que produjo los 10 archivos de
    # 0 bytes de IFACTURAOPT. La foto de un boton es la VENTANA que abre, con
    # su barra de titulo — no el dibujo del boton.
    bytes_ = os.path.getsize(destino)
    if img.width < 130 or img.height < 70 or bytes_ < 1500:
        avisos.append(
            f"RECORTE MINUSCULO: {img.width}x{img.height} px, {bytes_} bytes. "
            "Si querias la ventana que abre un boton, esto es solo el icono: "
            "usa auto=True para recortar la ventana completa con su titulo.")

    # Si el recorte empieza en una ventana, su barra de titulo activa esta
    # en las primeras filas. Sirve de acuse de que el encuadre es el bueno.
    # Si el recorte empieza en una ventana, sus primeras filas son una banda
    # de color uniforme y saturado: la barra de titulo. Se comprueba SIN
    # saber de que color es, igual que la deteccion, para no volver a atar
    # esto a un tema concreto.
    px = img.load()
    mejor = 0
    for y in range(min(8, img.height)):
        conteo = {}
        for x in range(img.width):
            c = px[x, y]
            if _saturado(c):
                conteo[c] = conteo.get(c, 0) + 1
        if conteo:
            mejor = max(mejor, max(conteo.values()))
    if mejor >= img.width * 0.5:
        avisos.append("encuadre OK: barra de titulo completa en el borde superior")

    return destino, img.width, img.height, avisos


# ── entrada ──────────────────────────────────────────────────────────────────

VK = {
    "ENTER": 0x0D, "RETURN": 0x0D, "TAB": 0x09, "ESC": 0x1B, "ESCAPE": 0x1B,
    "SPACE": 0x20, "BACKSPACE": 0x08, "DELETE": 0x2E, "INSERT": 0x2D,
    "HOME": 0x24, "END": 0x23, "PAGEUP": 0x21, "PAGEDOWN": 0x22,
    "UP": 0x26, "DOWN": 0x28, "LEFT": 0x25, "RIGHT": 0x27,
    "CTRL": 0x11, "SHIFT": 0x10, "ALT": 0x12,
    **{f"F{i}": 0x6F + i for i in range(1, 13)},   # F1=0x70 .. F12=0x7B
    # Letras y digitos: hacen falta para los atajos de SAFIX que los usan.
    # El mas importante es CTRL+L, que abre la lista de valores del campo
    # activo: es la unica via DETERMINISTA de abrir una LOV. Cazar la flecha
    # azul por pixeles falla (la ventana MDI se mueve) y F9 no es la tecla.
    **{chr(c): c for c in range(0x41, 0x5B)},      # A..Z
    **{chr(c): c for c in range(0x30, 0x3A)},      # 0..9
}


def _tecla(vk, up=False):
    return INPUT(type=INPUT_KEYBOARD,
                 ki=KEYBDINPUT(wVk=vk, wScan=0,
                               dwFlags=KEYEVENTF_KEYUP if up else 0,
                               time=0, dwExtraInfo=0))


def pulsar(combinacion):
    """Pulsa una combinacion tipo 'F8', 'CTRL+S', 'SHIFT+TAB'."""
    partes = [p.strip().upper() for p in combinacion.split("+") if p.strip()]
    if not partes:
        raise ValueError("Combinacion vacia")
    vks = []
    for p in partes:
        if p not in VK:
            raise ValueError(f"Tecla no reconocida: {p!r}. Validas: {', '.join(sorted(VK))}")
        vks.append(VK[p])
    _enviar(*[_tecla(v) for v in vks],
            *[_tecla(v, up=True) for v in reversed(vks)])


def escribir(texto):
    """Escribe texto literal como caracteres Unicode (no depende del teclado)."""
    eventos = []
    for ch in texto:
        for up in (False, True):
            eventos.append(INPUT(
                type=INPUT_KEYBOARD,
                ki=KEYBDINPUT(wVk=0, wScan=ord(ch),
                              dwFlags=KEYEVENTF_UNICODE | (KEYEVENTF_KEYUP if up else 0),
                              time=0, dwExtraInfo=0)))
        # SendInput acepta lotes; se manda por tandas para no armar arrays enormes.
        if len(eventos) >= 200:
            _enviar(*eventos)
            eventos = []
    if eventos:
        _enviar(*eventos)


def click(x, y, boton="izquierdo", doble=False):
    """Click en coordenadas absolutas de pantalla."""
    vx = user32.GetSystemMetrics(SM_XVIRTUALSCREEN)
    vy = user32.GetSystemMetrics(SM_YVIRTUALSCREEN)
    vw = user32.GetSystemMetrics(SM_CXVIRTUALSCREEN)
    vh = user32.GetSystemMetrics(SM_CYVIRTUALSCREEN)

    nx = int(round((x - vx) * 65535 / max(vw - 1, 1)))
    ny = int(round((y - vy) * 65535 / max(vh - 1, 1)))
    flags_base = MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_VIRTUALDESK

    if boton == "derecho":
        down, up = MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP
    else:
        down, up = MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP

    def mi(flags):
        return INPUT(type=INPUT_MOUSE,
                     mi=MOUSEINPUT(dx=nx, dy=ny, mouseData=0,
                                   dwFlags=flags_base | flags, time=0, dwExtraInfo=0))

    _enviar(mi(MOUSEEVENTF_MOVE))
    time.sleep(0.05)
    _enviar(mi(down), mi(up))
    if doble:
        time.sleep(0.06)
        _enviar(mi(down), mi(up))

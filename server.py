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
import json
import os
import re
import subprocess
import time

from mcp.server.mcpserver import MCPServer  # mcp 2.x: antes se llamaba FastMCP

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


mcp = MCPServer("forms-vision")
w.set_dpi_awareness()

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


def _bitacora(accion, detalle="", resultado="", avisos=None, nivel="ok"):
    """Anota una linea por accion en un .log del dia.

    Existe porque una corrida de ~90 fotos es larga y desatendida: sin
    registro no hay forma de saber DESPUES que se pidio, que salio y que
    quedo a medias. Escribir la bitacora no debe poder tumbar una captura,
    asi que cualquier fallo aqui se traga a proposito.
    """
    try:
        os.makedirs(BITACORA, exist_ok=True)
        ruta = os.path.join(BITACORA, f"{dt.date.today().isoformat()}.log")
        marca = {"ok": "  ", "aviso": "! ", "falla": "XX"}.get(nivel, "  ")
        linea = (f"{dt.datetime.now():%H:%M:%S} {marca} {accion:<14} "
                 f"{detalle}")
        if resultado:
            linea += f"  -> {os.path.basename(str(resultado))}"
        with open(ruta, "a", encoding="utf-8") as f:
            f.write(linea + "\n")
            for a in (avisos or []):
                f.write(f"{'':>9} ..  {a}\n")
    except Exception:
        pass


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


# ── inspeccion ───────────────────────────────────────────────────────────────

@mcp.tool()
def forms_ventanas() -> str:
    """Estado de la sesion de Forms: ventanas, canvas y la ventana MDI activa.

    Es la herramienta de diagnostico: dice si hay sesion, si esta minimizada
    o bloqueada, cual es el origen de coordenadas y donde esta la ventana de
    datos que forms_capturar(auto=True) va a recortar.
    """
    if w.escritorio_bloqueado():
        return ("La sesión de Windows está BLOQUEADA. Desbloquea el equipo: "
                "sin escritorio activo no hay pixeles que leer.")
    wins = w.ventanas_java()
    if not wins:
        return "No hay ventanas de Forms visibles."

    out = []
    for v in wins:
        (cl, ct, cr, cb), _ = w.canvas_de(v["hwnd"])
        lineas = [f"hwnd=0x{v['hwnd']:X}  pid={v['pid']}  {v['clase']}",
                  f"  titulo : {v['titulo']}",
                  f"  frame  : {v['rect']}  ({v['ancho']}x{v['alto']} px)"]
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
        return f"No existe el archivo JNLP: {ruta}"

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
    return (f"No se logro enfocar 0x{h:X}.{detalle} Puede haber un diálogo "
            "modal encima, o otra aplicación reteniendo el foco.")


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
                   auto: bool = False, comparar_con: str = "") -> str:
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
    """
    h = _resolver(int(hwnd, 0) if hwnd else None)
    if not w.traer_al_frente(h):
        if w.escritorio_bloqueado():
            return ("La sesión de Windows está BLOQUEADA: solo se capturaria la "
                    "pantalla de bloqueo. Desbloquea el equipo y reintenta.")
        return ("No se pudo poner la ventana en primer plano; la captura saldria "
                "tapada o negra. Cierra el dialogo que este encima y reintenta.")

    (cl, ct, cr, cb), _ = w.canvas_de(h)
    if incluir_marco:
        cl, ct, cr, cb = w.rect(h)

    if auto:
        r = w.rect_ventana_activa(h)
        if r is None:
            return ("No se pudo detectar la ventana activa dentro del canvas. "
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
    ruta, aw, ah, avisos = w.capturar_region(left, top, ww, hh, destino)

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
                    avisos.append("OJO: nada cambio. Si esperabas un cambio, "
                                  "el control NO se movio: no sigas la pasada.")
                elif d["veredicto"] == "CAMBIO MENOR":
                    avisos.append("cambio de uno o dos campos: basta UNA foto; "
                                  "el detalle va en el texto del manual.")
                else:
                    avisos.append("cambia lo que el usuario puede hacer: "
                                  "van LAS DOS versiones, con el estado en el nombre.")

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


# ── planificacion desde el extract ───────────────────────────────────────────

# Verbos que ESCRIBEN o lanzan procesos: un boton que los contenga no se pulsa
# nunca durante una sesion de fotos. Salio de encontrar un COMMIT dentro de
# BTN_NUEVOHIJO en binmueb, a 30 px del boton que si habia que usar.
# Los verbos que hacen peligroso a un boton viven en ajustes.json.
VERBOS_SEGUROS = ("SHOW_VIEW", "SHOW_WINDOW", "GO_BLOCK", "EXECUTE_QUERY",
                  "LIST_VALUES", "HIDE_VIEW", "GO_ITEM")


def _visibilidad_tabs(textos):
    """Tab pages que el codigo prende y apaga, y bajo que condicion.

    Sin esto el plan exige foto de TODAS las tab pages declaradas en el
    .fmb, y muchas forman juegos MUTUAMENTE EXCLUYENTES: en binmueb un solo
    checkbox decide si se ven CONSOLIDADO/CONSOLIDADO_NIIF o bien
    GENERAL/ESCRITURA/SALDOS/ESTATUS/OBLIGACIONES. Pedir las 14 a la vez es
    pedir algo imposible.

    Devuelve {tab: [(condicion, rama, valor)]}. La condicion se toma del IF
    mas cercano hacia arriba: es una heuristica sobre el texto del PL/SQL,
    no un analisis sintactico, y se reporta como tal.
    """
    import re as _re
    fuera = {}
    for texto in textos:
        cond, rama = None, "then"
        for linea in texto.splitlines():
            l = linea.strip()
            m = _re.match(r"IF\s+(.+?)\s+THEN", l, _re.I)
            if m:
                cond, rama = m.group(1).strip(), "then"
                continue
            if _re.match(r"ELSE\s*$", l, _re.I):
                rama = "else"
                continue
            if _re.match(r"END\s+IF", l, _re.I):
                cond, rama = None, "then"
                continue
            m = _re.search(r"set_tab_page_property\s*\(\s*'([^']+)'\s*,\s*"
                           r"visible\s*,\s*(property_true|property_false)", l, _re.I)
            if m:
                tab = m.group(1).split(".")[-1].upper()
                valor = m.group(2).lower().endswith("true")
                fuera.setdefault(tab, []).append((cond or "(sin IF)", rama, valor))
    return fuera


def _analizar_rutas(cargar):
    """Quien invoca a cada canvas/ventana, leyendo solo el extract.

    Con esto el plan deja de ser una lista optimista de todo lo declarado y
    puede decir por adelantado que NO tiene sentido intentar:

      ROTA      se invoca un objetivo que no existe en el .fmb
                (en binmueb: Show_view('INVERSION') y Show_view('PROMESA'))
      HUERFANA  el objetivo existe pero NADIE lo invoca
                (en binmueb: VALORES, FECHAS, CONCEPTOS)
      ENCERRADA solo se invoca desde dentro de otra ventana secundaria
                (en binmueb: WIN_PREDIO <-> WIN_FECHVAL_PREDIOS)
    """
    import re as _re

    bloques = cargar("01_bloques.json")
    canvases = cargar("07_canvases.json")
    ventanas = cargar("11_ventanas.json")

    donde = {}
    for b in bloques:
        for it in (b.get("items") or []):
            donde[it["nombre"]] = (it.get("canvas") or "", it.get("tab_page") or "")

    nombres_canvas = {c["nombre"].upper() for c in canvases}
    nombres_ventana = {v["nombre"].upper() for v in ventanas}
    ventana_del_canvas = {c["nombre"].upper(): (c.get("ventana") or "").upper()
                          for c in canvases}

    invocadores = {}
    for archivo in ("02_triggers_form.json", "03_triggers_bloque.json",
                    "04_triggers_item.json", "06_program_units.json"):
        def recorrer(o, item_actual=None):
            if isinstance(o, dict):
                codigo = o.get("codigo") or o.get("cuerpo")
                if isinstance(codigo, str):
                    for verbo, obj in _re.findall(
                            r"(show_view|show_window)\s*\(\s*'([^']+)'", codigo, _re.I):
                        objetivo = obj.split(".")[-1].upper()
                        cv, tab = donde.get(item_actual or "", ("", ""))
                        invocadores.setdefault(objetivo, []).append(
                            {"item": item_actual or "(program unit)",
                             "canvas": cv, "tab": tab, "verbo": verbo.lower()})
                for k, v in o.items():
                    recorrer(v, k if k in donde else item_actual)
            elif isinstance(o, list):
                for v in o:
                    recorrer(v, item_actual)
        recorrer(cargar(archivo))

    existentes = nombres_canvas | nombres_ventana
    rotas = {k: v for k, v in invocadores.items() if k not in existentes}

    def encerrada(objetivo):
        """True si solo se invoca desde dentro de una ventana secundaria."""
        invs = invocadores.get(objetivo, [])
        if not invs:
            return False
        for i in invs:
            win = ventana_del_canvas.get((i["canvas"] or "").upper(), "")
            if not i["canvas"] or win in ("", "WIN_APLICACION"):
                return False          # hay al menos un invocador accesible
        return True

    return {"invocadores": invocadores, "rotas": rotas,
            "existentes": existentes, "encerrada": encerrada,
            "ventana_del_canvas": ventana_del_canvas}


# Prefijos de la nomenclatura XENCO. El nombre de cada foto es la RUTA DE
# NAVEGACION acumulada, empezando por la pestana:
#     NN_<pestana>_<radio/panel>_<prefijo>_<elemento>.png
# Las etiquetas se leen de la PANTALLA, no del .fmb; lo que sale aqui es una
# propuesta a partir del prompt, que suele coincidir pero no manda.
# Los prefijos del nombre de archivo viven en ajustes.json.

# Los items de SAFIX casi nunca declaran su tipo: lo HEREDAN de una clase de
# propiedades, y el .fmb solo trae ItemType en el item que se desvia de ella.
# En iplanosopt lo declara 1 de 301, asi que `tipo_visual` sale 'Text Item'
# para 293 items — incluidos el grupo de radios, 64 casillas, 8 desplegables y
# los botones. Clasificar por `tipo_visual` es clasificar por el valor por
# defecto del extractor.
#
# `parent_name` (el ParentName del XML) SI dice de que clase hereda, y es la
# senal fiable. `tipo_visual` se queda como respaldo para las formas donde el
# item si declara su tipo.
# El mapa parent_name -> clase vive en ajustes.json.

# Sufijos de un extremo de rango. Los dos extremos abren la MISMA lista, asi
# que se fotografia una vez y el nombre va sin el sufijo.
# Los sufijos de rango viven en ajustes.json.


def _clase_control(it, riesgo_boton):
    """Que clase de control es, por `parent_name` y con `tipo_visual` de respaldo."""
    parent = (it.get("parent_name") or "").upper()
    tipo = it.get("tipo_visual") or ""
    nombre = it["nombre"]

    if it.get("radio_buttons") or tipo == "Radio Group" or parent == "RADIO_GROUP":
        return "RADIO"
    mapa = w.ajustes()["clase_por_parent"]
    if parent in mapa:
        clase = mapa[parent]
        # Un item con LOV colgada manda sobre la clase heredada: hay campos
        # TEXT_NORMAL con lov_name (VKPCODIGO, VMODULO) cuya flecha es un item
        # aparte, y la foto que interesa es la lista.
        if (clase.startswith("OMITIR") and it.get("lov_name")
                and clase != "OMITIR_ESPEJO"):
            return "LOV"
        return clase
    if it.get("lov_name"):
        return "LOV"
    if tipo == "Check Box":
        return "CHECK"
    if tipo == "List Item":
        return "LISTA"
    if nombre in riesgo_boton or tipo == "Push Button":
        return "BOTON"
    return "OMITIR_TEXTO"


def _colapsar_rangos(elementos):
    """Une los pares Inicial/Final que abren la misma lista.

    En `optica` de iplanosopt hay 10 flechas azules y solo 5 listas reales:
    Diseno, Tipo Lente, Clase Lente, Estilo Montura y Antireflejo, cada una
    con su extremo inicial y su extremo final. Fotografiar las 10 produce
    cinco parejas de fotos identicas.
    """
    def raiz(archivo):
        for s in w.ajustes()["sufijos_rango"]:
            if archivo.endswith(s):
                return archivo[: -len(s)]
        return None

    vistos, fuera = {}, []
    for e in elementos:
        r = raiz(e["archivo"]) if e["clase"] in ("LOV", "LISTA") else None
        if r is None:
            fuera.append(e)
            continue
        if r in vistos:
            otro = vistos[r]
            otro["nota"] += f" · mismo par que {e['item']} (rango: una sola foto)"
            otro["item"] += f" / {e['item']}"
            continue
        e = {**e, "archivo": r}
        vistos[r] = e
        fuera.append(e)
    return _colapsar_rejilla(fuera)


# Por encima de esto, un grupo de casillas es una REJILLA DE SELECCION, no un
# juego de controles que cambian la pantalla. En `campos` de iplanosopt hay 59
# ('Vendedor?', 'Grupo?', 'Lote?'...) y eligen que columnas lleva el archivo
# plano: cambian el RESULTADO, no la forma. Listarlas una por una produce 59
# filas de plan y tienta a tomar 118 fotos de la misma pantalla.
# rejilla_minima vive en ajustes.json


def _colapsar_rejilla(elementos):
    """Reduce una rejilla de casillas a una fila, y sin foto propia."""
    checks = [e for e in elementos if e["clase"] == "CHECK?"]
    if len(checks) < w.ajustes()["rejilla_minima"]:
        return elementos
    muestra = ", ".join(e["etiqueta"] for e in checks[:4])
    resto = [e for e in elementos if e["clase"] != "CHECK?"]
    return resto + [{
        "clase": "IGNORAR", "item": f"{len(checks)} casillas",
        "etiqueta": f"{muestra}, …",
        "archivo": "— (ya salen en la foto de la seccion)",
        "nota": f"{len(checks)} casillas juntas = rejilla de seleccion: eligen "
                "que sale en el RESULTADO, no cambian la forma. SIN foto "
                "propia. Confirmalo con un diff sobre una: si diera CAMBIO "
                "ESTRUCTURAL, entonces si son controles de pantalla",
        "obvio": False,
    }]


def _slug(texto):
    """Etiqueta de pantalla -> fragmento de nombre de archivo."""
    import re as _re
    t = (texto or "").strip().strip(":").lower()
    for a, b in (("á", "a"), ("é", "e"), ("í", "i"), ("ó", "o"), ("ú", "u"),
                 ("ñ", "n"), ("ü", "u")):
        t = t.replace(a, b)
    t = _re.sub(r"[^a-z0-9]+", "_", t).strip("_")
    return t or "sin_nombre"


def _probablemente_obvio(prompt, titulo_lov):
    """True si el contenido de la LOV se adivina por la etiqueta del campo.

    Regla del usuario: si los datos que muestra la LOV van acordes al nombre
    del campo, se puede omitir la foto (campo 'Ciudad' -> lista de ciudades).
    Es una SUGERENCIA: la decision final es de quien captura, mirando.
    """
    p, t = _slug(prompt), _slug(titulo_lov)
    if not p or not t:
        return False
    return p == t or t.startswith(p) or p.startswith(t) or t == p + "s"


def _elementos_de_seccion(bloques, lov_titulo, riesgo_boton, canvas, tab):
    """Elementos fotografiables de una seccion, con su nombre propuesto."""
    # La flecha azul es un item APARTE del campo al que pertenece, y se llama
    # BTN_<CAMPO>. Sin esto el encabezado de iplanosopt listaba 6 LOVs para 3
    # listas reales: el campo con su lov_name, y su flecha otra vez.
    en_seccion = {
        it["nombre"].upper()
        for b in bloques for it in (b.get("items") or [])
        if (it.get("canvas") or "") == canvas and (it.get("tab_page") or "") == tab
    }

    fuera = []
    for b in bloques:
        for it in (b.get("items") or []):
            if (it.get("canvas") or "") != canvas:
                continue
            if (it.get("tab_page") or "") != tab:
                continue
            if (it.get("visible") or "true").lower() == "false":
                continue

            clase = _clase_control(it, riesgo_boton)
            if clase.startswith("OMITIR"):
                continue
            # Flecha cuyo campo esta en la misma seccion: la foto ya sale por
            # el campo, que ademas si tiene etiqueta.
            if (clase == "LOV" and not it.get("lov_name")
                    and it["nombre"].upper().startswith("BTN_")
                    and it["nombre"].upper()[4:] in en_seccion):
                continue
            prompt = (it.get("prompt") or it.get("label") or "").strip(": ")
            nombre = it["nombre"]
            # Sin prompt no hay etiqueta de pantalla en el .fmb. Se cae al
            # nombre interno pero MARCADO, para que quede claro que hay que
            # leerlo de la captura y no usarlo tal cual en el archivo.
            # El extract trae acentos mutilados: 'Dise?o Inicial' por 'Diseño'.
            # Un '?' EN MEDIO de la etiqueta es una tilde perdida, no una
            # pregunta ('Inconsistencias?' si acaba en ?, y es legitimo). Si se
            # deja pasar, el archivo sale 'lov_dise_o'.
            roto = "?" in prompt.rstrip("?")
            etiqueta = (f"{prompt}  [acento mutilado]" if roto
                        else prompt or f"? {nombre}")
            base_nombre = ("<leer_en_pantalla>" if roto or not prompt
                           else _slug(prompt))

            if clase == "LOV":
                titulo = lov_titulo.get(it.get("lov_name") or "", "")
                fuera.append({
                    "clase": "LOV", "item": nombre, "etiqueta": etiqueta,
                    "archivo": w.ajustes()["prefijo"]["LOV"] + base_nombre,
                    "nota": (f"LOV {it['lov_name']}" if it.get("lov_name")
                             else "flecha azul (PBUTTON_LIST)")
                            + (f" · titulo {titulo!r}" if titulo else ""),
                    "obvio": _probablemente_obvio(prompt, titulo),
                })
            elif clase == "LISTA":
                fuera.append({
                    "clase": "LISTA", "item": nombre, "etiqueta": etiqueta,
                    "archivo": w.ajustes()["prefijo"]["LISTA"] + base_nombre,
                    "nota": "desplegable en el sitio; los valores solo se ven "
                            "en ejecucion",
                    "obvio": False,
                })
            elif clase == "LINK":
                fuera.append({
                    "clase": "LINK", "item": nombre, "etiqueta": etiqueta,
                    "archivo": w.ajustes()["prefijo"]["LINK"] + base_nombre,
                    "nota": "etiqueta clickeable: fotografiar lo que hace al pulsar",
                    "obvio": False,
                })
            elif clase == "CHECK":
                # Una casilla NO lleva foto por existir. Solo si al marcarla
                # cambia la forma (aparecen campos, paneles o pestanas) o abre
                # algo. Si lo unico que cambia es el recuadro, se ignora: la
                # casilla ya se ve en la foto de la seccion.
                fuera.append({
                    "clase": "CHECK?", "item": nombre, "etiqueta": etiqueta,
                    "archivo": w.ajustes()["prefijo"]["CHECK"] + base_nombre,
                    "nota": "marcar y comparar. CAMBIO ESTRUCTURAL -> las dos "
                            "versiones. CAMBIO MENOR (solo el recuadro) -> "
                            "SIN FOTO, se ignora",
                    "obvio": False,
                })
            elif clase == "RADIO":
                radios = it.get("radio_buttons") or []
                if radios:
                    for rb in radios:
                        et = (rb.get("label") or rb.get("nombre") or "")
                        fuera.append({
                            "clase": "RADIO", "item": f"{nombre}.{rb.get('nombre')}",
                            "etiqueta": et,
                            "archivo": w.ajustes()["prefijo"]["RADIO"] + _slug(et),
                            "nota": f"valor {rb.get('valor')!r}",
                            "obvio": False,
                        })
                else:
                    fuera.append({
                        "clase": "RADIO", "item": nombre,
                        "etiqueta": "(no esta en el extract)",
                        "archivo": w.ajustes()["prefijo"]["RADIO"] + "<leer_en_pantalla>",
                        "nota": "el .fmb no trae las etiquetas: leerlas de la captura",
                        "obvio": False,
                    })
            else:
                # Ser boton se decide por TENER un WHEN-BUTTON-PRESSED, no por
                # el tipo ni por el nombre: en SAFIX hay botones declarados como
                # 'Text Item' y sin prefijo BTN_ (p.ej. PROTOCOLO en binmueb),
                # y filtrarlos por nombre los dejaba fuera de la lista de
                # peligrosos, que es justo donde tienen que estar.
                riesgo, motivo = riesgo_boton.get(nombre, ("revisar", ""))
                # El nombre interno ya suele traer BTN_: no duplicar el prefijo.
                frag = base_nombre
                if frag.startswith("btn_"):
                    frag = frag[4:]
                elif not prompt:
                    frag = _slug(nombre).removeprefix("btn_") or "<leer_en_pantalla>"
                if riesgo == "NO TOCAR":
                    fuera.append({
                        "clase": "PELIGRO", "item": nombre,
                        "etiqueta": etiqueta, "archivo": "—",
                        "nota": f"NO PULSAR: {motivo}", "obvio": False,
                    })
                else:
                    fuera.append({
                        "clase": "BOTON", "item": nombre, "etiqueta": etiqueta,
                        "archivo": w.ajustes()["prefijo"]["BOTON"] + frag,
                        "nota": (f"{riesgo}: {motivo}" if motivo else riesgo)
                                + " · la VENTANA que abre, CON barra de titulo. "
                                  "Nada de recortar el icono: sale de 0 KB",
                        "obvio": False,
                    })
    return _colapsar_rangos(fuera)


def _clasificar(codigo):
    """(riesgo, motivo) de un WHEN-BUTTON-PRESSED."""
    alto = [v for v in w.ajustes()["verbos_peligrosos"]
            if v in codigo.upper()]
    if alto:
        return "NO TOCAR", "+".join(v.strip() for v in alto)
    if "OPEN_FORM" in codigo.upper() or "CALL_FORM" in codigo.upper():
        import re as _re
        otras = _re.findall(r"(?:OPEN_FORM|CALL_FORM)\s*\(\s*'([^']+)'", codigo, _re.I)
        return "otra forma", ",".join(otras) or "?"
    seguros = [v for v in VERBOS_SEGUROS if v in codigo.upper()]
    if seguros:
        return "seguro", "+".join(seguros)
    return "revisar", "sin verbo reconocido"


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

        if not invs:
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
        if es_win:
            vt = titulo_ventana.get(ventana_de.get(cv, ""), "") or ventana_de.get(cv, "")
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
# Se comparan en MINUSCULA: la primera version distinguia mayusculas y se le
# escapo "no se detecto la ventana activa" porque el marcador decia "No se
# detecta". El lote siguio, CTRL+L disparo y la foto se guardo con el nombre
# de una lista que nunca se abrio. Un marcador que falla por una tilde o una
# mayuscula no es una guarda.
# Los marcadores que detienen un lote viven en ajustes.json.


def _es_fallo(salida):
    """Motivo por el que un paso cuenta como fallo, o None si fue bien."""
    bajo = salida.lower()
    for marca, motivo in w.ajustes()["marcas_fallo"]:
        if marca in bajo:
            return motivo
    return None


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
        # espacios ("Bienes e inmuebles") y shlex partia
        # carpeta="Z:\...\Bienes e inmuebles\X" en tres tokens, con lo que
        # llegaba un argumento llamado 'e'. La clave es siempre un
        # identificador, asi que el valor es todo lo que va hasta la siguiente
        # clave o hasta el final — entre comillas o sin ellas.
        kwargs = {}
        for k, v_ent, v_com in re.findall(
                r'([A-Za-z_][A-Za-z0-9_]*)=(?:"([^"]*)"|(\S*))', cola):
            v = v_ent if v_ent else v_com
            if v.lower() in ("true", "false"):
                kwargs[k] = v.lower() == "true"
            else:
                try:
                    kwargs[k] = int(v)
                except ValueError:
                    try:
                        kwargs[k] = float(v)
                    except ValueError:
                        kwargs[k] = v
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
        return ("no se detecta ninguna ventana activa: no se pulsa a ciegas")
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
        return None, "No se detecta la ventana activa: no se puede calibrar."
    # OJO con el ORDEN: la referencia de "ventana de datos" se apunta al FINAL,
    # cuando el ajuste ya salio bien. Apuntarla aqui envenenaba la guarda: con
    # un mensaje de 321x155 delante, la calibracion fallaba por falta de campos
    # PERO ya habia registrado 321x155 como la ventana de datos, y a partir de
    # ahi forms_cerrar_popup contestaba "delante esta la ventana de datos" con
    # el mensaje encima. Paso el 2026-09-03.
    campos = w.detectar_campos(hwnd, v)
    if len(campos) < 3:
        return None, (f"Solo {len(campos)} campos blancos detectados; hacen falta "
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
        return None, "El .fmb declara menos de 3 campos anchos en esta seccion."

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
        return None, (f"Ajuste pobre: {n} encajes con residuo {res:.1f} px. "
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
              f"  {cal['encajes']} de {cal['de']} campos encajan · "
              f"residuo medio {cal['residuo']} px\n"
              "  Los que no encajan suelen ser campos deshabilitados: en gris "
              "no hay area blanca que detectar.")
    aviso = _contrastar_calibracion(forma, canvas, tab, estado, cal)
    return salida + aviso if not aviso else salida + "\n" + aviso


# Un ajuste con POCOS encajes puede cuadrar en un optimo falso y ensenar un
# residuo bueno: el residuo solo mide los puntos que encajaron, no si el
# desplazamiento es el correcto. Medido el 2026-09-03 en IMAGENES: 3 encajes de
# 4 dieron off_y=82 con residuo 0.63 px, cuando el valor real de CNV_TAB es 64
# (cuatro calibraciones independientes coincidieron). Los clicks salian 27 px
# abajo y el boton no se pulsaba — sin ningun error.
# encajes_fiables vive en ajustes.json


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
        return (f"Falta calibrar {canvas}/{tab or '(sin tab)'}"
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
            return (f"'{item}' no tiene el radio '{radio}'. "
                    f"Tiene: {', '.join(disponibles) or '(ninguno)'}")
        # Un radio es un circulo pequeno con su etiqueta a la derecha: el
        # punto de click va sobre el circulo, no en el centro de la etiqueta.
        objetivo = {**objetivo, "x": rb.get("x"), "y": rb.get("y"),
                    "ancho": 8, "alto": 8,
                    "tipo_visual": f"Radio '{rb.get('label') or radio}'"}
    if objetivo is None:
        nombres = [i["nombre"] for i in _items_de(forma, canvas, tab)
                   if item.upper() in i["nombre"].upper()][:8]
        return (f"No existe '{item}' en {canvas}/{tab}."
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
                    return (f"NO se pulsa '{item}': su codigo contiene {motivo}. "
                            "Escribe en la base de datos o lanza un proceso.")

    try:
        fx, fy = int(objetivo["x"]), int(objetivo["y"])
    except (ValueError, KeyError, TypeError):
        return f"'{item}' no declara posicion en el .fmb; no se puede calcular."
    fa = int(objetivo.get("ancho") or 0) or 14
    fh = int(objetivo.get("alto") or 0) or 14

    estorbo = _exigir_ventana_datos(h)
    if estorbo:
        return f"NO se pulsa '{item}': {estorbo}."

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
    return ("OJO foco EQUIVOCADO: el resalte esta en " + donde +
            f", no en ({cx},{cy}). El click no movio el foco: un Ctrl+L ahora "
            "abriria la lista de otro campo. Repite el click o salta el elemento.")


@mcp.tool()
def forms_cerrar_popup(hwnd: str = "", ancho_datos: int = 600,
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
        r = _cerrar_uno(hwnd, ancho_datos)
        if r.startswith("Cerrado"):
            cerrados.append(r)
            continue
        if cerrados and ("no hay recuadro que cerrar" in r
                         or "nada que cerrar" in r):
            return (f"{len(cerrados)} recuadro(s) cerrado(s): "
                    + " | ".join(x.replace("Cerrado el ", "") for x in cerrados))
        return r if not cerrados else f"{' | '.join(cerrados)} — y luego: {r}"
    return " | ".join(cerrados) or r


def _cerrar_uno(hwnd, ancho_datos):
    h = _resolver(int(hwnd, 0) if hwnd else None)
    _exigir_frente(h)
    v = w.detectar_ventana_reintentando(h)
    if v is None:
        return "No se detecta ningun recuadro; nada que cerrar."

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
    if v["alto"] > 250:
        # Cancel medido en el recuadro de 466x326: ocupa x 303..347, centro
        # 325 = 69.7%. La primera version usaba 74.7% (x 348), UN PIXEL fuera
        # del borde derecho: cerraba unas veces y otras no, y una LOV que se
        # queda abierta se lleva por delante todo lo que venga detras.
        # NUNCA se pulsa OK: eso SELECCIONA un valor y lo escribe en el campo.
        fx, fy, tipo, boton = 0.697, 0.936, "LOV", "Cancel"
    else:
        fx, fy, tipo, boton = 0.84, 0.84, "mensaje", "Aceptar"
    cx, cy = int(v["ancho"] * fx), int(v["alto"] * fy)
    forms_click(x=cx, y=cy, hwnd=hwnd, relativo=True)
    time.sleep(1.2)
    v2 = w.detectar_ventana_reintentando(h)
    sigue = (v2 and abs(v2["ancho"] - datos[0]) > 8 if datos
             else v2 and v2["ancho"] < ancho_datos)
    if sigue:
        return (f"Se pulso {boton} del {tipo} pero sigue habiendo un recuadro "
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
        return "No se detecto la ventana activa."
    tabs = w.detectar_tabs(h, v)
    if not tabs:
        return ("No se detecto tira de pestanas. Puede que esta forma no "
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
        return f"No se pudo leer {carpeta_fotos}: {e}"

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

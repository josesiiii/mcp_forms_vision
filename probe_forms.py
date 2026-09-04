"""
Sonda de diagnostico - Oracle Forms (Java Web Start) en Windows.

NO envia teclas ni clicks: solo enumera ventanas y captura pixeles.
Objetivo: responder tres preguntas antes de construir el MCP.

  P1  Que ventanas top-level publica el runtime de Forms y con que titulo/clase.
  P2  Expone hijos nativos (Windows UIA/MSAA) o es un unico rectangulo opaco.
  P3  La captura por region funciona sobre una ventana Java (o sale negra).

Uso:  python probe_forms.py [carpeta_salida]
"""

import ctypes
import ctypes.wintypes as wt
import os
import sys

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

PROCESS_QUERY_LIMITED_INFORMATION = 0x1000


def set_dpi_awareness():
    """Sin esto, GetWindowRect miente en pantallas con escalado != 100%."""
    try:
        # DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2
        user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
        return "per-monitor-v2"
    except Exception:
        try:
            ctypes.WinDLL("shcore").SetProcessDpiAwareness(2)
            return "per-monitor-v1"
        except Exception:
            user32.SetProcessDPIAware()
            return "system"


def process_name(pid):
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


def window_text(hwnd):
    n = user32.GetWindowTextLengthW(hwnd)
    buf = ctypes.create_unicode_buffer(n + 1)
    user32.GetWindowTextW(hwnd, buf, n + 1)
    return buf.value


def class_name(hwnd):
    buf = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, buf, 256)
    return buf.value


def rect(hwnd):
    r = wt.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(r))
    return (r.left, r.top, r.right, r.bottom)


ENUMPROC = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)


def children(hwnd, depth=0, out=None, limit=400):
    """Enumera hijos nativos. En Swing/AWT lo normal es que devuelva 0."""
    if out is None:
        out = []

    def cb(child, _):
        if len(out) >= limit:
            return False
        out.append((depth, child, class_name(child), window_text(child)[:60], rect(child)))
        children(child, depth + 1, out, limit)
        return True

    user32.EnumChildWindows(hwnd, ENUMPROC(cb), 0)
    return out


def java_windows():
    found = []

    def cb(hwnd, _):
        if not user32.IsWindowVisible(hwnd):
            return True
        pid = wt.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        pname = process_name(pid.value).lower()
        if pname in ("java.exe", "javaw.exe", "jp2launcher.exe", "javaws.exe"):
            l, t, r, b = rect(hwnd)
            if r - l > 50 and b - t > 50:
                found.append((hwnd, pid.value, pname, class_name(hwnd), window_text(hwnd)))
        return True

    user32.EnumWindows(ENUMPROC(cb), 0)
    return found


def capture(hwnd, path):
    """Captura la region de pantalla ocupada por la ventana.

    Se captura de PANTALLA, no con PrintWindow: sobre ventanas Java
    PrintWindow suele devolver negro. Precio: la ventana debe estar
    visible y sin nada encima.
    """
    import mss
    from PIL import Image

    l, t, r, b = rect(hwnd)
    with mss.mss() as sct:
        raw = sct.grab({"left": l, "top": t, "width": r - l, "height": b - t})
    img = Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")
    img.save(path)
    # Un frame totalmente negro delata que la captura fallo.
    extremes = img.convert("L").getextrema()
    return img.size, extremes


def main():
    out_dir = sys.argv[1] if len(sys.argv) > 1 else "."
    os.makedirs(out_dir, exist_ok=True)

    print(f"DPI awareness   : {set_dpi_awareness()}")
    wins = java_windows()
    print(f"Ventanas Java   : {len(wins)}\n")

    if not wins:
        print("No hay ninguna ventana Java visible. Abre SAFIX y repite.")
        return

    for i, (hwnd, pid, pname, cls, title) in enumerate(wins, 1):
        l, t, r, b = rect(hwnd)
        print(f"[{i}] hwnd=0x{hwnd:X}  pid={pid}  proc={pname}")
        print(f"    clase  : {cls}")
        print(f"    titulo : {title}")
        print(f"    rect   : ({l},{t})-({r},{b})   {r-l}x{b-t} px")

        kids = children(hwnd)
        print(f"    hijos nativos: {len(kids)}")
        for depth, ch, ccls, ctxt, crect in kids[:15]:
            print(f"      {'  '*depth}- {ccls!r} {ctxt!r} {crect}")
        if len(kids) > 15:
            print(f"      ... y {len(kids)-15} mas")

        png = os.path.join(out_dir, f"probe_{i}_hwnd{hwnd:X}.png")
        try:
            size, extremes = capture(hwnd, png)
            estado = "NEGRA (captura fallida)" if extremes == (0, 0) else "con contenido"
            print(f"    captura: {png}  {size[0]}x{size[1]}  -> {estado}")
        except Exception as e:
            print(f"    captura FALLO: {type(e).__name__}: {e}")
        print()


if __name__ == "__main__":
    main()

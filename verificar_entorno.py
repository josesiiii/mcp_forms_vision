"""Verificacion de entorno de forms-vision.

Comprueba que todo esta listo para trabajar con CUALQUIER forma, no solo con
la ultima que se trabajo. Se ejecuta antes de empezar una sesion de fotos:

    python verificar_entorno.py [forma_de_prueba]

Devuelve codigo 0 si todo lo esencial pasa, 1 si algo esencial falla.
Las comprobaciones marcadas [aviso] no tumban la verificacion.
"""
import glob
import importlib.util
import json
import os
import platform
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)

fallos, avisos = [], []

# Si la raiz del proyecto no viene declarada, server.py la deduce subiendo tres
# niveles — y desde Z:\J\... eso da Z:\, donde no hay ni extracts ni .mcp.json.
# Sin esta distincion el verificador reportaba dos FALLA por una variable de
# entorno ausente, que es peor que no comprobar nada: manda a buscar un
# problema que no existe.
PROYECTO_DECLARADO = bool(os.environ.get("FORMS_VISION_PROYECTO"))


def ok(titulo, detalle=""):
    print(f"  [OK]     {titulo}" + (f"  {detalle}" if detalle else ""))


def falla(titulo, detalle=""):
    print(f"  [FALLA]  {titulo}" + (f"  {detalle}" if detalle else ""))
    fallos.append(titulo)


def aviso(titulo, detalle=""):
    print(f"  [aviso]  {titulo}" + (f"  {detalle}" if detalle else ""))
    avisos.append(titulo)


print("=" * 72)
print("VERIFICACION DE ENTORNO — forms-vision")
print("=" * 72)

# ── 1. Interprete y dependencias ─────────────────────────────────────────────
print("\n1. Interprete y dependencias")
print(f"  python {platform.python_version()} {platform.architecture()[0]}"
      f"  ({sys.executable})")
if sys.platform != "win32":
    falla("plataforma", f"{sys.platform}: esta herramienta es solo Windows")
else:
    ok("plataforma Windows")

for mod, minimo in (("mcp", None), ("mss", None), ("PIL", None)):
    if importlib.util.find_spec(mod) is None:
        falla(f"falta el modulo {mod}", "corre instalar.ps1")
    else:
        m = __import__(mod)
        ok(f"modulo {mod}", getattr(m, "__version__", "instalado"))

# ── 2. El servidor carga y expone sus herramientas ───────────────────────────
print("\n2. Servidor MCP")
ESPERADAS = {
    "forms_plan", "forms_pendientes",                      # planificacion
    "forms_ventanas", "forms_items", "forms_tabs",         # inspeccion
    "forms_abrir", "forms_foco",                           # sesion
    "forms_capturar",                                      # captura
    "forms_click", "forms_escribir", "forms_tecla", "forms_secuencia",
}
try:
    import asyncio

    import server
    import winauto as w
    nombres = {t.name for t in asyncio.run(server.mcp.list_tools())}
    ok(f"server.py carga", f"{len(nombres)} herramientas")
    faltan = ESPERADAS - nombres
    if faltan:
        falla("herramientas ausentes", ", ".join(sorted(faltan)))
    else:
        ok(f"las {len(ESPERADAS)} herramientas esperadas estan presentes")
except Exception as e:
    falla("server.py no carga", f"{type(e).__name__}: {e}")
    print("\nSin servidor no se puede seguir.")
    sys.exit(1)

# ── 3. Configuracion ─────────────────────────────────────────────────────────
print("\n3. Configuracion")
print(f"  PROYECTO : {server.PROYECTO}")
print(f"  SALIDA   : {server.SALIDA}")
print(f"  JNLP     : {server.JNLP}")
print(f"  bloqueadas: {', '.join(sorted(server.TECLAS_BLOQUEADAS)) or '(ninguna)'}")

if PROYECTO_DECLARADO:
    ok("FORMS_VISION_PROYECTO declarada")
else:
    aviso("FORMS_VISION_PROYECTO no esta declarada",
          "la raiz se dedujo; corre con la misma variable que .mcp.json o los "
          "chequeos de extracts no valen")

if os.path.isdir(server.PROYECTO):
    ok("la raiz del proyecto existe")
else:
    falla("la raiz del proyecto no existe",
          "declara FORMS_VISION_PROYECTO en .mcp.json")
if {"F10", "CTRL+S"} <= server.TECLAS_BLOQUEADAS:
    ok("teclas de guardado bloqueadas")
else:
    aviso("las teclas de guardado NO estan todas bloqueadas",
          "riesgo de escribir en la base de datos")
if os.path.exists(server.JNLP):
    ok("el .jnlp existe")
else:
    aviso("no se encuentra el .jnlp", "forms_abrir no podra lanzar SAFIX")

# ── 4. Registro en .mcp.json ─────────────────────────────────────────────────
print("\n4. Registro en .mcp.json")
cfg = os.path.join(server.PROYECTO, ".mcp.json")
if not os.path.exists(cfg):
    aviso("no hay .mcp.json en la raiz del proyecto")
else:
    try:
        d = json.load(open(cfg, encoding="utf-8"))
        s = d.get("mcpServers", {}).get("forms-vision")
        if not s:
            falla(".mcp.json no registra forms-vision")
        else:
            cmd, args = s.get("command", ""), s.get("args", [])
            ok("forms-vision registrado")
            if os.path.exists(cmd):
                ok("el interprete del registro existe")
            else:
                falla("el interprete del registro no existe", cmd)
            destino = args[0] if args else ""
            if os.path.exists(destino):
                mismo = os.path.normcase(os.path.dirname(os.path.abspath(destino))) \
                    == os.path.normcase(AQUI)
                ok("el server.py del registro existe",
                   "(es este mismo)" if mismo else f"OJO: apunta a otra copia -> {destino}")
                if not mismo:
                    aviso("el registro apunta a otra copia de server.py",
                          "puede quedar desincronizada")
            else:
                falla("el server.py del registro no existe", destino)
    except Exception as e:
        falla(".mcp.json no se puede leer", str(e))

# ── 5. Extracts disponibles ──────────────────────────────────────────────────
print("\n5. Extracts de formas")
patron = os.path.join(server.PROYECTO, "06-frontend", "forms", "**",
                      "_extract_*_fmb", "01_bloques.json")
hits = glob.glob(patron, recursive=True)
grave = falla if PROYECTO_DECLARADO else aviso
if hits:
    ok(f"{len(hits)} extracts encontrados en el proyecto")
else:
    grave("no se encontro ningun extract",
          "genera uno con extraer_forma.py"
          if PROYECTO_DECLARADO else
          "esperable: la raiz esta deducida, no declarada")

# ── 6. Prueba de generalidad: planificar OTRA forma ──────────────────────────
forma = sys.argv[1] if len(sys.argv) > 1 else None
if not forma and hits:
    # Elegir un extract cualquiera distinto del mas grande, para probar que
    # el planificador no depende de una forma concreta.
    nombres_forma = sorted(
        os.path.basename(os.path.dirname(h))[len("_extract_"):-len("_fmb")]
        for h in hits)
    forma = nombres_forma[0]

print(f"\n6. Prueba de generalidad — planificar '{forma}'")
if forma:
    try:
        plan = server.forms_plan(forma)
        lineas = plan.splitlines()
        total = next((l.strip() for l in lineas if "TOTAL EN EL ESTADO BASE" in l), "")
        ok("forms_plan responde", f"{len(lineas)} lineas")
        if total:
            ok(total)
        for marca in ("FOTOS REQUERIDAS", "NO TOCAR"):
            if any(l.startswith(marca) for l in lineas):
                ok(f"seccion '{marca}' presente")
            else:
                aviso(f"seccion '{marca}' ausente en el plan de {forma}")
    except Exception as e:
        grave("forms_plan falla", f"{type(e).__name__}: {e}")

# ── 7. Estado en vivo ────────────────────────────────────────────────────────
print("\n7. Sesion de Forms en vivo")
w.set_dpi_awareness()
if w.escritorio_bloqueado():
    aviso("la sesion de Windows esta BLOQUEADA",
          "desbloquea antes de tomar fotos")
else:
    ok("escritorio activo")

ventanas = w.ventanas_java()
if not ventanas:
    aviso("no hay ninguna ventana de Forms abierta",
          "abre SAFIX y la forma antes de empezar")
else:
    if len(ventanas) > 1:
        aviso(f"{len(ventanas)} ventanas de Forms abiertas",
              "conviene dejar solo la forma a fotografiar")
    else:
        ok("una sola ventana de Forms abierta")
    v0 = ventanas[0]
    print(f"     titulo: {v0['titulo']}")
    if v0.get("minimizada"):
        aviso("la ventana esta minimizada", "forms_foco la restaura")
    else:
        h = v0["hwnd"]
        if w.traer_al_frente(h):
            ok("se puede poner en primer plano")
            det = w.detectar_ventana(h)
            if det:
                ok("recuadro detectado",
                   f"x={det['x']} y={det['y']} {det['ancho']}x{det['alto']}")
                ok("colores aprendidos",
                   f"titulo={det['color_titulo']} borde={det['color_borde']}")
                tabs = w.detectar_tabs(h, det)
                if tabs:
                    ok(f"tira de pestanas: {len(tabs)} blancos de click")
                else:
                    aviso("no se detecto tira de pestanas",
                          "puede que la forma no tenga tab canvas")
            else:
                # No es un fallo de deteccion: lo mas probable es que SAFIX
                # este en el menu, sin ninguna forma cargada. El menu no es una
                # ventana de datos y no tiene recuadro que recortar. Decirlo
                # como FALLA manda a depurar la deteccion en vez de abrir la
                # forma.
                aviso("no hay ventana de datos que recortar",
                      f"SAFIX esta en {v0['titulo'][:44]!r}: si es el menu, "
                      "abre la forma a fotografiar y repite")
        else:
            aviso("no se pudo poner en primer plano",
                  "otra aplicacion retiene el foco")

# ── 8. Captura de verdad ─────────────────────────────────────────────────────
# Esta comprobacion existe porque faltaba: una vez se dio el entorno por
# listo con capturar_region roto, y no se noto hasta intentar la primera
# foto real. Verificar la deteccion NO es verificar la captura.
print("\n8. Captura real (no solo deteccion)")
if not ventanas or ventanas[0].get("minimizada") or w.escritorio_bloqueado():
    aviso("no se pudo probar la captura", "sin ventana visible o pantalla bloqueada")
else:
    for etiqueta, kwargs in (("recorte automatico", {"auto": True}),
                             ("canvas completo", {})):
        try:
            r = server.forms_capturar(nombre="_verificacion", **kwargs)
            if "->" in r and ".png" in r:
                ok(f"captura {etiqueta}", r.splitlines()[0].split("->")[-1].strip())
                ruta_png = r.split("->")[-1].split("(")[0].strip()
                try:
                    os.remove(ruta_png)
                except OSError:
                    pass
            elif "No se pudo detectar la ventana activa" in r:
                aviso(f"captura {etiqueta} sin ventana de datos",
                      "abre la forma a fotografiar dentro de SAFIX")
            else:
                falla(f"captura {etiqueta} no produjo PNG", r.splitlines()[0])
        except Exception as e:
            falla(f"captura {etiqueta} lanza excepcion", f"{type(e).__name__}: {e}")

# ── 9. Escritura en disco ────────────────────────────────────────────────────
print("\n9. Escritura en disco")
# Con la raiz deducida, SALIDA apunta fuera del proyecto (p.ej. Z:\06-frontend)
# y esta comprobacion CREABA esa carpeta para luego borrarla, dejando arboles
# vacios en la raiz del disco. Una verificacion no debe ensuciar el disco de
# nadie: si la ruta no existe y la raiz no esta declarada, no se crea.
if not PROYECTO_DECLARADO and not os.path.isdir(server.SALIDA):
    aviso("no se probo la escritura",
          f"no se crea {server.SALIDA}: la raiz esta deducida y crear ahi "
          "dejaria carpetas vacias fuera del proyecto")
else:
    prueba = os.path.join(server.SALIDA, "_verificacion")
    try:
        os.makedirs(prueba, exist_ok=True)
        p = os.path.join(prueba, "escritura.tmp")
        with open(p, "w", encoding="utf-8") as f:
            f.write("ok")
        os.remove(p)
        os.rmdir(prueba)
        ok("la carpeta de salida es escribible", server.SALIDA)
    except Exception as e:
        falla("no se puede escribir en la carpeta de salida", str(e))

# ── Resumen ──────────────────────────────────────────────────────────────────
print("\n" + "=" * 72)
if fallos:
    print(f"RESULTADO: {len(fallos)} FALLO(S) — no esta listo")
    for f_ in fallos:
        print(f"   - {f_}")
else:
    print("RESULTADO: listo para trabajar")
if avisos:
    print(f"\n{len(avisos)} aviso(s) que no impiden trabajar:")
    for a in avisos:
        print(f"   - {a}")
print("=" * 72)
sys.exit(1 if fallos else 0)

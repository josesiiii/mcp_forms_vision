"""Pruebas de lo que se aprendio en el modulo Corporativo (2026-09-04).

Cuatro defectos reales, ninguno de los cuales daba error: todos devolvian una
respuesta que parecia buena.

  * BTN_SCRIPT de etipest es UNA linea: `a1v.Insert_Script;`. El plan lo listo
    como "NO TOCAR: ninguno", porque los verbos peligrosos traen "INSERT " con
    espacio -para no cazar cualquier palabra- y ahi no hay espacio. Un boton que
    delega en una PLL no se puede auditar: el cuerpo no viene en el extract.
  * La flecha de una LOV abre, arma o no hace nada segun lo que diga SU trigger,
    y los TRES casos aparecen dentro de esoporte. Adivinarlo costo aperturas en
    falso; leerlo del .fmb cuesta una lectura.
  * El plan pedia CNV_DOCUMENTOS de evisitas "desde VER2", y VER2 no esta en
    ningun canvas: no hay nada que pulsar.
  * forms_capturar guardo el Visor de fotos de Windows en la carpeta de
    entregables, con nombre de foto de manual, porque pedir el primer plano no
    es obtenerlo y la captura sale del RECTANGULO de pantalla.

    python pruebas_riesgo.py

Codigo 0 si todo pasa, 1 si algo falla.
"""
import inspect
import os
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
os.environ.setdefault("FORMS_VISION_PROYECTO", r"Z:\Projects")

import plan  # noqa: E402

fallos, hechas = [], 0


def comprobar(titulo, condicion, detalle=""):
    global hechas
    hechas += 1
    print(f"  [{'OK' if condicion else 'FALLA'}]  {titulo}"
          + (f"  {detalle}" if detalle else ""))
    if not condicion:
        fallos.append(titulo)


def plano(s):
    return " ".join(s.split())


print("=" * 70)
print("PRUEBAS — riesgo delegado, gesto de LOV y alcance real")
print("=" * 70)

# ── 1. un boton que delega en una libreria no se declara seguro ─────────────
print("\n1. Delegar en una PLL con nombre de escritura es NO TOCAR")

riesgo, motivo = plan._clasificar("a1v.Insert_Script;")
comprobar("el caso literal de etipest se marca NO TOCAR",
          riesgo == "NO TOCAR", f"{riesgo}: {motivo}")
comprobar("y el motivo NOMBRA la llamada, para poder comprobarla",
          "a1v.Insert_Script" in motivo, motivo)
comprobar("y dice por que no se puede auditar",
          "extract" in motivo.lower(), motivo)

for codigo, etiqueta in (("pkg_x.Grabar_Todo;", "Grabar"),
                         ("PU_ALGO.actualizar_saldos(:B.I);", "actualizar"),
                         ("lib.eliminarFoto;", "eliminar")):
    r, m = plan._clasificar(codigo)
    comprobar(f"tambien con el verbo {etiqueta!r}", r == "NO TOCAR", f"{r}: {m}")

# Lo contrario importa igual: un punto no es una llamada.
print("\n2. Un punto en el codigo NO es una llamada a nada")
seguro = ("IF :TESOPORTES.dsp_cliente IS NULL THEN\n"
          "  Set_item_Property('TESOPORTES.dsp_cliente', Lov_Name,"
          " 'LOV_TXTERCEROSCLIENTESNOM');\n  LIST_VALUES;\nEND IF;")
riesgo, motivo = plan._clasificar(seguro)
comprobar("BTN_CLIENTE de esoporte NO se marca peligroso",
          riesgo != "NO TOCAR", f"{riesgo}: {motivo}")
comprobar("una referencia :BLOQUE.ITEM sola tampoco",
          plan._clasificar("GO_ITEM('X'); :TEVISITAS.DSP_VDNI_ASESOR := NULL;")[0]
          != "NO TOCAR")
comprobar("ni un comentario que mencione un update",
          plan._clasificar("-- Abr-2016: pkg.Update_Todo lo hacia antes\n"
                           "SHOW_VIEW('CNV_X');")[0] != "NO TOCAR")

# ── 3. el gesto de la LOV sale del trigger ──────────────────────────────────
print("\n3. Como se abre la LOV se lee del trigger, no se adivina")

r, m = plan._clasificar(seguro)
comprobar("con LIST_VALUES: un click abre", r == "LOV" and "click" in m, m)

solo_arma = ("if :TESOPORTES.DSP_VDNI_ASESOR is null then\n"
             "  Set_item_Property('TESOPORTES.DSP_VDNI_ASESOR', Lov_Name,'');\n"
             "Else\n"
             "  Set_item_Property('TESOPORTES.DSP_VDNI_ASESOR', Lov_Name,"
             "'LOV_TXTERCEROSasesorNOM');\nEnd If;")
r, m = plan._clasificar(solo_arma)
comprobar("sin LIST_VALUES: dice que hay que pulsar Ctrl+L",
          r == "LOV" and "Ctrl+L" in m, m)
comprobar("y que hay que escribir algo en el campo antes",
          "fragmento" in m, m)

# El caso de evisitas: llama LIST_VALUES pero en la rama del campo vacio ha
# puesto Lov_Name a '', asi que no muestra nada. Parece que la flecha no sirve.
vacia = ("IF :TEVISITAS.DSP_VDNI_CLIENTE IS NULL THEN\n"
         "  SET_ITEM_PROPERTY('TEVISITAS.DSP_VDNI_CLIENTE',LOV_NAME,'');\n"
         "  LISt_VALUES;\nEND IF;")
r, m = plan._clasificar(vacia)
comprobar("avisa del caso 'borra la lista y llama LIST_VALUES'",
          r == "LOV" and "VACIO" in m.upper(), m)

comprobar("un boton sin LOV no se clasifica como LOV",
          plan._clasificar("SHOW_VIEW('CNV_X');")[0] != "LOV")
comprobar("y un boton sin trigger no llega aqui (cadena vacia -> revisar)",
          plan._clasificar("")[0] == "revisar")

# ── 4. un disparador que no esta en pantalla no es un camino ────────────────
print("\n4. Un disparador sin canvas no es un camino")


def rutas(bloques, trig_item, canvases, ventanas=None):
    datos = {
        "01_bloques.json": bloques,
        "07_canvases.json": canvases,
        "11_ventanas.json": ventanas or [{"nombre": "WIN_APLICACION",
                                          "canvas_primario": ""}],
        "02_triggers_form.json": [],
        "03_triggers_bloque.json": [],
        "04_triggers_item.json": trig_item,
        "06_program_units.json": [],
    }
    return plan._analizar_rutas(lambda f: datos[f])


# evisitas: VER2 existe como item pero sin canvas; VER si esta en una tab.
bloques = [{"nombre": "B", "items": [
    {"nombre": "VER2", "canvas": "", "tab_page": ""},
    {"nombre": "VER", "canvas": "CONTROLES", "tab_page": "IMAGENES"},
]}]
r = rutas(
    bloques,
    [{"VER2": [{"nombre": "WHEN-BUTTON-PRESSED",
                "codigo": "show_view('CNV_DOCUMENTOS');"}],
      "VER": [{"nombre": "WHEN-BUTTON-PRESSED",
               "codigo": "show_view('CNV_SEGUIMIENTO');"}]}],
    [{"nombre": "CNV_DOCUMENTOS", "tipo": "Stacked", "ventana": "WIN_APLICACION"},
     {"nombre": "CNV_SEGUIMIENTO", "tipo": "Stacked", "ventana": "WIN_APLICACION"},
     {"nombre": "CONTROLES", "tipo": "Content", "ventana": "WIN_APLICACION"}])

comprobar("se detecta que VER2 invoca CNV_DOCUMENTOS",
          bool(r["invocadores"].get("CNV_DOCUMENTOS")))
comprobar("pero CNV_DOCUMENTOS queda SIN CONTROL: VER2 no esta en un canvas",
          r["sin_control"]("CNV_DOCUMENTOS"))
comprobar("y el que si tiene canvas NO se descarta",
          not r["sin_control"]("CNV_SEGUIMIENTO"))
comprobar("un objetivo sin invocadores no se confunde con este caso",
          not r["sin_control"]("NO_LO_INVOCA_NADIE"))

# Un program unit tiene canvas vacio por naturaleza: eso NO es invisible.
r2 = rutas(
    [{"nombre": "B", "items": [{"nombre": "OTRO", "canvas": "CV", "tab_page": ""}]}],
    [], [{"nombre": "CNV_IND", "tipo": "Stacked", "ventana": "WIN_APLICACION"}])
r2["invocadores"]["CNV_IND"] = [{"item": "(program unit)", "canvas": "",
                                 "tab": "", "verbo": "show_view"}]
comprobar("una llamada desde un program unit NO se declara sin control",
          not r2["sin_control"]("CNV_IND"))

# ── 5. la captura comprueba quien esta delante ──────────────────────────────
print("\n5. La captura no se guarda si delante hay otra aplicacion")
import server  # noqa: E402

cap = plano(inspect.getsource(getattr(server.forms_capturar, "fn", None)
                              or getattr(server.forms_capturar, "func", None)
                              or server.forms_capturar))
comprobar("mira la ventana en primer plano", "ventana_al_frente()" in cap)
comprobar("compara por PID, no por hwnd (una LOV es otro hwnd del mismo proceso)",
          "proceso_de_ventana(h)" in cap and "!= pid_forms" in cap)
comprobar("y devuelve FALLO, que detiene el lote",
          "delante de Forms hay otra aplicacion" in cap)
# El orden es lo que de verdad protege: la comprobacion tiene que estar ANTES
# de decidir el archivo, o el PNG con la ventana ajena ya se habria escrito.
comprobar("la comprobacion va antes de resolver la ruta del PNG",
          cap.index("pid_forms") < cap.index("_ruta_salida"),
          f"{cap.index('pid_forms')} vs {cap.index('_ruta_salida')}")
comprobar("da un margen por si el foco iba en camino", "time.sleep(0.4)" in cap)

# ── 6. cerrar un popup no confunde la ventana de datos con un recuadro ──────
print("\n6. Cerrar un recuadro no acusa a la ventana de datos")
cu = plano(inspect.getsource(server._cerrar_uno))
comprobar("refresca la medida de la ventana de datos al identificarla",
          "_ventana_datos[h] = (v[\"ancho\"], v[\"alto\"])" in cu)
comprobar("ya no concluye 'sigue' de una referencia que no coincide",
          "abs(v2[\"ancho\"] - datos[0]) > 8" not in cu)
comprobar("y decide por ancho, el mismo criterio que sin referencia",
          "sigue = v2[\"ancho\"] < ancho_datos" in cu)

# ── 7. click_item reintenta con la ventana al frente ────────────────────────
print("\n7. click_item no se rinde en el primer fallo de deteccion")
import calibra  # noqa: E402

ex = plano(inspect.getsource(calibra._exigir_ventana_datos))
comprobar("trae la ventana al frente antes del segundo intento",
          "traer_al_frente(hwnd)" in ex)
comprobar("y reintenta con mas vueltas", "intentos=4" in ex)
comprobar("si aun asi falla, sigue negandose a pulsar a ciegas",
          "no se pulsa a ciegas" in ex)

print("\n" + "=" * 70)
if fallos:
    print(f"RESULTADO: {len(fallos)} FALLO(S) de {hechas}")
    for f in fallos:
        print(f"   - {f}")
else:
    print(f"RESULTADO: las {hechas} comprobaciones pasan")
print("=" * 70)
sys.exit(1 if fallos else 0)

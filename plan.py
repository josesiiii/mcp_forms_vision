"""Planificacion de las fotos, decidida con el extract del .fmb.

Capa 2. Aqui NO se toca la forma: todo sale de los JSON que produjo
extraer_forma.py. Es lo que permite cerrar la lista de fotos ANTES de abrir
la aplicacion, en vez de ir a la pantalla a ver que hay.
"""

import json
import os
import re

import winauto as w
from nucleo import _extract_de  # noqa: F401



# Verbos que ESCRIBEN o lanzan procesos: un boton que los contenga no se pulsa
# nunca durante una sesion de fotos. Salio de encontrar un COMMIT dentro de
# BTN_NUEVOHIJO en binmueb, a 30 px del boton que si habia que usar.
# Los verbos que hacen peligroso a un boton viven en ajustes.json.
VERBOS_SEGUROS = ("SHOW_VIEW", "SHOW_WINDOW", "GO_BLOCK", "EXECUTE_QUERY",
                  "LIST_VALUES", "HIDE_VIEW", "GO_ITEM")

# Convencion SAFIX: la ventana raiz de toda forma se llama asi. Estaba escrita
# a mano dentro de `encerrada`; ahora tiene un nombre, porque el analisis de
# alcance la necesita en dos sitios y ninguno debe poder quedarse atras.
VENTANA_RAIZ = "WIN_APLICACION"


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

    Devuelve tambien `canvas_raiz`: los canvas que NO NECESITAN invocacion
    porque Forms los muestra al abrir la forma. Sin esa excepcion, la PANTALLA
    PRINCIPAL se clasificaba HUERFANA por no encontrarle un llamador — medido
    en el modulo Portafolio: 6 de las 10 formas, 148 items visibles que el plan
    no habria pedido fotografiar nunca. binmueb no lo destapo porque su
    contenido colgaba de tab pages, que si se reconocen.
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

    # Los dos caminos por los que un canvas es la pantalla de apertura. Hay que
    # aceptar ambos porque el .fmb no es uniforme: fcalifica declara
    # WIN_APLICACION.canvas_primario = CNV_CALIFICACIONES, mientras fvalora deja
    # canvas_primario vacio y su CG$PAGE_1 solo se reconoce por colgar de la
    # ventana raiz. Los apilados quedan FUERA a proposito: esos si necesitan que
    # alguien los muestre.
    canvas_raiz = {(v.get("canvas_primario") or "").upper()
                   for v in ventanas
                   if v["nombre"].upper() == VENTANA_RAIZ
                   and (v.get("canvas_primario") or "")}
    canvas_raiz |= {c["nombre"].upper() for c in canvases
                    if (c.get("ventana") or "").upper() == VENTANA_RAIZ
                    and str(c.get("tipo", "")).lower() != "stacked"}

    # Un canvas se puede mostrar de dos formas, y hasta ahora solo se veia una:
    #
    #   show_view('MI_CANVAS')      -> el objetivo ES el canvas
    #   show_window('WIN_LO_QUE')   -> el objetivo es la VENTANA, y el canvas
    #                                  sale porque cuelga de ella
    #
    # La comprobacion buscaba `invocadores[canvas]`, asi que la segunda forma no
    # contaba. En fclasinv eso mando a HUERFANA la ventana 'Estatus Disponibles'
    # -que si se abre, desde el boton AGREGAR_ESTATUS- y con ella sus 6 items.
    # Ayudo a esconderlo que el canvas se llame ESTAUS_DISPONIBLES, con la
    # errata, y la ventana WIN_ESTATUS_DISPONIBLES: ni siquiera coincidian de
    # nombre.
    for cv, win in ventana_del_canvas.items():
        if win and invocadores.get(win) and not invocadores.get(cv):
            invocadores[cv] = [{**i, "via_ventana": win} for i in invocadores[win]]

    def encerrada(objetivo):
        """True si solo se invoca desde dentro de una ventana secundaria."""
        invs = invocadores.get(objetivo, [])
        if not invs:
            return False
        for i in invs:
            win = ventana_del_canvas.get((i["canvas"] or "").upper(), "")
            if not i["canvas"] or win in ("", VENTANA_RAIZ):
                return False          # hay al menos un invocador accesible
        return True

    return {"invocadores": invocadores, "rotas": rotas,
            "existentes": existentes, "encerrada": encerrada,
            "ventana_del_canvas": ventana_del_canvas,
            "canvas_raiz": canvas_raiz}


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



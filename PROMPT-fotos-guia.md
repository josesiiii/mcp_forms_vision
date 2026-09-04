# Prompt reutilizable — Fotos para la guía de una forma Oracle Forms

> Copiar el bloque de abajo, reemplazar los **cuatro** valores entre `<>` y
> enviarlo. Lo demás no se toca.
>
> El MCP `forms-vision` aporta las **capacidades** (detectar la ventana,
> recortar, leer el extract, clasificar riesgos). Este prompt aporta la
> **política**: qué se fotografía, cómo se llama y qué no se hace. Eso es lo
> único que una herramienta no puede decidir sola, porque **no existe un
> estándar escrito de XENCO sobre capturas para ayudas** — la única regla
> documentada está en el skill `crear-ayudas` §4.6 y es una frase.

---

## CONTEXTO

Vas a tomar las capturas que necesita el manual de usuario de una forma de
Oracle Forms del ERP SAFIX (XENCO S.A.). Las fotos alimentan el skill
`crear-ayudas`, cuyo HTML **se adapta a las fotos que existan**: lista la
carpeta y referencia solo las que estén en disco. No hay huecos fijos ni un
número prefijado, así que la cobertura la define esta política.

Reparto de trabajo, que conviene tener claro:

```
el EXTRACT dice    qué existe, cómo se llega, qué es peligroso, qué no tiene ruta
la PANTALLA dice   cómo se llama cada cosa y si de verdad se dibuja
```

**Los nombres salen de la pantalla, no del `.fmb`.** El extract trae las
pestañas con etiqueta vacía: "Basica" o "Consolidado Niif" solo se leen
mirando la captura.

La sesión de SAFIX ya está abierta con la forma cargada, y es la única forma
abierta.

## DATOS DE ESTA TAREA

```
FORMA             : <nombre_forma>
EXTRACT           : <ruta_extract>
CARPETA IMAGENES  : <ruta_imagenes>
CARPETA PENDIENTES: <ruta_pendientes>
```

## HERRAMIENTAS

| Grupo | Herramienta |
|---|---|
| Planificación | `forms_plan` · `forms_pendientes` |
| Inspección | `forms_ventanas` · `forms_items` · `forms_tabs` |
| Sesión | `forms_abrir` · `forms_foco` |
| Captura | `forms_capturar` |
| Navegación | `forms_click` · `forms_escribir` · `forms_tecla` · `forms_secuencia` |

Dos usos que ahorran la mayor parte del trabajo:

- **`forms_capturar(auto=true)`** detecta y recorta la ventana activa sola, y
  devuelve un diagnóstico del encuadre. No hay que medir nada.
- **`forms_click(..., relativo=true)`** para todo lo que esté **dentro** de la
  ventana de datos. La ventana MDI se mueve cuando la forma se reinicializa, y
  unas coordenadas de canvas tomadas antes de ese salto pulsan en el sitio
  equivocado. Solo usa `relativo=false` para la barra de menú o de estado.

## OBJETIVO

Se fotografía **lo funcional**: lo que el usuario puede abrir, cambiar o
necesita entender para usar la forma. El criterio que decide los casos dudosos
es uno solo:

> **¿esta foto hace el manual más intuitivo, o solo más largo?**

Cobertura completa de lo funcional, entonces — no cobertura exhaustiva de la
pantalla. Una foto que no le enseña nada nuevo al lector **le resta**, porque
lo obliga a compararla con la anterior para descubrir que no cambió nada.

Las fotos deben servirle a alguien que nunca ha visto la forma.

## QUÉ SE FOTOGRAFÍA

- cada **pestaña** y **subpestaña**
- cada **radio botón** y **sub radio botón**
- cada **LOV** (flecha azul) y cada **select list**
- cada **recuadro** que abra cualquier elemento clickeable
- las **alertas informativas**

Si dentro de un recuadro hay elementos clickeables **ambiguos**, dales clic
para ver qué sale; si sale algo, fotografíalo.

## QUÉ SE OMITE

### Una casilla NO lleva foto por existir

Regla dura, y va antes que cualquier otra sobre checkboxes:

| Al marcar la casilla… | Foto |
|---|---|
| aparecen campos, paneles o pestañas — **cambia la forma** | **las dos versiones**, con `marcado` / `desmarcado` en el nombre |
| se abre un desplegable o una ventana | **foto de lo que abre** |
| solo cambia el recuadro | **ninguna** — se ignora |

La casilla ya se ve en la foto de la sección. Una foto de la misma pantalla con
un tick de diferencia no le enseña nada al lector: le hace comparar dos
imágenes para descubrir que no cambió nada.

Se decide con el diff, no a ojo: `CAMBIO ESTRUCTURAL` → las dos; `CAMBIO MENOR`
→ ninguna. Y ocho casillas o más juntas son una **rejilla de selección**
(eligen qué sale en el resultado, no cambian la forma): sin foto propia, ni una.
En `campos` de `iplanosopt` son 59 — por la regla vieja habrían sido 118 fotos
del mismo panel.

### El botón: la ventana que abre, con barra de título

La foto de un botón es **la ventana que abre, encuadrada con su barra de
título** — el título nombra la ventana y le dice al lector dónde está.

**Nunca un recorte del icono.** Los 10 archivos de 0 bytes de `IFACTURAOPT`
eran exactamente eso: recortes de 31×32 a 55×40 px que no llegaron a ser
imagen. `forms_capturar` avisa `RECORTE MINUSCULO` por debajo de 130×70 px o
1.500 bytes.

| Se omite | Por qué |
|---|---|
| La foto del **botón en sí** | solo interesa **lo que abre** |
| **Calendarios** | el selector de fecha es el mismo en todo SAFIX y no aporta |
| Lo que **abre otra forma** | esa forma tiene su propio manual |
| Lo que **no abre nada** | si al pulsar solo cambia el foco, no hay nada que mostrar |
| Alertas de **error** o de **ausencia de datos** | *"No existen valores para la lista"* en un manual del cliente queda fatal. Solo alertas con **información útil** |
| Lo **evidente para el usuario** | campo *Ciudad* → lista de ciudades: se adivina. Si el campo es ambiguo, o lo que abre cuesta relacionar con su nombre, **sí se fotografía** |
| Todo lo que el plan marque **DESCARTADA** | no hay camino en el `.fmb`: no se intenta |
| **Defectos de la forma** | secciones huérfanas o encerradas y referencias rotas (`show_view` a un canvas inexistente). Se omiten y se sigue |

### Los defectos de la forma no son trabajo de esta tarea

Una forma puede invocar canvases que no existen o tener secciones que nadie
alcanza. En `binmueb` son 13 casos. **No se investigan, no se fotografían y no
se abre nada por ellos**: se omiten, se mencionan de pasada en el informe final
y **se continúa con la siguiente forma**.

El manual documenta lo que el usuario **puede** usar. Un canvas que nadie
invoca no le sirve a nadie, y perseguirlo consume la sesión sin producir una
sola foto útil.

**No insistir.** Si un control no abre nada, se anota y se sigue. Nada de
reintentar con otras coordenadas ni buscarle la vuelta: cuesta más de lo que
vale y ensucia el estado de la forma.

Cómo se reconoce que no abrió nada: la captura sale con el **tamaño de la
ventana de datos** en vez de un recuadro nuevo y más pequeño. El diagnóstico
del resultado lo dice sin necesidad de abrir el PNG.

## NOMBRES DE ARCHIVO

El nombre es la **ruta de navegación acumulada**, empezando por la pestaña
(sin el nombre de la forma), en minúscula y con `_`:

```
NN_<pestaña>_<radio/panel>_<prefijo>_<elemento>.png
```

| Prefijo | Para | Se reconoce por `parent_name` |
|---|---|---|
| `radio_btn_` | radio botones | `radio_buttons` no vacío |
| `select_list_` | **desplegable en el sitio** | `POPLIST` |
| `lov_` | **flecha azul que abre una ventana de búsqueda** | `PBUTTON_LIST` o `lov_name` |
| `check_box_` | casillas de verificación | `CHECK_BOX` |
| `btn_` | botón | `PBUTTON_ICONIC` |
| `link_` | etiqueta clickeable | `PC_LINK` |
| `_principal` | vista base de la sección | — |
| `_vista` | lo que abre un botón | — |

> `select_list_` y `lov_` **son controles distintos y llevan prefijo distinto**:
> uno despliega opciones donde está, el otro abre una ventana en la que se
> busca. Para el usuario son dos acciones diferentes. Los manuales anteriores
> llamaban `select_list_` a los dos.

### El tipo del control NO está en `tipo_visual`

Los items de SAFIX **heredan su tipo de una clase de propiedades**, y el `.fmb`
solo trae `ItemType` en el item que se desvía de ella. En `iplanosopt` lo
declara **1 de 301**, así que `tipo_visual` sale `Text Item` para 293 — el grupo
de radios, 64 casillas, 8 desplegables y todos los botones incluidos.

La señal fiable es `parent_name`, que ya viene en `01_bloques.json`:

| `parent_name` | Es | Decisión |
|---|---|---|
| `CHECK_BOX` | casilla | foto |
| `POPLIST` | desplegable | foto |
| `PBUTTON_LIST` | flecha azul | foto de la lista que abre |
| `PBUTTON_ICONIC` | botón de icono | foto |
| `PC_LINK` | etiqueta clickeable | foto de lo que hace |
| `PBUTTON_CALENDAR` | calendario | **se omite, sin mirar la pantalla** |
| `TEXT_READ_ONLY` | **gris por diseño** | sin foto, y no es un fallo |
| `TEXT_NORMAL` | campo editable | sin foto |

Dos reglas que esto vuelve mecánicas: los calendarios se descartan del plan sin
verlos, y **los campos grises quedan identificados antes de abrir la forma** —
un gris de `TEXT_READ_ONLY` es diseño, no un error.

> `parent_name` clasifica el **tipo de control**. No nombra nada: el nombre sale
> siempre de la pantalla (ver abajo).

### El nombre sale de la pantalla, nunca del `label`

El extract trae `label` lleno en muchos items y **tienta a cerrar el plan sin
abrir la forma**. No se hace: los labels del `.fmb` traen errores que solo se
ven cuando la lista se abre en pantalla, y además llegan con acentos mutilados
(`Dise?o` por *Diseño*).

El `label` del plan es una **propuesta**. La etiqueta que manda es la que se
lee en la captura, siempre, incluso cuando el extract parece traerla perfecta.

### Un rango Inicial/Final es una sola foto

Los dos extremos abren la misma lista. El nombre va **sin el sufijo**:
`lov_tipo_lente`, no `lov_tipo_lente_inicial` y `lov_tipo_lente_final`. En
`optica` de `iplanosopt` son 10 flechas y 5 listas reales.

### Una rejilla de casillas es una sola foto

Ocho casillas o más juntas en un panel son una **rejilla de selección**: eligen
qué sale en el resultado (qué columnas lleva el archivo plano), no cambian la
pantalla. `campos` de `iplanosopt` tiene **59**; fotografiarlas en dos estados
serían 118 fotos del mismo panel. Va **una foto del panel**, y el manual dice
«marque las columnas que quiera».

Se confirma con un diff sobre una casilla: si da `CAMBIO ESTRUCTURAL`, entonces
sí son controles de pantalla y se tratan como tales.

### Acentos mutilados en el extract

El extract trae `Dise?o` donde la pantalla dice *Diseño*. Un `?` **en medio** de
la etiqueta es una tilde perdida (uno al final es legítimo: `Inconsistencias?`).
El plan marca esos como `<leer_en_pantalla>`; si se dejan pasar, el archivo sale
`lov_dise_o`.

```
01_principal.png                        si la forma tiene una sola sección
01_basica_principal.png                 si hay varias pestañas
02_basica_select_list_departamento.png
03_basica_radio_btn_avaluos.png
04_basica_radio_btn_avaluos_select_list_avaluador.png
```

### El estado va en la ruta, como un segmento más

La ruta acumulada incluye **todo control que hubo que dejar en cierto estado
para llegar a esa pantalla**, con el estado pegado a su nombre:

| Control | Cómo entra en el nombre |
|---|---|
| checkbox | `check_box_<nombre>_marcado` / `check_box_<nombre>_desmarcado` |
| radio botón | `radio_btn_<nombre>` — estar seleccionado **es** su estado |
| select list | `select_list_<nombre>` cuando el valor elegido cambia la pantalla |

```
01_basica_check_box_es_hijo_desmarcado_principal.png
05_basica_check_box_es_hijo_marcado_radio_btn_impuestos.png
12_ubicacion_check_box_es_hijo_marcado_radio_btn_localizacion_select_list_barrio.png
```

Los nombres salen largos, y así se quedan: el nombre es la **receta para
reproducir la pantalla**. Sin él el manual describiría una vista sin decir cómo
llegar a ella.

### Cuándo hacen falta las dos versiones

Se mueve el control, se captura, y se **compara contra la captura de antes**.
La decisión sale de cuánto cambió, no de mi criterio:

| Lo que muestra la comparación | Qué se hace |
|---|---|
| aparece o desaparece una **pestaña**, un **panel** o un bloque de campos | **las dos fotos** — cambia lo que el usuario puede hacer |
| cambian **uno o dos campos** (se ponen grises, se limpian) | **una foto**, y el detalle va en el texto del manual |
| la imagen es **idéntica** | una foto — y ojo: si esperaba un cambio, **el click no aterrizó** |

Esa última fila es la que salva la pasada: si al mover el control la imagen no
cambia, el control no se movió, y todo lo que viniera después saldría mal
**pareciendo correcto**.

### En los dos estados se duplica TODO, no solo la sección

Cuando una pestaña existe en los dos estados se capturan **las dos**, y también
**todos sus elementos** — cada LOV, cada lista, cada radio — con el estado en el
nombre:

```
024_basica_check_box_es_hijo_desmarcado_lov_departamento.png
098_basica_check_box_es_hijo_marcado_lov_departamento.png
```

Suponer que el estado no toca una pestaña, o que el contenido de una lista no
depende de él, es la clase de suposición que esta política prohíbe. Y el nombre
tiene que decir en qué estado se tomó cada una, porque el lector necesita saber
qué marcar para llegar a esa pantalla.

Consecuencia práctica: **la forma se recorre dos veces completas y el número de
fotos se dobla.** En `binmueb` son 59 en el estado desmarcado y 94 en el
marcado: **153**, más lo que salga de las 7 casillas. Hay que presupuestarlo
desde el plan, no descubrirlo a mitad de la corrida.

### Lo que en un estado está en gris va a pendientes, no a foto

Un campo deshabilitado no abre su lista: `Ctrl+L` no hace nada. Eso **no es un
fallo** y no se insiste. Se anota en el `.txt` con el estado en que se intentó,
y la foto sale en la pasada donde el campo está habilitado.

En `binmueb` desmarcado, de las 16 LOVs de *Basica* solo 3 son alcanzables, y
de los 6 radios solo se dibuja *Auditoria*. Las demás son de la pasada marcada.

### Cómo se cambia de estado: cerrando y reabriendo

Cada estado es una **pasada completa**. Al terminar una:

1. Cerrar la forma **sin guardar** (si pregunta *«¿Desea salvar?»* → **No**).
2. Avisar y reabrirla limpia.
3. Dejar el control en el otro estado y hacer la pasada entera.

Mover el control sin cerrar es más rápido, pero deja el registro marcado como
modificado y la forma empieza a preguntar por guardado en cada cambio de
pestaña. Una pasada larga y desatendida no se hace sobre un registro sucio.

**La numeración se rehace al final**, cuando ya están las dos pasadas: durante
la corrida los números son provisionales.

### LOVs que dependen de otro campo

Los LOVs parametrizados devuelven *"No existen valores"* sobre un registro
vacío. Se **digita un valor válido en el campo padre** para que la lista
muestre contenido real, y se fotografía. Digitar está permitido; **confirmar,
actualizar o guardar, nunca**.

**Reglas que no se negocian:**

- Las etiquetas se **leen de la pantalla**. `forms_plan` propone un nombre a
  partir del prompt del `.fmb` y marca con `?` los que no tiene: esos hay que
  leerlos en la captura, sin excepción.
- Una **LOV se nombra por el campo que la abrió**, no por el título del
  recuadro — si no, no se sabe de dónde vino. Campo *Categoría* →
  `select_list_categoria`, aunque el recuadro se llame "Tipos de Bien".
- Si aparece un recuadro grande con una columna con LOV **sin nombre**, se usa
  el **título del cuadro** o lo más cercano.
- Numeración correlativa en orden de toma. **Nunca solo el número.**

## ORDEN DE CAPTURA — UNA PESTAÑA COMPLETA ANTES DE PASAR A LA SIGUIENTE

Se agota **todo** el contenido de una pestaña —su vista base, sus radios, sus
desplegables, sus listas, sus botones— y solo entonces se pasa a la siguiente.

```
CORRECTO                          MAL
  basica principal                  basica principal
  basica lov_departamento           ubicacion principal
  basica lov_municipio              consolidado principal
  basica radio_btn_impuestos        …
  ubicacion principal               volver a basica por los elementos
  ubicacion select_list_estrato
```

Recorrer las pestañas primero y volver luego por los elementos obliga a
recalibrar cada sección dos veces, deja la numeración en un orden que no es el
del manual, y multiplica los cambios de pestaña — que en SAFIX es justo lo que
dispara el *«¿Desea salvar los cambios?»*.

## PARA QUE ABRAN LAS LISTAS: EL BINÓCULO

Una LOV sobre un registro nuevo vacío **no abre**: el usuario no tiene permiso
de inserción y la forma responde *«Este campo no puede ser modificado…»*, o el
botón pide *«Debe consultar el inmueble»*.

La solución es cargar un registro, y eso lo hace el **binóculo de la barra de
SAFIX** — ejecuta la consulta y trae el primer registro. Está **fuera** de la
ventana de datos, así que se pulsa con `relativo=false`; en este equipo, en el
canvas, está en **(464, 42)**, justo a la derecha del semáforo.

Con un registro cargado las flechas azules se habilitan y `Ctrl+L` abre la
lista de verdad (se reconoce por el tamaño: **466×326**).

| Lo que devuelve `Ctrl+L` | Qué significa |
|---|---|
| ventana de **466×326** | la lista abrió: es la foto |
| recuadro de **~x155** | un mensaje. Léelo: puede ser lista vacía o permisos |
| el tamaño de la ventana de datos | no abrió nada: se anota y se sigue |

Si al pulsar el binóculo pide guardar, la respuesta es **No** — descarta lo que
se haya tocado y continúa. Ojo: eso reinicializa la forma a un registro nuevo,
así que conviene pulsarlo **antes** de tocar cualquier campo.

### Antes de probar un gesto, lee el trigger del botón

Cada flecha azul es un ítem `BTN_*`, y su `WHEN-BUTTON-PRESSED` **dice** cómo se
abre la lista. Se lee una vez, del extract, para toda la forma:

```
04_triggers_item.json -> los WHEN-BUTTON-PRESSED que mencionan
                         Lov_Name o LIST_VALUES
```

| Lo que hace el trigger | Gesto |
|---|---|
| asigna `Lov_Name` **y** llama `LIST_VALUES` | un click en la flecha |
| **solo** asigna `Lov_Name` | escribir un fragmento → flecha → volver al campo → `Ctrl+L` |
| pone `Lov_Name` a `''` y llama `LIST_VALUES` | igual: **con el campo vacío no hay lista** |
| no tiene trigger | decorativo; la LOV va en el ítem → `Ctrl+L` en el campo |

Los cuatro casos conviven en una misma forma (`esoporte`). `forms_plan` ya los
clasifica como `LOV` y escribe el gesto.

**`Ctrl+L` y `F9` no son lo mismo.** Si uno no abre, se prueba el otro antes de
anotar el campo como bloqueado.

**Cuenta las filas en la BD antes.** Sirve para dos cosas: saber si la lista
puede devolver algo, y **verificar** que la que abrió es la que se creía —
`Choices in list: N` de la barra de estado tiene que coincidir con el conteo.

**Una LOV dependiente necesita su padre lleno.** El indicador *List of Values*
de la barra de estado se enciende solo entonces. Primero el padre.

### Aparta la lista antes de la foto

Una LOV se abre **encima del campo que la sirve** y lo tapa junto con su
etiqueta. La foto queda con una lista y sin ninguna pista de a qué campo
corresponde: quien lee el manual no puede situarla. Se aparta con `mover`, y
entonces la etiqueta y la lista caben en la misma imagen:

```
tecla combinacion=CTRL+L
esperar segundos=3
mover x=430 y=10
capturar nombre=07_soporte_telefonico_lov_asesor
```

`x`/`y` es la esquina superior izquierda destino en coordenadas del canvas;
`dx`/`dy` desplaza desde donde esté. El recuadro nunca se queda medio fuera: un
destino imposible se recorta al borde.

**Después de mover, `OK`, `Cancel` y la `X` están en otro sitio.** O se releen
de una captura nueva, o se cierra con `ESC`, que no depende de la posición.

### Cerrar una lista: dos `ESC`, y cuidado con el click siguiente

El primer `ESC` sale de la caja *Find*; el segundo cierra la lista. Y mientras
está abierta **ocupa x 180-652, y 202-528**: un click dirigido a la forma cae
dentro de la lista y no pasa nada visible, así que la foto siguiente sale siendo
la lista anterior con otro nombre. Dos salidas:

- encadenar solo clicks **fuera** de ese rectángulo, o
- usar el paso `cerrar`, que verifica en vez de suponer.

## PROCESO OBLIGATORIO — EN ESTE ORDEN

1. **Planificar con el extract.** `forms_plan(forma)` para la vista general:
   secciones, condicionadas, descartadas con motivo, referencias rotas y
   botones que no se pueden pulsar. Luego `forms_plan(forma, seccion='<TAB>')`
   por cada sección, que enumera LOVs, select lists, checkboxes y botones con
   su nombre propuesto.

2. **Publicar el plan** en el chat, en una tabla corta: cuántas fotos, cuáles
   condicionadas, cuáles descartadas. Sin esto no se empieza.

3. **Leer las etiquetas reales.** Una captura de la tira de pestañas y de la
   sección para leer los nombres visibles. Sin este paso los archivos saldrían
   con nombres internos del `.fmb`, que no sirven.

4. **Ejecutar por lotes.** `forms_secuencia` agrupa clicks, esperas y capturas
   en una sola llamada; `forms_capturar(auto=true)` siempre. No vayas a la
   forma a ver qué elementos hay: eso ya lo dijo el plan. Lo único que se
   explora en vivo es el interior de un recuadro que se abrió, cuando tenga
   elementos ambiguos.

5. **Una pasada completa por estado.** Cuando el plan diga que algo depende de
   una condición, se recorre **todo** el estado actual, se cierra la forma sin
   guardar, se avisa, se reabre limpia y se recorre el otro estado entero. No
   se salta de un estado a otro dentro de una misma pestaña.

6. **Renumerar al final**, con las dos pasadas en disco, para que el orden de
   los archivos sea el orden en que el manual los va a mostrar.

7. **Cerrar con `forms_pendientes`**, que escribe el `.txt` en la carpeta de
   pendientes cruzando el plan con lo que quedó en disco.

## RESTRICCIONES — NO NEGOCIABLES

- **No guardar nunca.** `F10` y `CTRL+S` están bloqueadas en la herramienta; no
  las desbloquees. Si aparece "¿Desea salvar los cambios?", la respuesta es
  siempre **No**.
- **No pulsar los botones que el plan liste en NO TOCAR.** Contienen `COMMIT`,
  `RUN_PRODUCT`, `DELETE` o crean registros. Ojo: en SAFIX hay botones
  declarados como `Text Item` y sin prefijo `BTN_`, así que fíate de la lista
  del plan y no del nombre.
- **No alterar datos existentes.** Digitar en los campos está permitido; lo
  prohibido es **confirmar, actualizar o guardar** con datos digitados. El
  semáforo de la barra importa solo en ese momento: **rojo modifica los datos,
  verde solo consulta**.
- **No inventar.** Si el extract no lo dice y no se ve en pantalla, no se
  afirma: se anota como no verificado.

## VERIFICACIÓN ANTES DE ENTREGAR

- **Ninguna foto duplicada.** Compara los archivos por hash, no a ojo. Una
  captura idéntica a la anterior significa que la ruta **no hizo nada**: hay
  que rehacerla o anotarla, nunca dejarla.
- **Ninguna foto mal rotulada.** Si al capturar apareció un diálogo en vez de
  lo planeado, renómbrala por lo que de verdad muestra.
- **Ninguna foto vacía.** La captura se autoverifica: si el resultado dice
  `NEGRA` o `PLANA`, esa foto no sirve.
- **Numeración correlativa** sin huecos ni repetidos al terminar.

## SI ALGO NO ESTABA EN EL PLAN

Dímelo en **una o dos líneas** y sigue con el resto. No te detengas a
investigar. Lo que no se pueda hacer va al `.txt` de pendientes con su motivo.

## AL FINAL, INFÓRMAME

- Cuántas fotos se tomaron y cuántas pedía el plan.
- Qué quedó pendiente y por qué.
- **Qué omitiste por evidente**, para que yo lo revise.
- Los defectos de la forma, **en una lista corta y sin analizarlos**:
  referencias rotas, controles inalcanzables, mensajes mal redactados. Es
  información de paso, no un entregable — no gastes la sesión en ellos.

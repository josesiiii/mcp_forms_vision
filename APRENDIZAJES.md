# Aprendizajes de las pasadas de fotos

Bitácora de lo que se ha **medido** haciendo fotos de formas reales, con la
consecuencia que tuvo en la herramienta o en el procedimiento. Cada entrada
existe porque algo salió mal o costó de más, no porque pareciera buena idea.

Se lee de arriba abajo: lo de arriba es lo que más caro sale si se olvida.

---

## Lo que más caro sale

### 0 · Un mensaje de error puede ser del lanzamiento, no de la forma

`fplaneac` respondió *«La forma seleccionada no existe»*. Parecía la sentencia
de muerte de la forma. No lo era: la caja de la barra decía `FPLANEACFMO`
porque usé `HOME` antes de `BACKSPACE`, y **retroceder desde el inicio del
campo no borra nada** — el código nuevo se insertó delante del anterior.

> Antes de suspender una forma por *«no existe»*, **verificar qué decía la
> caja**. Con el código limpio, `fplaneac` dio *«Error executing module»*, que
> sí es el error real.

La regla de suspensión sigue en pie; lo que cambia es que un reintento causado
por un fallo propio está justificado y hay que decirlo.

### 1 · Generalizar desde tres intentos

En `fofertas` dije dos veces que un grupo entero de LOVs estaba bloqueado
después de probar tres o cuatro campos. Las dos veces era falso: primero
resultó que las seis de la rejilla abrían, después que *Moneda*, *Tipos
Relaciones*, *Tercero* y *Recurso* también. **No hay patrón por zona de la
pantalla**: *Moneda* es de cabecera y abre; *Recurso* está en un panel y solo
abre por la flecha.

> Se prueba **campo por campo** y se anota el motivo de cada uno. Una lista de
> 22 LOVs se recorre entera o no se recorre.

**En la herramienta**: el aviso de `IDENTICAS` lleva ahora la escalera de
gestos y la frase «no generalices, campo por campo».

#### Y la respuesta: el gesto está escrito en el trigger del botón

Probar gestos a ciegas fue el error; leer el `.fmb` lo resuelve. Cada flecha
azul es un ítem `BTN_*`, y lo que hace su `WHEN-BUTTON-PRESSED` decide el gesto.
Los **tres** casos aparecen dentro de `esoporte`, así que no hay regla por forma:

| lo que hace el trigger | qué abre | gesto |
|---|---|---|
| asigna `Lov_Name` **y** llama `LIST_VALUES` | abre | un click |
| **solo** asigna `Lov_Name` | arma la lista | escribir un fragmento → flecha → volver al campo → `Ctrl+L` |
| pone `Lov_Name` a `''` y **luego** llama `LIST_VALUES` | nada | igual: sin texto en el campo no hay lista |
| sin trigger | nada | decorativo; la LOV, si existe, va en el ítem → `Ctrl+L` |

En `esoporte`: `BTN_CLIENTE` abre con un click; `BTN_ASESOR`, `BTN_REALIZADO` y
`BTN_RESPONSABLE` solo arman; `BTN_MOD_VKPCODIGO` y `BTN_MOD_SIN_VIG` no tienen
trigger. En `evisitas` los cuatro llaman `LIST_VALUES`, pero borran la lista en
la rama del campo vacío. Con esto, *Asesor* abrió al primer intento en las dos.

**En la herramienta**: `forms_plan` clasifica ahora esos botones como `LOV` y
dice el gesto (`pruebas_riesgo`).

### 2 · Mezclar coordenadas de ventana y de canvas

Dos veces. Un pixel leído en una captura de la **ventana** se pulsó como si
fuera del **canvas** — 50 px de más en x, 68 en y — y el click cayó en el campo
de al lado. La segunda vez fue al revés: leí `x=762` en un canvas completo y
pulsé `812`, que era `%Participación` en vez de la flecha.

**En la herramienta**: toda captura dice ahora en qué coordenadas está y qué
sumar. `forms_click(relativo=True)` sigue siendo la vía segura para lo que está
dentro de la ventana de datos.

### 3 · Coordenadas leídas de una captura vieja

Calculé las posiciones de la rejilla de *Calificaciones* con la foto del panel
anterior, cuando la pantalla ya había cambiado de panel. El click se fue a otro
sitio sin dar error.

> Las coordenadas se miden en una captura **de este mismo momento**.

### 4 · `CAMBIO MENOR` no es un negativo

Estuve a punto de dar por fallida una consulta que **sí** había cargado el
registro, porque el diff dijo *CAMBIO MENOR 1,44%*. En una ventana de 959×571
la cabecera es una fracción mínima. Y un desplegable abierto dio **1,18%**.

> **Solo `IDENTICAS` es un negativo fiable.**

**En la herramienta**: el aviso de `CAMBIO MENOR` lo dice, con los números
medidos.

---

## Gestos: qué abre qué

| gesto | cuándo funciona |
|---|---|
| flecha azul | lo más frecuente. La única vía en `fofertas` → *Recurso* |
| click en el campo | mueve el foco; a veces abre |
| `Ctrl+L` | funcionó en `fclasinv`, `femisore`, `fmovimie` |
| **`F9`** | es la tecla que **documenta SAFIX**: *«Presione `<F9>` para consultarlo»* |
| doble click | no abrió ninguna de las probadas |
| etiqueta azul subrayada | **no es una LOV**: abre la **forma del maestro** |

Ese último es un hallazgo con valor propio: `Tiempo:` en `fofertas` abre
`administrar uNidades [Xunidade]`. Son ítems `*_LINK` del `.fmb` y son
funcionalidad documentable, no un fallo.

**`ESC` cierra las LOVs.** Se creía que no —la herramienta
`forms_cerrar_popup` se escribió por eso— y medido el 2026-09-04 las cierra sin
problema. Sale gratis: una tecla, encadenable, sin medir el botón *Cancel*.

**Pero hace falta pulsarlo DOS veces**, y el segundo `ESC` no es opcional: el
primero sale de la caja *Find*, el segundo cierra la lista. Medido dos veces el
mismo día. Y con la lista abierta, **un click dirigido a la forma cae dentro de
la ventana de la LOV** —ocupa x 180-652, y 202-528 en un canvas de 1366×697—:
así se tomó una foto que era la lista anterior con otro nombre. Dos reglas
prácticas:

- después de `ESC`, encadenar solo clicks **fuera** de ese rectángulo;
- o usar el paso `cerrar`, que verifica en vez de suponer.

**`Ctrl+L` y `F9` no son intercambiables.** En la rejilla de `esoporte`, `F9`
dejó el indicador *List of Values* encendido y no mostró nada; `Ctrl+L` abrió la
lista de 139. Se prueban las dos antes de anotar un campo como bloqueado.

**Una flecha que «solo mueve el foco» puede ser una LOV de 0 filas.** En
`esoporte` interpreté que *Módulo* no reaccionaba; lo que pasaba es que
`TKCLIENTESMODULOS` está **vacía en todo el esquema**, y Forms no pinta una
lista sin filas. Es la regla de «vacía o rota» aplicada al gesto: antes de
llamarlo defecto, contar filas.

**Una LOV dependiente no abre hasta que su padre tiene valor.** *Módulo* filtra
por el cliente; con el registro vacío no podía devolver nada. El indicador
*List of Values* de la barra de estado se encendió solo al llenar *Cliente*.
Orden: primero el padre.

---

## Antes de tocar la forma

**Contar filas en la BD.** Es el paso que más pasadas ahorra. Con `fmovimie` se
comprobó primero (`TFMOVIMIENTOS` y sus dos detalles a 0 filas) y se hizo una
sola pasada; con `femisore` no, y se gastaron varios intentos de consulta que
nunca podían devolver nada.

**Agrupar las LOVs por su consulta.** En `fofertas`, 22 LOVs declaradas son
**15 consultas distintas**, y cuatro de ellas ya estaban fotografiadas en otras
formas con la consulta byte a byte idéntica. Una lectura del `.fmb` en vez de
22 aperturas.

El caso extremo es `evisitas`: **24 record groups son ~11 listas**, y **ocho de
ellos son la misma** consulta de terceros `'EMP'` con distinto filtro
(`RG_ASESORES`, `RG_EMPLE_TOMA`, `RG_EMPLE_TOMA_NOMBRE/CODIGO`,
`RG_EMPLE_EJECUTA_NOMBRE/CODIGO`, `RG_ASESORES_NOMBRE/CODIGO`). Una foto para
los ocho. Es el paso que más aperturas ahorra de todos los medidos: 13.

El patrón se repite: SAFIX declara **dos** grupos por campo, uno por *nombre*
(`... LIKE Upper(:campo)||'%'`) y otro por *identificación* (`= :campo`), y el
botón elige según lo que se haya escrito. Son la misma lista.

**El conteo también VERIFICA la foto.** La barra de estado dice `Choices in
list: N`. Si ese N coincide con el conteo que se sacó de la BD, la lista abierta
es la que se creía; si no, se abrió otra. En Corporativo cuadró cinco veces
seguidas —139=139, 10.416=10.416, 9=9, 57=57, 40=40, 30=30, 10=10— y por eso no
hizo falta abrir ningún PNG para comprobar el rótulo.

**Distinguir «vacía» de «rota».** Una lista sin valores puede ser falta de
datos o una consulta mal escrita. En `fcalifica` el record group filtra por el
propio valor del campo que la lista sirve para elegir:

```sql
WHERE VKPCODIGO = :TFTIPOSCALIFICACIONES.VKPCODIGO
```

Vacío → 0 filas; con el código escrito → esa única fila. Como selector no sirve
nunca, y la tabla tiene 3 filas. Eso es un defecto para Redmine. En cambio
`TGCOMISIONES` y `TTOPERACIONESEFECTIVAS` tienen 0 filas de verdad: la consulta
está bien y no hay nada que mostrar.

---

## Dos pasadas, y en qué orden

Con un registro **consultado**, los campos clave se protegen y su LOV no abre.
Con un registro **nuevo**, abren pero la pantalla sale vacía.

```
pasada A  registro NUEVO       -> LOVs y desplegables
pasada B  registro CONSULTADO  -> secciones y paneles con datos
```

El número de la foto es el orden del manual, no el orden en que se tomó.

---

## Trampas de la captura

**`auto=True` falla con un modal delante**: en `fofertas` recortó **una columna
de la rejilla** en vez de la ventana. Con un modal encima se pasan coordenadas
explícitas.

**La posición de una LOV depende del campo que la abre.** Un recorte fijo de la
zona cortó una foto por la mitad. Para LOVs, canvas completo.

**Comparar una LOV contra otra LOV engaña**: dos listas completamente distintas
dieron 0,99% y 2,74% porque ocupan la misma zona. Se compara contra el estado
**cerrado**.

**Los mensajes de error salen duplicados**: hay que pulsar *Aceptar* dos veces.
Mientras quede uno, la caja de lanzamiento no recibe teclado y parece
bloqueada.

**La foto puede no ser de Forms.** El 2026-09-04 una captura salió del **Visor
de fotos de Windows** y se guardó en la carpeta de entregables, con nombre de
foto de manual. `traer_al_frente` había devuelto `True`: Windows puede negar el
cambio de foco, y la captura sale del **rectángulo de pantalla**, o sea de lo
que haya encima.

**En la herramienta**: `forms_capturar` comprueba ahora **quién** quedó delante
—por pid, para que una LOV o un modal de Forms sigan valiendo— y falla antes de
escribir el archivo (`pruebas_riesgo`).

---

## Lo que la herramienta ya hace sola

Cosas que antes eran disciplina de quien capturaba y hoy son código, con su
prueba:

| | |
|---|---|
| foto repetida | se detecta al guardar y **no** se guarda copia (`pruebas_gasto`) |
| icono de un botón | `escala=5` en la misma llamada, sin PIL por fuera |
| pantalla de apertura | ya no se clasifica HUERFANA (`pruebas_alcance`) |
| canvas tras `show_window` | cuenta como alcanzable (`pruebas_alcance`) |
| rejilla y `off_y` | se puntúan **alturas** distintas, no encajes (`pruebas_calibra`) |
| `texto=01` | llega como texto, no como `int` 1 (`pruebas_parser`) |
| ambiente | solo se actúa en los autorizados (`pruebas_ambiente`) |
| gesto de una LOV | se dice leyendo el trigger del botón (`pruebas_riesgo`) |
| botón que delega en una PLL | cuenta como **NO TOCAR**, no como seguro (`pruebas_riesgo`) |
| sección sin control en pantalla | se descarta `SIN CONTROL` (`pruebas_riesgo`) |
| otra aplicación delante | la captura falla en vez de guardarla (`pruebas_riesgo`) |
| ventana de datos | ya no se confunde con un recuadro por una medida rancia (`pruebas_riesgo`) |

**193 comprobaciones** corren sin abrir SAFIX.

> Se corren con el Python del servidor, no con el del sistema:
> `%LOCALAPPDATA%\forms-vision-venv\Scripts\python.exe`. Con el otro fallan
> todas por `ModuleNotFoundError: mcp`, que parece un desastre y no lo es.

---

## Listas que se parecen y no son la misma

Comparar por **título** o por **cuánto ocupa** la lista lleva a fusionar cosas
distintas. Se compara por la **consulta** y por el **conteo de filas**:

| lista | forma | consulta | filas |
|---|---|---|---|
| Plan de Cuentas | `fmovimie` | `TCPLANCUENTAS` sin filtro | 2.768 |
| Plan de Cuentas | `fvalora` | `+ FRESMOVIMIENTO='S' AND VRXESTADO='A'` | **2.767** |
| Terceros | `femisore` | `VXTERCEROS` | 6.987 |
| Terceros | `fvalora` | `VXTERCEROSTODOS` | **7.014** |
| Clientes | `esoporte` | `txTerceros+tkClientes+poblaciones` | 1.812 |
| Clientes | `evisitas` | `VKCLIENTES` | **2.568** |
| Empleados | `esoporte` | `txTerceros+txTercerosTipos 'EMP'` | 83 |
| Empleados | `esoporte` *Realizado por* | `+ thTercerosPerEmpleados` | **93** |

Una fila de diferencia y 27 de diferencia: son cuatro listas, no dos. En
cambio dentro de `fmovimie`, `CGFK$CUENTAS` y `LOV_TCPLANCUENTAS` **sí** dan
exactamente la misma —2.768— y ahí sobra una foto.

> El conteo se saca de la BD **antes** de abrir nada, y decide si la foto hace
> falta.

## Pendiente de mejorar

- **Renumerar es manual.** Al descartar fotos queda un hueco y hay que
  renombrar a mano. Cabe una herramienta que renumere una carpeta conservando
  el orden.
- **La calibración de un canvas apilado no funciona**: tiene su propio
  desplazamiento y `forms_calibrar` da 0 encajes. Hoy se pulsa por pixel leído
  de la pantalla.
- **El detector de ventana activa elige por área**, y una ventana secundaria
  más grande le gana a la de datos. Pasó al empezar con dos formas abiertas.
- **`_ventana_datos` se guarda por `hwnd`**, y el `hwnd` del frame de SAFIX es
  el mismo para todas las formas: al cambiar de forma la referencia queda
  rancia. Ya se refresca al identificar la ventana de datos, pero la clave
  correcta sería `(hwnd, forma)`.
- **`Ctrl+Shift+→` no selecciona** cuando las teclas se inyectan. Se vacía la
  caja con **`END`** + `BACKSPACE` ×30 (ver la entrada 0: con `HOME` no borra
  nada).
- **`canvas_de` puede devolver una medida transitoria.** Tras un lanzamiento
  fallido dio 681×688 en vez de 1366×697, y `forms_click` rechazó un click
  legítimo por salirse de ese canvas falso. Falló **del lado seguro** —se negó
  en vez de pulsar a ciegas— pero le falta el reintento que sí tiene
  `detectar_ventana_reintentando` por exactamente el mismo motivo.

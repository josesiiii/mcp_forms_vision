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

**155 comprobaciones** corren sin abrir SAFIX.

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
- **`Ctrl+Shift+→` no selecciona** cuando las teclas se inyectan. Se vacía la
  caja con **`END`** + `BACKSPACE` ×30 (ver la entrada 0: con `HOME` no borra
  nada).
- **`canvas_de` puede devolver una medida transitoria.** Tras un lanzamiento
  fallido dio 681×688 en vez de 1366×697, y `forms_click` rechazó un click
  legítimo por salirse de ese canvas falso. Falló **del lado seguro** —se negó
  en vez de pulsar a ciegas— pero le falta el reintento que sí tiene
  `detectar_ventana_reintentando` por exactamente el mismo motivo.

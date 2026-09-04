# forms-vision — MCP para ver y manejar Oracle Forms

Permite a Claude abrir SAFIX, **fotografiar la pantalla y los elementos** de una
forma, y navegar por ella (clicks, texto, teclas).

> ### ⚠ Maneja una sesión REAL del ERP
>
> Esta herramienta **inyecta entrada real**: mueve el puntero físico y el foco
> del teclado de verdad, porque AWT ignora los mensajes sintéticos. Un click
> mal calculado pulsa lo que haya en ese píxel.
>
> **Úsala contra `SAFIXDEMOS`, nunca contra producción.**
>
> Guardas que trae puestas: `F10` y `CTRL+S` bloqueadas, se niega a pulsar
> botones cuyo `WHEN-BUTTON-PRESSED` contiene `COMMIT`/`RUN_PRODUCT`/`DELETE`,
> no inyecta nada si la ventana no logra ponerse en primer plano, y ante
> *«¿Desea salvar los cambios?»* la respuesta correcta es siempre **No**.
> Ninguna sustituye a trabajar en un ambiente de pruebas.

## Por qué está hecho así

Verificado en este equipo el **2026-09-01** con `probe_forms.py`:

| Hecho comprobado | Consecuencia de diseño |
|---|---|
| El runtime es Java Web Start (`jp2launcher.exe`), no un navegador | Playwright y las herramientas de navegador **no sirven** |
| La ventana es un `SunAwtFrame` con **un solo hijo**, un `SunAwtCanvas` de 1366×720 | No hay árbol de items para Windows: la posición de cada item hay que **deducirla** |
| `PrintWindow` sobre ventanas Java suele devolver negro | Se captura de **pantalla**; la ventana debe estar al frente y despejada |
| AWT ignora los mensajes sintéticos | La entrada se inyecta con **SendInput** (entrada real: el puntero se mueve de verdad) |
| Java Access Bridge está **deshabilitado** y solo existe `WindowsAccessBridge-32.dll` (JRE 8u501 de 32 bits), mientras el Python del equipo es de 64 bits | La ruta "árbol accesible" está **descartada por ahora** (ver *Mejora pendiente*) |

Por eso la ubicación de los items **no se descubre, se deduce**: sale de los
`XPosition/YPosition/Width/Height` que `06-frontend/forms/extraer_forma.py` ya
extrae del `.fmb`, traducidos a píxeles con una calibración medida una vez por
forma. No se asume ninguna conversión de unidades — se mide, porque
`coordenadas_modulo` viene `None` en los extracts existentes.

## Flujo obligatorio para una sesión de fotos

> Añadido 2026-09-02, después de medir dónde se iba el tiempo en la primera
> sesión real. **Las decisiones se toman con el extract, no frente a la forma.**

```
[1] forms_plan(forma)      -> qué fotos hacen falta, cómo llegar a cada una,
                              qué NO necesita foto y por qué, y qué botones
                              NO se pueden pulsar porque escriben en la BD
[2] revisar el plan         -> cerrar la lista ANTES de tocar la forma
[3] forms_secuencia(...)    -> ejecutar por lotes: click, tecla, capturar
[4] lo que no salga         -> anotarlo y seguir; nada de explorar la forma
```

Prohibido en el paso 3: ir a la forma "a ver qué hay". Si aparece algo que el
extract no anunció, se anota y se continúa con el resto.

### Por qué es más rápido que la primera versión

| Costo medido en la sesión del 2026-09-01 | Cómo se eliminó |
|---|---|
| Medir el recuadro con un script de PIL externo antes de **cada** foto | `forms_capturar(auto=True)` lo detecta solo |
| Abrir cada PNG para comprobar que servía | la captura devuelve diagnóstico (negra / plana / encuadre OK) |
| Un viaje ida y vuelta por cada click, espera y captura | `forms_secuencia` ejecuta la tanda en una llamada |
| Leer triggers a mano para saber qué botón era seguro | `forms_plan` clasifica el riesgo de los 54 botones |

## Las capas

```
winauto.py    807   Win32, pixeles, ajustes            no sabe nada de MCP
nucleo.py     104   configuracion, extract, contrato   depende solo de winauto
plan.py       366   planificacion desde el .fmb        no toca la forma
calibra.py    168   calibracion .fmb -> pixel
server.py    1075   las 15 herramientas MCP
```

Cada capa depende solo de las de abajo. `nucleo.py` existe justamente para
romper el círculo: si la configuración y el contrato vivieran en `server.py`,
`plan.py` tendría que importar `server` y `server` importar `plan`.

El servidor MCP se declara **solo** en `server.py`, así que `plan` y `calibra`
se pueden importar desde una prueba sin levantar nada de MCP — que es lo que
permite que 51 de las comprobaciones corran sin sesión de Forms.

### El contrato de éxito y fallo

Las herramientas devuelven texto, porque quien las lee es un modelo. El
problema era que devolvían texto **también al fallar**, así que un lote tenía
que adivinar por subcadenas si un paso había salido bien. Eso costó tres
defectos en un solo día, y en dos de ellos se guardaron fotos con el nombre de
una lista que nunca se abrió.

Ahora cada fallo va prefijado con `[FALLO]` y cada aviso que invalida lo que
venga detrás con `[AVISO]`. La lista de `marcas_fallo` queda como red de
seguridad y, cuando salta, lo dice: *«…(por marcador de texto, sin token)»*.

`pruebas_contrato.py` **audita el código fuente de las cuatro capas** y falla
si alguien añade un retorno de fallo sin token. Ya cazó cuatro que se me
escaparon en la conversión.

## Herramientas

**15 herramientas**, agrupadas por lo que hacen:

| Grupo | Herramienta | Qué hace |
|---|---|---|
| Planificación | `forms_plan` | **Empezar aquí.** Secciones, rutas, riesgos y descartes. Con `seccion=` da el detalle: LOVs, select lists, checkboxes y botones con nombre propuesto |
| | `forms_pendientes` | **Terminar aquí.** Escribe el `.txt` cruzando plan y disco |
| Inspección | `forms_ventanas` | Estado de la sesión: canvas, ventana activa, tira de pestañas, bloqueo |
| | `forms_items` | Inventario de items con su etiqueta de pantalla y su LOV |
| | `forms_tabs` | Blancos de click de la tira de pestañas |
| Sesión | `forms_abrir` · `forms_foco` | Lanzar SAFIX y traer la ventana al frente |
| Captura | `forms_capturar` | PNG con `auto=True`; se autoverifica el encuadre. Con `comparar_con=` mide cuánto cambió la pantalla |
| Navegación | `forms_click` · `forms_escribir` · `forms_tecla` | Entrada real; `relativo=True` para lo que esté dentro de la ventana |
| | `forms_calibrar` · `forms_click_item` | Pulsar un control **por su nombre del `.fmb`**, incluido `GRUPO.RADIO` |
| | `forms_cerrar_popup` | Cierra el recuadro de encima identificándolo por su **tamaño** |
| | `forms_secuencia` | Varios pasos en una sola llamada |

> `forms_esperar` existe solo como paso de `forms_secuencia`, que es donde se
> usa. `forms_ventana_activa` desapareció: su información está en
> `forms_ventanas`.

Las capturas se guardan en `06-frontend/forms/_capturas/<fecha>/` y las
herramientas devuelven la **ruta**, no la imagen: una imagen en línea cuesta
mucho contexto y casi siempre basta con abrir la que interesa.

## Los dos fallos que no daban ninguna señal

Lo más valioso de la herramienta no es lo que hace, es lo que **se niega a
hacer a ciegas**. Dos fallos producían fotos impecables con el nombre
equivocado, y ninguno de los dos daba error:

| Fallo | Cómo se caza ahora |
|---|---|
| Un click **no mueve el foco** → el `Ctrl+L` siguiente abre la lista de otro campo. Pedí *Centro Costos* y salió *Barrios* | `forms_click_item` mira el **resalte amarillo** después de pulsar y avisa si no cubre el punto pulsado. Siempre, no a petición |
| Un control **no se movió** → la pasada entera se hace creyendo que el estado cambió | `forms_capturar(comparar_con=...)`. Si sale `IDENTICAS` cuando se esperaba un cambio, el control no se movió |

`forms_secuencia` **detiene el lote** ante `[FALLO]` o `[AVISO]`: seguir
después de uno de estos solo produce fotos mal rotuladas.

El mismo mecanismo decide si un control necesita **dos fotos**: se mide el área
que cambió. `CAMBIO ESTRUCTURAL` (aparece una pestaña o un panel) → las dos
versiones; `CAMBIO MENOR` (uno o dos campos) → una sola. El umbral está en
**píxeles, no en porcentaje**: el mismo cambio es 0,26% de la ventana de datos
y 1,6% de un recuadro de LOV, y con un umbral porcentual la misma diferencia
se clasificaba distinto según dónde ocurriera.

## Bitácora

Cada captura y cada `click_item` dejan una línea en
`_capturas/_bitacora/<fecha>.log` con la hora, lo que se pidió y los avisos.
Una corrida de ~90 fotos es larga y desatendida: sin registro no hay forma de
saber después qué salió y qué quedó a medias. Se cambia con
`FORMS_VISION_BITACORA`.

## Ajustes — lo que se afina sin reiniciar

Nueve valores viven en `ajustes.json` y se releen **en cada llamada**, con
caché por fecha de modificación. Son justo los que se afinan probando:

| Ajuste | Qué decide |
|---|---|
| `marcas_fallo` | qué textos detienen un lote de `forms_secuencia` |
| `menor_pixeles` · `menor_tope` | cuándo un cambio en pantalla es MENOR y no ESTRUCTURAL |
| `clase_por_parent` | el mapa `parent_name` → clase de control |
| `prefijo` | el prefijo del nombre de archivo por clase |
| `sufijos_rango` | qué sufijos marcan un extremo de rango |
| `rejilla_minima` | desde cuántas casillas un panel es una rejilla de selección |
| `encajes_fiables` | cuántos encajes hacen fiable una calibración propia |
| `verbos_peligrosos` | qué hace que un botón sea NO TOCAR |

El archivo **aguanta que se edite mal**: si falta, no es JSON válido, trae una
clave desconocida o un tipo equivocado, se usan los valores de respaldo que
lleva `winauto.py` dentro y se avisa del problema. Un JSON roto a mitad de una
corrida de 90 fotos sería peor que el reinicio que evita.

## Pruebas

```bash
python pruebas_deteccion.py      # 19 comprobaciones, sin sesión de Forms
python pruebas_ajustes.py        # 16 comprobaciones, sin sesión de Forms
python pruebas_contrato.py       # 16 comprobaciones, sin sesión de Forms
python verificar_entorno.py      # entorno + captura real
```

**51 comprobaciones corren sin abrir SAFIX.** Dos de ellas no comprueban un
resultado sino el **código**: `pruebas_contrato.py` audita las cuatro capas
buscando retornos de fallo sin token, y `pruebas_ajustes.py` compara las claves
contra `AJUSTES_DEFECTO` en vez de contra un número fijo — porque una prueba
que hay que editar cada vez que el código crece acaba fallando por estar vieja,
no por un defecto.

`pruebas_deteccion.py` sintetiza las imágenes que necesita, así que corre en
cualquier momento. Existe porque lo que verifica está puesto para cazar fallos
silenciosos, y una verificación que se creyera a sí misma no serviría de nada
— de hecho la primera vez tumbó el umbral porcentual.

> `verificar_entorno.py` necesita las **mismas variables** que `.mcp.json`. Sin
> `FORMS_VISION_PROYECTO` la raíz se deduce y los chequeos de extracts no
> valen: eso sale como aviso, no como fallo, para no mandar a buscar un
> problema que no existe.

## Flujo típico

```
forms_ventanas                                   # ver qué hay abierto
forms_capturar  nombre="estado"                  # foto del canvas
forms_items     forma="ipedidosopt" canvas="LOTES"
forms_calibrar  forma="ipedidosopt" \
                item_a="FECHA_VENCIMIENTO" px_a=... py_a=... \
                item_b="..."            px_b=... py_b=...
forms_capturar_item forma="ipedidosopt" item="FECHA_VENCIMIENTO"
```

La calibración se guarda en `calibraciones.json` y **deja de valer si mueves o
redimensionas la ventana de Forms**, o si cambias de resolución.

Si una forma no tiene extract todavía:

```bash
python 06-frontend/forms/extraer_forma.py <ruta>/<forma>.xml
```

## Guardas

- Ninguna tecla ni click se inyecta si la ventana de Forms no logra ponerse en
  primer plano. Evita escribir en la aplicación equivocada.
- `F10` y `CTRL+S` están **bloqueadas** por defecto: son candidatas a confirmar
  o guardar contra la base de datos. Es una precaución de esta herramienta, no
  una regla de Forms — se cambia con `FORMS_VISION_TECLAS_BLOQUEADAS` en
  `.mcp.json`.
- La sesión que se maneja es una sesión **real**. Úsala contra `SAFIXDEMOS`.

### El semáforo de la barra — qué significa de verdad

Digitar en los campos **no** depende del semáforo: se puede escribir en
cualquier momento y en cualquier parte. El color importa en el momento de
**guardar, actualizar o cambiar de página** habiendo digitado algo:

| Semáforo | Qué pasa al guardar |
|---|---|
| 🔴 rojo | modo edición/creación: **modifica los datos** |
| 🟢 verde | modo consulta: lo digitado es solo criterio de búsqueda |

De ahí que la guarda de esta herramienta esté en las teclas de guardado, no en
el teclear. Antes de pulsar cualquier cosa que confirme, comprobar el color.

Ojo con un patrón frecuente en las formas SAFIX: **navegar entre pestañas o
mover un radio puede marcar el registro como modificado**, y entonces al entrar
a modo consulta la forma pregunta si guardar aunque nadie haya escrito. La
respuesta segura es siempre *No*.

## Nada está atado a una forma concreta

Todo lo que se descubrió trabajando una forma quedó como mecanismo general:

| Se descubrió en una forma | Cómo quedó |
|---|---|
| posición y tamaño de la ventana | se **detecta** en cada captura; da igual si la forma es más grande o está corrida |
| los colores del tema (título, borde) | se **aprenden** de la imagen; no hay RGB fijo en el código |
| dónde está la tira de pestañas | se busca la banda con más bloques; no hay desplazamiento fijo |
| qué botones son peligrosos | se leen los `WHEN-BUTTON-PRESSED` del extract de esa forma |
| qué pestañas son condicionales | se leen los `SET_TAB_PAGE_PROPERTY` y su `IF` |
| qué no tiene camino | se calcula quién invoca a quién en ese extract |
| rutas de fotos y de pendientes | son parámetros, no constantes |

Para trabajar otra forma no hay que tocar código: basta su extract y sus rutas.

## Instalación

```powershell
git clone <repo> && cd MCP-Capturas-Oracle-Forms
powershell -ExecutionPolicy Bypass -File instalar.ps1 -Proyecto Z:\Projects
```

El instalador crea el venv, **copia el código a `%LOCALAPPDATA%\forms-vision`**
e imprime el JSON exacto para el panel *Servidores MCP locales* de la app.

### Por qué el código se copia y no se ejecuta desde el repo

| Qué | Dónde | Por qué |
|---|---|---|
| el código que ejecuta | `%LOCALAPPDATA%\forms-vision\` | el servidor arranca en **cada llamada**; si el repo está en red, eso cruza la red constantemente |
| el intérprete | `%LOCALAPPDATA%\forms-vision-venv\` | un venv en red es tan lento que el `pip install` no termina |
| **los datos** — extracts, fotos, pendientes | donde apunte `FORMS_VISION_PROYECTO` | ahí viven y ahí los espera el equipo |

En el equipo donde se desarrolló, `Z:` es un recurso de red compartido, de ahí
la separación. En una máquina con el repo en disco local da igual, pero el
instalador hace lo mismo: una sola forma de instalar, sin casos especiales.

### Lo que NO se versiona, y por qué

- **`calibraciones.json`** — la conversión unidades del `.fmb` → píxeles,
  medida contra la ventana viva. Depende de la resolución, del tamaño de la
  ventana y hasta de la corrida: la misma sección dio `escala 1.335 / off 6` en
  una y `1.33 / off 7` en otra. Versionarlo haría que otra máquina arrancara
  con una geometría ajena, y **los clicks caerían desplazados sin dar ningún
  error**. Se regenera con `forms_calibrar`.
- **el venv y los `__pycache__`** — binarios de una máquina y una versión de
  Python concretas.
- **`.mcp.json` y `claude_desktop_config.json`** — configuración de máquina, y
  el segundo puede llevar credenciales en texto plano.

> Tras editar `server.py` o `winauto.py` hay que **reinstalar y reiniciar la
> app**: el proceso del MCP ya tiene el módulo en memoria y Python no recarga
> nada por su cuenta. Se comprueba comparando la fecha del archivo con la hora
> de arranque del proceso — si el proceso es anterior, corre código viejo.
> Los **9 ajustes de `ajustes.json` son la excepción**: esos se releen en
> caliente (ver *Ajustes*).

## Configuración

Registrado en `Z:\Projects\.mcp.json` (ámbito de **proyecto**: carga cuando la
sesión está abierta en `Z:\Projects`). Variables de entorno:

| Variable | Por defecto |
|---|---|
| `FORMS_VISION_PROYECTO` | tres niveles arriba del servidor — **hay que declararla** |
| `FORMS_VISION_JNLP` | `C:\Scripdominio\SAFIXV4.jnlp` |
| `FORMS_VISION_SALIDA` | `Z:\Projects\06-frontend\forms\_capturas` |
| `FORMS_VISION_BITACORA` | `<SALIDA>\_bitacora` |
| `FORMS_VISION_TECLAS_BLOQUEADAS` | `F10,CTRL+S` |

`FORMS_VISION_PROYECTO` es obligatoria con la copia local: subir tres niveles
desde `%LOCALAPPDATA%\forms-vision` da una ruta absurda. `verificar_entorno.py`
lo avisa en vez de reportar fallos falsos por extracts que no encuentra.

Dependencias: `mcp`, `mss`, `pillow`. Sin `pywin32`: la capa Win32 es `ctypes`
puro en `winauto.py`.

## Mejora pendiente — Java Access Bridge

Daría el árbol de componentes en vivo (rol, nombre y rectángulo por item), sin
calibrar y sin depender del `.fmb`. Requiere dos cosas que hoy no están:

1. Habilitar el puente: `jabswitch -enable` y reiniciar la sesión de Forms.
2. Resolver el choque de arquitectura — instalar un Python de 32 bits, o un
   JRE 8 de 64 bits para que aparezca `WindowsAccessBridge-64.dll`.

Ambas son instalaciones en la máquina, así que no se hicieron sin permiso.

## Diagnóstico

```bash
python probe_forms.py <carpeta_salida>
```

Enumera las ventanas Java, sus hijos nativos y captura cada una. No envía
teclas ni clicks: es seguro contra una sesión en uso.

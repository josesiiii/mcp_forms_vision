# Seguridad de forms-vision — controles implementados y sus límites

Este documento existe para que el responsable del SGSI de XENCO pueda
contrastar la herramienta contra la Declaración de Aplicabilidad. **No es un
certificado de conformidad ni pretende serlo.**

## Lo primero, y sin rodeos

**Una herramienta no puede «cumplir ISO 27001».** ISO/IEC 27001 certifica un
*sistema de gestión de seguridad de la información* de una organización: sus
cláusulas 4–10 son gobierno —política, análisis de riesgos, objetivos,
competencia, auditoría interna, revisión por la dirección, mejora— y el
Anexo A son 93 controles cuya mayoría es organizativa: personal, proveedores,
seguridad física, continuidad, cumplimiento legal.

Un archivo de Python no puede satisfacer nada de eso. Lo que sí puede hacer un
componente de software es **implementar los controles técnicos que le
correspondan** dentro de un SGSI que ya exista, y **dejar por escrito los que
quedan fuera de su alcance** para que alguien los asuma.

Este documento hace exactamente eso: separa lo que está en el código de lo que
no puede estarlo.

> **No se ha comparado con las políticas de XENCO.** Esta herramienta se
> desarrolló sin acceso a la política de seguridad, la Declaración de
> Aplicabilidad ni el análisis de riesgos de la empresa. Cualquier afirmación
> de equivalencia con esos documentos tendría que hacerla quien los tenga
> delante. Aquí solo se declara qué hace el código.

## Qué es esta herramienta, en términos de riesgo

Antes que los controles, el riesgo, porque es lo que los justifica:

- **Inyecta entrada real** en una sesión del ERP. Mueve el puntero físico y el
  foco del teclado, porque el runtime Java ignora los mensajes sintéticos. Un
  click mal calculado pulsa lo que haya en ese píxel.
- **Captura la pantalla** y guarda PNG en disco. Esas capturas contienen los
  datos reales que estuvieran a la vista.
- **Corre con los permisos del usuario de Windows** y con la sesión de SAFIX
  ya autenticada. No tiene autenticación propia y no debería fingir tenerla:
  quien puede usar la herramienta es quien ya puede usar SAFIX.

## Controles implementados en el código

Cada uno se puede ejecutar y comprobar. La columna «prueba» dice con qué.

| Control (Anexo A 2022) | Qué hace el código | Prueba |
|---|---|---|
| **8.31** Separación de entornos | Lee el ambiente del **título de la ventana** (`[XENCO/Safix@SAFIXDEMOS/…]`) y **rechaza actuar** si no está en `ambientes_permitidos`. Falla **cerrado**: sin ambiente legible, no se actúa. Cubre toda inyección de entrada y también la captura | `pruebas_ambiente.py` (16) |
| **8.15** Registro de eventos | Cada captura y cada click deja línea con hora, **usuario**, **pid de la sesión**, **ambiente**, acción y avisos. Los rechazos se registran con marca `XX` | `pruebas_ambiente.py` §4 |
| **8.15** Fiabilidad del registro | La escritura se traga sus errores para no tumbar una captura, pero **los anota y los expone**: `forms_ventanas` muestra siempre la ruta del registro, porque el modo de fallo real no es una excepción sino escribir en el sitio equivocado sin queja | `verificar_entorno.py` |
| **8.28** Codificación segura | Contrato explícito de éxito/fallo (`[FALLO]`, `[AVISO]`) en vez de adivinar por subcadenas. `pruebas_contrato.py` **audita el código fuente** de las cuatro capas y falla si un retorno de fallo no lo lleva | `pruebas_contrato.py` (16) |
| **8.28** Codificación segura | La herramienta **se niega a pulsar** botones cuyo `WHEN-BUTTON-PRESSED` contiene `COMMIT`, `RUN_PRODUCT`, `DELETE_RECORD`, `FORMS_DDL` u otros verbos que escriben. La lista está en `ajustes.json` | `forms_plan` los lista como NO TOCAR |
| **8.28** Codificación segura | `F10` y `CTRL+S` bloqueadas; no se inyecta nada si la ventana no logra ponerse en primer plano, para no escribir en otra aplicación | `winauto.pulsar` |
| **8.9** Gestión de configuración | Toda la configuración por variables de entorno y `ajustes.json`; 13 ajustes con valores de respaldo en código y validación de tipo, para que una edición torpe no deje la herramienta inservible | `pruebas_ajustes.py` (16) |
| **8.32** Gestión de cambios | Repositorio git con historia; `.gitignore` excluye el estado de máquina y la configuración con credenciales | `git log` |
| **8.25** Ciclo de vida seguro | 67 comprobaciones, de las que 67 corren sin abrir el ERP. Dos auditan el **código** y no un resultado | las 5 suites |

## Controles que el código NO puede implementar

Estos quedan **fuera del alcance del software** y necesitan que alguien los
asuma en el SGSI. No están implementados y no deben contarse como tales.

| Control | Por qué está fuera | Quién debería asumirlo |
|---|---|---|
| **5.1** Políticas de seguridad | Es un documento de la organización | Responsable del SGSI |
| **5.15 / 8.2** Control de acceso, derechos privilegiados | La herramienta hereda la sesión de Windows y la de SAFIX. **No tiene autenticación propia**, y añadirle una sería seguridad aparente: quien puede ejecutarla ya puede usar SAFIX | Administración de accesos |
| **8.12** Prevención de fuga de datos | Las capturas **contienen datos reales** del registro consultado y se guardan sin cifrar en una carpeta de documentación. El código no clasifica ni redacta lo que fotografía | Clasificación de la información. Ver *riesgo abierto* abajo |
| **8.16** Monitorización | El registro es un `.log` local, sin envío a un SIEM ni protección contra borrado | Operaciones de seguridad |
| **8.24** Criptografía | Ni el registro ni las capturas se cifran | Cifrado en reposo del puesto |
| **8.13 / 8.10** Respaldo y borrado | No hay política de retención de capturas ni de registros | Gestión documental |
| **6.3** Concienciación | La precondición «úsala contra `SAFIXDEMOS`» está en el código, pero quien la opera debe entender por qué | Formación |
| **5.19–5.22** Proveedores | Depende de `mcp`, `mss`, `pillow`. Versiones acotadas, sin verificación de firma ni SBOM | Gestión de terceros |

## Riesgo abierto que conviene decidir, no dejar implícito

**Las capturas contienen datos reales.** En la corrida de `binmueb` se
fotografió el registro con matrícula `346789097612`: nombre del inmueble,
departamento, municipio, escritura y destino. Esas 70 imágenes están en
`07-documentacion/imagenes/Ayudas/…` y de ahí van a un manual de usuario.

El control 8.12 no está implementado y el código no puede decidirlo solo. Hay
tres salidas y **es una decisión de negocio**:

1. Fotografiar solo con datos de prueba en el ambiente de demostración.
2. Aceptar los datos de demostración como no sensibles, por escrito.
3. Anonimizar antes de publicar el manual.

Mientras no se decida, el riesgo es que un manual distribuido contenga datos
de un cliente real.

## Precondición operativa del control 8.31

SAFIX **solo rotula el ambiente en el título cuando el inicio de sesión está
completo con empresa y período**. Antes de eso el título es
`XENCO - Administracion del Sistema` y no declara nada, así que el control
—que falla cerrado— **rechaza actuar**. Medido el 2026-09-04.

No es un defecto: es la consecuencia correcta de no actuar sin saber contra qué
base se trabaja. Quien opere la herramienta debe completar el inicio de sesión
antes de empezar. `verificar_entorno.py` lo dice con esas palabras.

## Cómo comprobar los controles

```bash
python pruebas_ambiente.py      # 16 — separación de ambientes (8.31, 8.15)
python pruebas_contrato.py      # 16 — contrato de fallo (8.28)
python pruebas_ajustes.py       # 16 — configuración (8.9)
python pruebas_deteccion.py     # 19 — detección y comparación
python verificar_entorno.py     # entorno, ambientes y bitácora
```

Las pruebas de ambiente **no abren producción para comprobar que se rechaza**:
sustituyen la lectura del título por títulos de prueba, incluido uno de
producción. Comprobar un control de separación de entornos entrando en
producción sería el propio incidente que el control evita.

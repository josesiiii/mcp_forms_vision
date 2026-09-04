# Instala forms-vision en esta maquina, DESDE el repo.
#
# Hace tres cosas:
#   1. crea el venv en %LOCALAPPDATA%\forms-vision-venv
#   2. COPIA el codigo a %LOCALAPPDATA%\forms-vision
#   3. imprime la configuracion exacta para el panel de MCP
#
# Por que copiar el codigo a local en vez de ejecutarlo desde el repo: el
# servidor MCP arranca en CADA llamada. Si el repo vive en un recurso de red
# -el caso donde se desarrollo- eso cruza la red constantemente. El venv,
# ademas, en red es tan lento que el 'pip install' no termina.
#
# Los DATOS (extracts, fotos, pendientes) SI se quedan en la red: ahi viven y
# ahi los espera el equipo. Solo baja el codigo.
#
# Uso:
#   powershell -ExecutionPolicy Bypass -File instalar.ps1 -Proyecto Z:\Projects
#   powershell -ExecutionPolicy Bypass -File instalar.ps1 -SoloCodigo

param(
    [string]$Proyecto = "",
    [switch]$SoloCodigo
)

$ErrorActionPreference = "Stop"

$repo  = $PSScriptRoot
$local = Join-Path $env:LOCALAPPDATA "forms-vision"
$venv  = Join-Path $env:LOCALAPPDATA "forms-vision-venv"
$py    = Join-Path $venv "Scripts\python.exe"

# Lo que se instala se DERIVA de lo que hay en el repo, no se enumera a mano:
# la lista escrita a mano se quedo atras en cuanto server.py se partio en
# nucleo/plan/calibra, y una instalacion sin uno de esos modulos deja el MCP
# sin arrancar.
#
# calibraciones.json queda EXCLUIDO a proposito: es estado de cada maquina
# (geometria medida contra esta pantalla) y el servidor lo crea al primer
# forms_calibrar. Copiarlo desviaria los clicks en otra maquina.
$excluir = @("calibraciones.json")
$fuentes = Get-ChildItem $PSScriptRoot -File |
    Where-Object { $_.Extension -in @(".py", ".json", ".md", ".txt") } |
    Where-Object { $_.Name -notin $excluir } |
    ForEach-Object { $_.Name }

# ── 1. entorno ───────────────────────────────────────────────────────────────
if (-not $SoloCodigo) {
    if (Test-Path $py) {
        Write-Host "Entorno ya existe: $venv"
    } else {
        Write-Host "Creando entorno en $venv ..."
        python -m venv $venv
    }
    Write-Host "Instalando dependencias ..."
    & $py -m pip install --quiet --disable-pip-version-check `
        -r (Join-Path $repo "requirements.txt")
    & $py -c "import mss, PIL; from mcp.server.mcpserver import MCPServer; print('  mss', mss.__version__, '| pillow', PIL.__version__, '| mcp OK')"
}

# ── 2. el codigo, a local ────────────────────────────────────────────────────
New-Item -ItemType Directory -Force -Path $local | Out-Null
$copiados = 0
foreach ($f in $fuentes) {
    $src = Join-Path $repo $f
    if (-not (Test-Path $src)) {
        Write-Host "  OJO: falta en el repo -> $f"
        continue
    }
    Copy-Item $src (Join-Path $local $f) -Force
    $copiados++
}
Write-Host "$copiados archivos instalados en $local"

# ── 3. configuracion ─────────────────────────────────────────────────────────
if (-not $Proyecto) {
    $Proyecto = "<RAIZ DEL PROYECTO SAFIX>"
    Write-Host ""
    Write-Host "OJO: no se indico -Proyecto. FORMS_VISION_PROYECTO es OBLIGATORIA:"
    Write-Host "     el servidor ya no la deduce de su ubicacion, y desde"
    Write-Host "     %LOCALAPPDATA% subir tres niveles da una ruta absurda."
}

Write-Host ""
Write-Host "Anade esto en el panel 'Servidores MCP locales' de la app"
Write-Host "(o en %APPDATA%\Claude\claude_desktop_config.json):"
Write-Host ""
$cfg = [ordered]@{
    command = $py
    args    = @((Join-Path $local "server.py"))
    env     = [ordered]@{
        FORMS_VISION_PROYECTO          = $Proyecto
        FORMS_VISION_JNLP              = "C:\Scripdominio\SAFIXV4.jnlp"
        FORMS_VISION_SALIDA            = (Join-Path $Proyecto "06-frontend\forms\_capturas")
        FORMS_VISION_TECLAS_BLOQUEADAS = "F10,CTRL+S"
    }
}
@{ "forms-vision" = $cfg } | ConvertTo-Json -Depth 6

Write-Host ""
Write-Host "Luego comprueba:"
Write-Host "  cd `"$local`""
Write-Host "  `$env:FORMS_VISION_PROYECTO = `"$Proyecto`""
# Las suites se enumeran leyendo la carpeta, igual que $fuentes: la lista
# escrita a mano ya se quedo atras una vez -no mencionaba pruebas_contrato ni
# pruebas_ambiente- y una comprobacion que nadie sabe que existe no comprueba.
Get-ChildItem $PSScriptRoot -File -Filter "pruebas_*.py" |
    Sort-Object Name |
    ForEach-Object { Write-Host ("  & `"$py`" {0,-24}# sin SAFIX" -f $_.Name) }
Write-Host "  & `"$py`" verificar_entorno.py    # entorno + captura real"
Write-Host ""
Write-Host "Y no lo olvides: esta herramienta inyecta entrada REAL y maneja una"
Write-Host "sesion de SAFIX en vivo. El control A.8.31 solo la deja actuar en los"
Write-Host "ambientes de ajustes.json, y para leer el ambiente SAFIX necesita el"
Write-Host "inicio de sesion completo con empresa y periodo. Ver SEGURIDAD.md."

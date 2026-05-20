# setupWin.ps1 - Instala Aikiu en Windows (version Groq, sin Ollama ni Whisper local)

$ErrorActionPreference = "Stop"

function Write-Ok   ($msg) { Write-Host "  [OK] $msg" -ForegroundColor Green }
function Write-Info ($msg) { Write-Host "  ->   $msg" -ForegroundColor Yellow }
function Write-Err  ($msg) { Write-Host "  [ERROR] $msg" -ForegroundColor Red }

$DIR = $PSScriptRoot
if (-not $DIR) { $DIR = Split-Path -Parent $MyInvocation.MyCommand.Definition }
Set-Location $DIR

Write-Host ""
Write-Host "  Aikiu - Setup"
Write-Host ""

# Python
Write-Info "Verificando Python..."

$pythonExe  = $null
$pythonArgs = @()

$candidates = @(
    @{ Exe = "py";     Args = @("-3.11") },
    @{ Exe = "py";     Args = @("-3")    },
    @{ Exe = "python"; Args = @()        }
)

foreach ($c in $candidates) {
    try {
        $out = & $c.Exe @($c.Args + @("--version")) 2>&1
        if ($LASTEXITCODE -eq 0) {
            $pythonExe  = $c.Exe
            $pythonArgs = $c.Args
            Write-Ok "Python: $out"
            break
        }
    } catch { }
}

if (-not $pythonExe) {
    Write-Err "No se encontro Python. Instalalo desde https://www.python.org/downloads/"
    exit 1
}

# Entorno virtual
Write-Info "Configurando entorno Python..."

if (-not (Test-Path "$DIR\venv")) {
    & $pythonExe @($pythonArgs + @("-m", "venv", "$DIR\venv"))
    if ($LASTEXITCODE -ne 0) {
        Write-Err "No se pudo crear el entorno virtual."
        exit 1
    }
}

$venvPython = "$DIR\venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    Write-Err "No se encontro $venvPython tras crear el venv."
    exit 1
}

& $venvPython -m pip install -q --upgrade pip
& $venvPython -m pip install -q -r "$DIR\requirements.txt"
Write-Ok "Dependencias instaladas"

# Verificar .env
if (-not (Test-Path "$DIR\.env")) {
    Copy-Item "$DIR\.env.example" "$DIR\.env"
}

$placeholders = Select-String -Path "$DIR\.env" -Pattern "PEGA_TU_TELEGRAM_BOT_TOKEN|PEGA_TU_GROQ" -Quiet

if ($placeholders) {
    Write-Host ""
    Write-Host "  Completa .env antes de iniciar:"
    Write-Host "  notepad .env"
    Write-Host ""
    Write-Host "  Necesitas (solo 2 obligatorios):"
    Write-Host "  - BOT_TOKEN    -> @BotFather en Telegram"
    Write-Host "  - GROQ_API_KEY -> console.groq.com (gratis)"
    Write-Host ""
    Write-Host "  Opcional: FAMILIAR_BOT_TOKEN (segundo bot para alertas)."
    Write-Host "  Los chat_id se registran solos cuando el adulto/familiar mandan /start."
    Write-Host ""
} else {
    Write-Host ""
    Write-Ok ".env configurado"
    Write-Host "  Inicia con: .\startWin.ps1" -ForegroundColor Green
    Write-Host "  Tip: la primera vez, pedile al adulto que abra el bot y mande /start." -ForegroundColor Yellow
    Write-Host ""
}

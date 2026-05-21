# instalarWin.ps1 - Instalador completo de Aikiu para Windows
# Hace todo de punta a punta: dependencias, credenciales, perfil y arranque.

$ErrorActionPreference = "Stop"

# ---------- UI helpers --------------------------------------------------------

function Write-Title($text) {
    Write-Host ""
    Write-Host ("=" * 60) -ForegroundColor Cyan
    Write-Host "  $text" -ForegroundColor Cyan
    Write-Host ("=" * 60) -ForegroundColor Cyan
    Write-Host ""
}

function Write-Step($n, $total, $text) {
    Write-Host ""
    Write-Host ("-" * 60) -ForegroundColor DarkCyan
    Write-Host "  [$n/$total]  $text" -ForegroundColor Cyan
    Write-Host ("-" * 60) -ForegroundColor DarkCyan
    Write-Host ""
}

function Write-Ok   ($msg) { Write-Host "  [OK]    $msg" -ForegroundColor Green }
function Write-Info ($msg) { Write-Host "  ->      $msg" -ForegroundColor Yellow }
function Write-Warn ($msg) { Write-Host "  [aviso] $msg" -ForegroundColor Yellow }
function Write-Err  ($msg) { Write-Host "  [ERROR] $msg" -ForegroundColor Red }

function Ask-NonEmpty($label) {
    while ($true) {
        $resp = (Read-Host "  $label").Trim()
        if (-not [string]::IsNullOrWhiteSpace($resp)) { return $resp }
        Write-Host "    (no puede estar vacio)" -ForegroundColor Red
    }
}

function Ask-YesNo($prompt, [bool]$defaultYes = $true) {
    $suffix = if ($defaultYes) { "[S/n]" } else { "[s/N]" }
    $resp = (Read-Host "  $prompt $suffix").Trim().ToLower()
    if ([string]::IsNullOrWhiteSpace($resp)) { return $defaultYes }
    return ($resp -eq "s" -or $resp -eq "si" -or $resp -eq "y" -or $resp -eq "yes")
}

function Show-CredentialHelp {
    param(
        [string]   $Title,
        [string]   $Que,
        [string[]] $Pasos,
        [string]   $Ejemplo,
        [string[]] $Notas
    )
    Write-Host ""
    Write-Host "  ----------------------------------------------------------" -ForegroundColor DarkGray
    Write-Host "    $Title" -ForegroundColor Cyan
    Write-Host "  ----------------------------------------------------------" -ForegroundColor DarkGray
    if ($Que) {
        Write-Host "    Que es:  $Que" -ForegroundColor Gray
        Write-Host ""
    }
    if ($Pasos) {
        Write-Host "    Como obtenerlo:" -ForegroundColor Gray
        foreach ($p in $Pasos) {
            Write-Host "      $p" -ForegroundColor Gray
        }
    }
    if ($Ejemplo) {
        Write-Host ""
        Write-Host "    Se ve asi:  $Ejemplo" -ForegroundColor DarkGray
    }
    if ($Notas) {
        Write-Host ""
        foreach ($n in $Notas) {
            Write-Host "    NOTA: $n" -ForegroundColor Yellow
        }
    }
    Write-Host ""
}

# ---------- Setup -------------------------------------------------------------

$DIR = $PSScriptRoot
if (-not $DIR) { $DIR = Split-Path -Parent $MyInvocation.MyCommand.Definition }
Set-Location $DIR

Write-Title "Aikiu - Instalador para Windows"

Write-Host "  Voy a guiarte paso a paso. Vamos a:"
Write-Host "    1. Verificar Python e instalar dependencias"
Write-Host "    2. Configurar tokens (Telegram + Groq) -- sin pedir chat_id"
Write-Host "    3. Armar el perfil de la persona que va a usar el asistente"
Write-Host "    4. (Opcional) arrancar el bot"
Write-Host ""
Read-Host "  Apreta Enter para empezar" | Out-Null

# ============================================================================
# 1. Python + venv + dependencias
# ============================================================================
Write-Step 1 4 "Python y dependencias"

$venvPython = "$DIR\venv\Scripts\python.exe"

if (-not (Test-Path $venvPython)) {
    $pythonExe  = $null
    $pythonArgs = @()
    foreach ($c in @(
        @{ Exe = "py";     Args = @("-3.11") },
        @{ Exe = "py";     Args = @("-3")    },
        @{ Exe = "python"; Args = @()        }
    )) {
        try {
            $out = & $c.Exe @($c.Args + @("--version")) 2>&1
            if ($LASTEXITCODE -eq 0) {
                $pythonExe  = $c.Exe
                $pythonArgs = $c.Args
                Write-Ok "Python detectado: $out"
                break
            }
        } catch { }
    }

    if (-not $pythonExe) {
        Write-Err "No se encontro Python en el sistema."
        Write-Host "  Instalalo desde https://www.python.org/downloads/ y volve a correr este script."
        Write-Host "  (o probá: winget install --id Python.Python.3.11 --scope user)"
        exit 1
    }

    Write-Info "Creando entorno virtual (venv)..."
    & $pythonExe @($pythonArgs + @("-m", "venv", "$DIR\venv"))
    if ($LASTEXITCODE -ne 0) { Write-Err "No se pudo crear el venv."; exit 1 }
    Write-Ok "venv creado"
} else {
    Write-Ok "venv ya existe (saltando deteccion de Python global)"
}

if (-not (Test-Path $venvPython)) {
    Write-Err "No se encontro $venvPython"
    exit 1
}

Write-Info "Instalando dependencias (puede tardar un minuto)..."
& $venvPython -m pip install --quiet --upgrade pip
& $venvPython -m pip install --quiet -r "$DIR\requirements.txt"
Write-Ok "Dependencias instaladas"

# ============================================================================
# 2. Credenciales (.env)
# ============================================================================
Write-Step 2 4 "Tokens y API keys"

$envExists = Test-Path "$DIR\.env"
$envHasPlaceholders = $false
if ($envExists) {
    $envHasPlaceholders = [bool](Select-String -Path "$DIR\.env" -Pattern "PEGA_TU" -Quiet)
}

$reconfigEnv = $true
if ($envExists -and -not $envHasPlaceholders) {
    Write-Warn "Ya existe un .env totalmente configurado."
    $reconfigEnv = Ask-YesNo "Queres reconfigurar las credenciales?" $false
}

if ($reconfigEnv) {
    Write-Host "  Vamos a pedir SOLO 2 datos obligatorios (BOT_TOKEN, GROQ_API_KEY)"
    Write-Host "  y al final preguntamos si queres tambien el bot familiar (opcional)."
    Write-Host ""
    Write-Host "  Los chat_id (ni del adulto ni del familiar) hacen falta:"
    Write-Host "  se registran solos la primera vez que cada uno abre el bot y manda /start."
    Write-Host ""
    Write-Host "  Antes de cada pregunta te explico que es y como sacarlo. Si todavia"
    Write-Host "  no lo tenes, segui los pasos y volve cuando lo tengas en el portapapeles."
    Write-Host ""

    # ---------------- BOT_TOKEN -----------------------------------------------
    Show-CredentialHelp `
        -Title "1/2  -  BOT_TOKEN  (token del bot principal)" `
        -Que   "Es el bot de Telegram que va a CHARLAR con la persona mayor." `
        -Pasos @(
            "1. En tu Telegram, busca el contacto @BotFather y abrilo.",
            "2. Enviale el comando:  /newbot",
            "3. Te pide un NOMBRE para el bot (lo que vera la persona mayor).",
            "   Ej: 'Clarita' o 'Asistente de Mama'.",
            "4. Te pide un USERNAME unico que termine en 'bot'.",
            "   Ej: 'clarita_para_marta_bot'",
            "5. BotFather te responde con el token. Copialo COMPLETO y pegalo aca."
        ) `
        -Ejemplo "8123456789:AAEhBOLpQjK_xxxxxxxxxxxxxxxxxxxxxx" `
        -Notas @(
            "Apenas arranque Aikiu, desde el celular de la PERSONA MAYOR,",
            "abrir el bot recien creado y mandarle /start. Ese primer /start",
            "queda registrado como el dueno del bot (nadie mas podra usarlo)."
        )

    $botToken = Ask-NonEmpty "BOT_TOKEN"
    if ($botToken -notmatch '^\d+:[A-Za-z0-9_-]+$') {
        Write-Warn "El formato no parece un BOT_TOKEN tipico (numeros:letras). Lo guardo igual."
    }

    # ---------------- GROQ_API_KEY --------------------------------------------
    Show-CredentialHelp `
        -Title "2/2  -  GROQ_API_KEY  (cerebro del bot, gratis)" `
        -Que   "Es la API key del LLM que entiende y responde. Groq es gratis." `
        -Pasos @(
            "1. Entra a:  https://console.groq.com",
            "2. Registrate con Google o con email (es gratis, sin tarjeta).",
            "3. En el menu lateral, anda a 'API Keys'.",
            "4. Click en 'Create API Key'. Ponele un nombre (ej: 'aikiu').",
            "5. Te muestra la key UNA sola vez. Copiala y pegala aca."
        ) `
        -Ejemplo "gsk_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx" `
        -Notas @(
            "Si cerras la ventana sin copiar la key, no la vas a poder ver",
            "de nuevo: hay que crear una nueva. La vieja se puede borrar."
        )

    $groqKey = Ask-NonEmpty "GROQ_API_KEY"
    if (-not $groqKey.StartsWith("gsk_")) {
        Write-Warn "Las API keys de Groq suelen empezar con 'gsk_'. Lo guardo igual."
    }

    # ---------------- Bot familiar (opcional) ---------------------------------
    Write-Host ""
    Write-Host "  ----------------------------------------------------------" -ForegroundColor DarkGray
    Write-Host "    Extra (opcional) - Bot familiar" -ForegroundColor Cyan
    Write-Host "  ----------------------------------------------------------" -ForegroundColor DarkGray
    Write-Host "    El bot familiar manda avisos a un familiar cuando pasan cosas" -ForegroundColor Gray
    Write-Host "    importantes (ej: la persona no escribe hace 4 horas, dijo algo" -ForegroundColor Gray
    Write-Host "    angustiante, etc.). Es un SEGUNDO bot, distinto del primero." -ForegroundColor Gray
    Write-Host ""
    Write-Host "    Lo podes saltear ahora y configurarlo despues editando .env." -ForegroundColor Gray
    Write-Host ""

    $useFamiliar = Ask-YesNo "Queres configurar el bot familiar ahora?" $false

    $familiarToken = "PEGA_TU_FAMILIAR_BOT_TOKEN_AQUI"

    if ($useFamiliar) {
        Show-CredentialHelp `
            -Title "Extra  -  FAMILIAR_BOT_TOKEN" `
            -Que   "Token de un SEGUNDO bot, distinto del que charla con la persona." `
            -Pasos @(
                "1. En tu Telegram, ir de nuevo a @BotFather.",
                "2. /newbot  (creas OTRO bot, distinto del primero).",
                "3. Nombre: por ej 'Avisos Aikiu - familia'.",
                "4. Username unico terminado en 'bot' (ej: aikiu_familia_xxx_bot).",
                "5. Copia el token que te devuelve."
            ) `
            -Ejemplo "8987654321:BBFhPmKxxxxxxxxxxxxxxxxxxxxxxxxxxxx" `
            -Notas @(
                "Cada FAMILIAR que quiera recibir avisos tiene que abrir el bot",
                "que acabas de crear y mandarle /start. Ese acto lo suscribe;",
                "no hace falta pedir ningun CHAT_ID a mano."
            )

        $familiarToken = Ask-NonEmpty "FAMILIAR_BOT_TOKEN"
        if ($familiarToken -notmatch '^\d+:[A-Za-z0-9_-]+$') {
            Write-Warn "El formato no parece un BOT_TOKEN. Lo guardo igual."
        }
    }

    $envContent = @"
BOT_TOKEN=$botToken
GROQ_API_KEY=$groqKey

FAMILIAR_BOT_TOKEN=$familiarToken
"@

    Set-Content -Path "$DIR\.env" -Value $envContent -Encoding UTF8
    Write-Host ""
    Write-Ok ".env guardado"
} else {
    Write-Info "Manteniendo .env existente."
}

# ============================================================================
# 3. Perfil de la persona (configurar.py)
# ============================================================================
Write-Step 3 4 "Perfil de la persona"

$reconfigProfile = $true
if (Test-Path "$DIR\perfil.md") {
    Write-Warn "Ya existe un perfil cargado (perfil.md)."
    $reconfigProfile = Ask-YesNo "Queres rehacerlo?" $false
}

if ($reconfigProfile) {
    Write-Host "  Te voy a hacer preguntas sobre la persona que va a usar el asistente"
    Write-Host "  (nombre, gustos, familia, salud, etc.). En cada una podes apretar"
    Write-Host "  Enter para aceptar el valor sugerido."
    Write-Host ""
    Read-Host "  Apreta Enter para arrancar el cuestionario" | Out-Null

    $env:PYTHONIOENCODING = "utf-8"
    try { chcp 65001 | Out-Null } catch { }

    & $venvPython "$DIR\configurar.py"
    if ($LASTEXITCODE -ne 0) {
        Write-Err "El cuestionario fue interrumpido. Podes volver a correrlo despues con:"
        Write-Host "    .\venv\Scripts\python.exe configurar.py"
        exit 1
    }
} else {
    Write-Info "Manteniendo perfil existente."
}

# ============================================================================
# 4. Listo - arrancar?
# ============================================================================
Write-Step 4 4 "Instalacion completa"

Write-Ok "Todo listo."
Write-Host ""
Write-Host "  Resumen:" -ForegroundColor Cyan
Write-Host "    - venv:      $DIR\venv"
Write-Host "    - .env:      $DIR\.env"
Write-Host "    - perfil:    $DIR\perfil.md"
Write-Host "    - config:    $DIR\config.yml"
Write-Host ""

$start = Ask-YesNo "Queres arrancar el bot ahora?" $true
if ($start) {
    Write-Host ""
    & "$DIR\startWin.ps1"
} else {
    Write-Host ""
    Write-Host "  Cuando quieras arrancarlo:" -ForegroundColor Green
    Write-Host "    .\startWin.ps1" -ForegroundColor Green
    Write-Host ""
    Write-Host "  Si en algun momento queres rehacer el perfil:" -ForegroundColor Gray
    Write-Host "    .\venv\Scripts\python.exe configurar.py" -ForegroundColor Gray
    Write-Host ""
}

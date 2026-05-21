# startWin.ps1 - Lanza Aikiu en Windows

$ErrorActionPreference = "Stop"

$DIR = $PSScriptRoot
if (-not $DIR) { $DIR = Split-Path -Parent $MyInvocation.MyCommand.Definition }
Set-Location $DIR

function Read-EnvFile {
    $map = @{}
    if (-not (Test-Path "$DIR\.env")) { return $map }
    Get-Content -Path "$DIR\.env" | ForEach-Object {
        $line = $_.Trim()
        if ($line -and -not $line.StartsWith("#") -and $line.Contains("=")) {
            $parts = $line -split "=", 2
            $map[$parts[0].Trim()] = $parts[1].Trim()
        }
    }
    return $map
}

$envVars = Read-EnvFile

foreach ($var in @("BOT_TOKEN", "GROQ_API_KEY")) {
    $val = $envVars[$var]
    if ([string]::IsNullOrWhiteSpace($val) -or $val -match "PEGA_TU") {
        Write-Host "  ERROR: Completa $var en .env" -ForegroundColor Red
        Write-Host "  notepad .env"
        exit 1
    }
}

# El chat_id del adulto se autoregistra en el primer /start (state.json).
if (-not (Test-Path "$DIR\state.json") -and [string]::IsNullOrWhiteSpace($envVars["CHAT_ID"])) {
    Write-Host ""
    Write-Host "  Nota: el adulto todavia no abrio el bot." -ForegroundColor Yellow
    Write-Host "  Apenas arranque, pedile que mande /start desde su Telegram." -ForegroundColor Yellow
    Write-Host ""
}

$venvPython = "$DIR\venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    Write-Host "  ERROR: Falta el entorno virtual. Ejecuta .\setupWin.ps1 primero." -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "  Aikiu iniciando..."
Write-Host "  Ctrl+C para detener."
Write-Host ""

$procs = @()
$procs += Start-Process -FilePath $venvPython -ArgumentList "aikiu.py" -NoNewWindow -PassThru

$familiarToken = $envVars["FAMILIAR_BOT_TOKEN"]
if (-not [string]::IsNullOrWhiteSpace($familiarToken) -and $familiarToken -notmatch "PEGA_TU") {
    $procs += Start-Process -FilePath $venvPython -ArgumentList "familiar_bot.py" -NoNewWindow -PassThru
    Write-Host "  Bot familiar activo."
}

try {
    while ($procs | Where-Object { $_ -and -not $_.HasExited }) {
        Start-Sleep -Seconds 1
    }
} finally {
    foreach ($p in $procs) {
        if ($p -and -not $p.HasExited) {
            try { Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue } catch { }
        }
    }
}

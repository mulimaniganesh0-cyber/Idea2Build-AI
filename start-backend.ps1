[CmdletBinding()]
param(
    [ValidateRange(1, 65535)]
    [int]$Port = 8000
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSCommandPath
$BackendRoot = Join-Path $ProjectRoot "backend"
$VenvPython = Join-Path $BackendRoot ".venv\Scripts\python.exe"
$Requirements = Join-Path $BackendRoot "requirements.txt"

if (-not (Test-Path -LiteralPath $Requirements)) {
    throw "Backend requirements file was not found: $Requirements"
}

if (-not (Test-Path -LiteralPath $VenvPython)) {
    Write-Host "Creating backend virtual environment..."
    Push-Location $BackendRoot
    try { python -m venv .venv } finally { Pop-Location }
}

Push-Location $BackendRoot
try {
    & $VenvPython -m pip install -r $Requirements

    $listener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($listener) {
        try {
            $health = Invoke-WebRequest -UseBasicParsing "http://127.0.0.1:$Port/api/v1/health" -TimeoutSec 2
            if ($health.StatusCode -eq 200) {
                Write-Host "AI-CAD Engineer API is already running at http://127.0.0.1:$Port"
                exit 0
            }
        } catch {
            # A different service owns the preferred port. Leave it untouched.
        }
        if ($Port -eq 8000) {
            $Port = 8001
            Write-Warning "Port 8000 is in use by another service. Starting AI-CAD Engineer on port 8001."
        } else {
            throw "Port $Port is already in use by another service."
        }
    }

    & $VenvPython -m uvicorn app.main:app --reload --host 127.0.0.1 --port $Port
} finally {
    Pop-Location
}

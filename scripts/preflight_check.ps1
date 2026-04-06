$ErrorActionPreference = "Stop"

function Write-Ok([string]$Message) {
    Write-Host "[preflight][ok] $Message" -ForegroundColor Green
}

function Write-WarnMsg([string]$Message) {
    Write-Host "[preflight][warn] $Message" -ForegroundColor Yellow
}

function Write-Fail([string]$Message) {
    Write-Host "[preflight][fail] $Message" -ForegroundColor Red
}

function Test-RequiredCommand {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][string]$Hint
    )
    if (Get-Command $Name -ErrorAction SilentlyContinue) {
        Write-Ok "$Name detected"
        return $true
    }

    Write-Fail "$Name is missing. $Hint"
    return $false
}

function Test-OptionalCommand {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][string]$Hint
    )
    if (Get-Command $Name -ErrorAction SilentlyContinue) {
        Write-Ok "$Name detected"
    }
    else {
        Write-WarnMsg "$Name is missing. $Hint"
    }
}

Write-Host "=== WritingBot preflight check ==="

$ok = $true
$ok = (Test-RequiredCommand -Name "python" -Hint "Install Python 3.11+ and add it to PATH.") -and $ok
$ok = (Test-RequiredCommand -Name "node" -Hint "Install Node.js 20 LTS from https://nodejs.org/.") -and $ok
$ok = (Test-RequiredCommand -Name "npm" -Hint "npm ships with Node.js; reinstall Node.js if needed.") -and $ok
Test-OptionalCommand -Name "bun" -Hint "FastWrite will run in degraded mode. Install from https://bun.sh/."

if (Get-Command python -ErrorAction SilentlyContinue) {
    & cmd /c "python -m pytest --version >nul 2>nul"
    if ($LASTEXITCODE -eq 0) {
        Write-Ok "pytest detected"
    }
    else {
        Write-WarnMsg "pytest is missing. Backend test commands may fail until dependencies are installed."
    }
}

if (-not $ok) {
    Write-Host "[preflight] Blocking dependency check failed." -ForegroundColor Red
    exit 1
}

Write-Host "[preflight] Environment is ready." -ForegroundColor Green

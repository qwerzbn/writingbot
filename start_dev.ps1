$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ProjectRoot

$LogDir = Join-Path $ProjectRoot ".logs"
if (-not (Test-Path $LogDir)) {
    New-Item -ItemType Directory -Path $LogDir | Out-Null
}

if (-not $env:WRITINGBOT_API_PORT) { $env:WRITINGBOT_API_PORT = "5001" }
if (-not $env:WRITINGBOT_WEB_PORT) { $env:WRITINGBOT_WEB_PORT = "3000" }
if (-not $env:FASTWRITE_WEB_PORT) { $env:FASTWRITE_WEB_PORT = "3002" }
if (-not $env:FASTWRITE_API_PORT) { $env:FASTWRITE_API_PORT = "3003" }
if (-not $env:WRITINGBOT_API_URL) { $env:WRITINGBOT_API_URL = "http://127.0.0.1:$($env:WRITINGBOT_API_PORT)" }
if (-not $env:FASTWRITE_URL) { $env:FASTWRITE_URL = "http://127.0.0.1:$($env:FASTWRITE_WEB_PORT)" }
if (-not $env:NEXT_PUBLIC_FASTWRITE_URL) { $env:NEXT_PUBLIC_FASTWRITE_URL = $env:FASTWRITE_URL }

Write-Host "[start_dev] Running dependency preflight check..."
& (Join-Path $ProjectRoot "scripts\preflight_check.ps1")
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

function Stop-PortProcess([int]$Port) {
    $entries = netstat -ano | Select-String ":$Port\s+.*LISTENING\s+(\d+)$"
    foreach ($entry in $entries) {
        $pid = [int]($entry.Matches[0].Groups[1].Value)
        if ($pid -gt 0) {
            try {
                Stop-Process -Id $pid -Force -ErrorAction Stop
                Write-Host "[start_dev][warn] Freed port $Port (pid=$pid)"
            }
            catch {
                Write-Host "[start_dev][warn] Could not stop pid=$pid on port $Port"
            }
        }
    }
}

Stop-PortProcess -Port ([int]$env:WRITINGBOT_API_PORT)
Stop-PortProcess -Port ([int]$env:WRITINGBOT_WEB_PORT)
Stop-PortProcess -Port ([int]$env:FASTWRITE_WEB_PORT)
Stop-PortProcess -Port ([int]$env:FASTWRITE_API_PORT)

function Start-ServiceProcess {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][string]$FilePath,
        [Parameter(Mandatory = $true)][string[]]$Arguments,
        [Parameter(Mandatory = $true)][string]$WorkingDirectory,
        [Parameter(Mandatory = $true)][string]$StdOutLog,
        [Parameter(Mandatory = $true)][string]$StdErrLog
    )

    Write-Host "[start_dev] Starting $Name ..."
    return Start-Process `
        -FilePath $FilePath `
        -ArgumentList $Arguments `
        -WorkingDirectory $WorkingDirectory `
        -RedirectStandardOutput $StdOutLog `
        -RedirectStandardError $StdErrLog `
        -PassThru
}

$Processes = @()

$backendArgs = @(
    "-m", "uvicorn", "src.api.main:app",
    "--host", "0.0.0.0",
    "--port", "$($env:WRITINGBOT_API_PORT)",
    "--reload",
    "--reload-exclude", "data/*",
    "--reload-exclude", "web/*",
    "--reload-exclude", ".git/*",
    "--reload-exclude", "FastWrite/*",
    "--reload-exclude", ".env"
)
$Processes += Start-ServiceProcess `
    -Name "WritingBot backend" `
    -FilePath "python" `
    -Arguments $backendArgs `
    -WorkingDirectory $ProjectRoot `
    -StdOutLog (Join-Path $LogDir "backend.log") `
    -StdErrLog (Join-Path $LogDir "backend.err.log")

$Processes += Start-ServiceProcess `
    -Name "WritingBot web" `
    -FilePath "npm" `
    -Arguments @("run", "dev") `
    -WorkingDirectory (Join-Path $ProjectRoot "web") `
    -StdOutLog (Join-Path $LogDir "web.log") `
    -StdErrLog (Join-Path $LogDir "web.err.log")

$fastWriteMode = "degraded"
$fastWriteRoot = Join-Path $ProjectRoot "FastWrite"
$bun = Get-Command bun -ErrorAction SilentlyContinue

if ((Test-Path (Join-Path $fastWriteRoot "package.json")) -and $bun) {
    $fastWriteMode = "enabled"
    $env:PORT = "$($env:FASTWRITE_API_PORT)"
    $Processes += Start-ServiceProcess `
        -Name "FastWrite API" `
        -FilePath "bun" `
        -Arguments @("run", "--watch", "src/server.ts") `
        -WorkingDirectory $fastWriteRoot `
        -StdOutLog (Join-Path $LogDir "fastwrite-api.log") `
        -StdErrLog (Join-Path $LogDir "fastwrite-api.err.log")

    $fastWriteWebDir = Join-Path $fastWriteRoot "web"
    if (Test-Path $fastWriteWebDir) {
        $Processes += Start-ServiceProcess `
            -Name "FastWrite web" `
            -FilePath "bun" `
            -Arguments @("run", "dev", "--no-open", "--port", "$($env:FASTWRITE_WEB_PORT)") `
            -WorkingDirectory $fastWriteWebDir `
            -StdOutLog (Join-Path $LogDir "fastwrite-web.log") `
            -StdErrLog (Join-Path $LogDir "fastwrite-web.err.log")
    }
    else {
        $fastWriteMode = "degraded"
        Write-Host "[start_dev][warn] FastWrite web directory missing; running without co-writer UI."
    }
}
else {
    Write-Host "[start_dev][warn] FastWrite unavailable (missing project or bun). Running in degraded mode."
}

Write-Host ""
Write-Host "=========================================="
Write-Host " WritingBot development services started"
Write-Host "=========================================="
Write-Host " WritingBot API : $($env:WRITINGBOT_API_URL)"
Write-Host " WritingBot Web : http://127.0.0.1:$($env:WRITINGBOT_WEB_PORT)"
Write-Host " FastWrite mode : $fastWriteMode"
if ($fastWriteMode -eq "enabled") {
    Write-Host " FastWrite API  : http://127.0.0.1:$($env:FASTWRITE_API_PORT)"
    Write-Host " FastWrite Web  : $($env:FASTWRITE_URL)"
}
Write-Host " Logs directory : $LogDir"
Write-Host "=========================================="
Write-Host " Press Ctrl+C to stop all services."
Write-Host ""

try {
    Wait-Process -Id ($Processes | ForEach-Object { $_.Id })
}
finally {
    foreach ($process in $Processes) {
        if ($process -and -not $process.HasExited) {
            try {
                Stop-Process -Id $process.Id -Force -ErrorAction Stop
            }
            catch {
                # Ignore cleanup failures.
            }
        }
    }
}

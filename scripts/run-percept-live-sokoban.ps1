param(
    [int]$RuntimePort = 3543,
    [int]$BackendPort = 8000,
    [int]$MaxSteps = 40,
    [int]$Episodes = 4,
    [double]$SleepSeconds = 0.4,
    [string]$GameId = "ps_sokoban_basic-v1",
    [switch]$FreshMemory
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Root = (Resolve-Path (Join-Path $ScriptDir "..")).Path
$OutputDir = Join-Path $Root "client\percept_live_sokoban\output"
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null

function Test-Port {
    param([int]$Port)

    $client = New-Object System.Net.Sockets.TcpClient
    try {
        $connect = $client.BeginConnect("127.0.0.1", $Port, $null, $null)
        if (-not $connect.AsyncWaitHandle.WaitOne(500, $false)) {
            return $false
        }
        $client.EndConnect($connect)
        return $true
    }
    catch {
        return $false
    }
    finally {
        $client.Close()
    }
}

function Wait-Port {
    param(
        [int]$Port,
        [string]$Name
    )

    for ($i = 0; $i -lt 40; $i++) {
        if (Test-Port -Port $Port) {
            return
        }
        Start-Sleep -Milliseconds 500
    }

    throw "$Name did not open port $Port in time."
}

$runtimeProcess = $null
$apiProcess = $null

try {
    if (-not (Test-Port -Port $RuntimePort)) {
        Write-Host "Starting PuzzleScript runtime on port $RuntimePort..."
        $npmCommand = Get-Command npm.cmd -ErrorAction SilentlyContinue
        if ($null -eq $npmCommand) {
            $npmCommand = Get-Command npm -ErrorAction Stop
        }

        $runtimeLog = Join-Path $OutputDir "percept-runtime.log"
        $runtimeErr = Join-Path $OutputDir "percept-runtime.err.log"
        $env:PORT = [string]$RuntimePort
        $runtimeProcess = Start-Process `
            -FilePath $npmCommand.Source `
            -ArgumentList @("start") `
            -WorkingDirectory $Root `
            -RedirectStandardOutput $runtimeLog `
            -RedirectStandardError $runtimeErr `
            -WindowStyle Hidden `
            -PassThru
        Wait-Port -Port $RuntimePort -Name "PuzzleScript runtime"
    }
    else {
        Write-Host "PuzzleScript runtime already listening on port $RuntimePort."
    }

    if (-not (Test-Port -Port $BackendPort)) {
        Write-Host "Starting ARC adapter on port $BackendPort..."
        $pythonCommand = Get-Command python -ErrorAction Stop
        $apiLog = Join-Path $OutputDir "percept-arc-adapter.log"
        $apiErr = Join-Path $OutputDir "percept-arc-adapter.err.log"
        $env:ARC_PROXY_PORT = [string]$BackendPort
        $env:PUZZLESCRIPT_SERVER_URL = "http://localhost:$RuntimePort"
        $apiProcess = Start-Process `
            -FilePath $pythonCommand.Source `
            -ArgumentList @("-m", "puzzlescript_interface.api.main") `
            -WorkingDirectory $Root `
            -RedirectStandardOutput $apiLog `
            -RedirectStandardError $apiErr `
            -WindowStyle Hidden `
            -PassThru
        Wait-Port -Port $BackendPort -Name "ARC adapter"
    }
    else {
        Write-Host "ARC adapter already listening on port $BackendPort."
    }

    Write-Host "Running symbol-percept LIVE experiment for $Episodes episode(s)..."
    $clientArgs = @(
        "-m",
        "client.percept_live_sokoban.run",
        "--backend-url",
        "http://localhost:$BackendPort",
        "--game-id",
        $GameId,
        "--max-steps",
        [string]$MaxSteps,
        "--episodes",
        [string]$Episodes,
        "--sleep",
        [string]$SleepSeconds
    )
    if ($FreshMemory) {
        $clientArgs += "--fresh-memory"
    }

    & python @clientArgs

    if ($LASTEXITCODE -ne 0) {
        throw "Percept LIVE run exited with code $LASTEXITCODE."
    }
}
finally {
    if ($null -ne $apiProcess -and -not $apiProcess.HasExited) {
        Stop-Process -Id $apiProcess.Id -Force
    }
    if ($null -ne $runtimeProcess -and -not $runtimeProcess.HasExited) {
        Stop-Process -Id $runtimeProcess.Id -Force
    }
    Write-Host "Rule file and service logs are in: $OutputDir"
}

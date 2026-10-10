param([int]$ExitAfterSeconds = 0)

$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$python = Join-Path $repoRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) {
    throw 'Install the project Python environment first (uv sync).'
}
foreach ($port in @(3544, 8001)) {
    if (Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue) {
        throw "Dedicated Enqueue port $port is already in use. No process was stopped."
    }
}

$children = [System.Collections.Generic.List[System.Diagnostics.Process]]::new()
function Start-EnqueueProcess {
    param([string]$FileName, [string]$Arguments, [hashtable]$Environment)
    $info = [System.Diagnostics.ProcessStartInfo]::new()
    $info.FileName = $FileName
    $info.Arguments = $Arguments
    $info.WorkingDirectory = $repoRoot
    $info.UseShellExecute = $false
    foreach ($key in $Environment.Keys) {
        $info.Environment[$key] = [string]$Environment[$key]
    }
    $process = [System.Diagnostics.Process]::new()
    $process.StartInfo = $info
    [void]$process.Start()
    $children.Add($process)
    Write-Host "Started Enqueue backend PID $($process.Id): $FileName $Arguments"
    return $process
}

try {
    $node = Start-EnqueueProcess -FileName 'node' `
        -Arguments 'puzzlescript_interface/runtime/server.js' `
        -Environment @{ PORT = '3544'; PUZZLESCRIPT_METHOD = 'ondemand' }
    $arc = Start-EnqueueProcess -FileName $python `
        -Arguments '-m puzzlescript_interface.api.main' `
        -Environment @{
            ARC_PROXY_PORT = '8001'
            PUZZLESCRIPT_SERVER_URL = 'http://127.0.0.1:3544'
            PUZZLESCRIPT_ONLY_GAME_ID = 'ps_enqueue-v1'
        }

    $ready = $false
    for ($attempt = 0; $attempt -lt 50; $attempt++) {
        if ($node.HasExited -or $arc.HasExited) { throw 'An Enqueue backend child exited during startup.' }
        try {
            $games = Invoke-RestMethod -Uri 'http://127.0.0.1:8001/api/games' -TimeoutSec 1
            if ($games.Count -eq 1 -and $games[0].game_id -eq 'ps_enqueue-v1') {
                $ready = $true
                break
            }
        } catch { }
        Start-Sleep -Milliseconds 200
    }
    if (-not $ready) { throw 'Enqueue ARC backend did not become ready.' }
    Write-Host 'Enqueue ARC backend: http://127.0.0.1:8001 (Docker: http://host.docker.internal:8001)'
    Write-Host 'Press Ctrl+C to stop both owned processes.'
    $startedAt = Get-Date
    while ($true) {
        if ($node.HasExited -or $arc.HasExited) { throw 'An Enqueue backend child exited.' }
        if ($ExitAfterSeconds -gt 0 -and ((Get-Date) - $startedAt).TotalSeconds -ge $ExitAfterSeconds) {
            break
        }
        Start-Sleep -Milliseconds 500
    }
} finally {
    foreach ($process in $children) {
        if (-not $process.HasExited) {
            Write-Host "Stopping owned Enqueue PID $($process.Id)"
            & taskkill.exe /PID $process.Id /T /F | Out-Null
            [void]$process.WaitForExit(5000)
        }
        $process.Dispose()
    }
}

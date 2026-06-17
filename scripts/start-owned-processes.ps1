param(
    [switch]$WithArcService,
    [int]$ExitAfterSeconds = 0
)

$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$runtimePort = 3543
if ($env:PORT) {
    $runtimePort = [int]$env:PORT
}
$arcPort = 8000
if ($env:ARC_PROXY_PORT) {
    $arcPort = [int]$env:ARC_PROXY_PORT
}
$children = New-Object System.Collections.Generic.List[System.Diagnostics.Process]

# Prefer uv if it is available; otherwise fall back to a system Python install.
$pythonFileName = "python"
$pythonArguments = "-m puzzlescript_interface.api.main"
$uvCmd = Get-Command uv -ErrorAction SilentlyContinue
if ($uvCmd) {
    $pythonFileName = "uv"
    $pythonArguments = "run python -m puzzlescript_interface.api.main"
}

function Stop-PortOwnerIfRuntime {
    param(
        [int]$Port,
        [string[]]$AllowedCommandParts
    )

    $connections = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    foreach ($connection in $connections) {
        $owner = Get-CimInstance Win32_Process -Filter "ProcessId=$($connection.OwningProcess)" -ErrorAction SilentlyContinue
        if ($null -eq $owner) {
            continue
        }

        $commandLine = [string]$owner.CommandLine
        $isKnownRuntime = $false
        foreach ($part in $AllowedCommandParts) {
            if ($commandLine -like "*$part*") {
                $isKnownRuntime = $true
                break
            }
        }

        if (-not $isKnownRuntime) {
            throw "Port ${Port} is already used by PID $($owner.ProcessId): $commandLine"
        }

        Write-Host "Stopping stale process on port ${Port}: PID $($owner.ProcessId)"
        Stop-Process -Id $owner.ProcessId -Force
    }
}

function Start-OwnedProcess {
    param(
        [string]$FileName,
        [string]$Arguments,
        [hashtable]$Environment = @{}
    )

    $startInfo = [System.Diagnostics.ProcessStartInfo]::new()
    $startInfo.FileName = $FileName
    $startInfo.Arguments = $Arguments
    $startInfo.WorkingDirectory = $repoRoot
    $startInfo.UseShellExecute = $false

    foreach ($key in $Environment.Keys) {
        $startInfo.Environment[$key] = [string]$Environment[$key]
    }

    $process = [System.Diagnostics.Process]::new()
    $process.StartInfo = $startInfo
    [void]$process.Start()
    $children.Add($process)
    Write-Host "Started PID $($process.Id): $FileName $Arguments"
    return $process
}

function Stop-Children {
    foreach ($child in $children) {
        if ($null -eq $child -or $child.HasExited) {
            continue
        }
        Write-Host "Stopping PID $($child.Id)"
        try {
            $child.Kill($true)
        } catch {
            Stop-Process -Id $child.Id -Force -ErrorAction SilentlyContinue
        }
    }
}

Stop-PortOwnerIfRuntime `
    -Port $runtimePort `
    -AllowedCommandParts @("puzzlescript_interface/runtime/server.js")

if ($WithArcService) {
    Stop-PortOwnerIfRuntime `
        -Port $arcPort `
        -AllowedCommandParts @("puzzlescript_interface.api.main", "puzzlescript_interface/api/main.py")
}

try {
    $runtime = Start-OwnedProcess `
        -FileName "node" `
        -Arguments "puzzlescript_interface/runtime/server.js" `
        -Environment @{ PORT = $runtimePort }

    if ($WithArcService) {
        $arcService = Start-OwnedProcess `
            -FileName $pythonFileName `
            -Arguments $pythonArguments `
            -Environment @{
                ARC_PROXY_PORT = $arcPort
                PUZZLESCRIPT_SERVER_URL = "http://127.0.0.1:$runtimePort"
            }
    }

    Write-Host ""
    Write-Host "Runtime: http://127.0.0.1:$runtimePort"
    if ($WithArcService) {
        Write-Host "ARC service: http://127.0.0.1:$arcPort"
    }
    Write-Host "Press Ctrl+C, or close this terminal, to stop owned processes."
    Write-Host ""

    $startedAt = Get-Date
    while ($true) {
        foreach ($child in $children) {
            if ($child.HasExited) {
                throw "Process PID $($child.Id) exited with code $($child.ExitCode)."
            }
        }
        if ($ExitAfterSeconds -gt 0 -and ((Get-Date) - $startedAt).TotalSeconds -ge $ExitAfterSeconds) {
            Write-Host "Smoke-test timeout reached; stopping owned processes."
            return
        }
        Start-Sleep -Milliseconds 500
    }
} finally {
    Stop-Children
}

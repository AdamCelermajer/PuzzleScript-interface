param(
    [int]$ExitAfterSeconds = 0
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$runtimePort = if ($env:PORT) { [int]$env:PORT } else { 3543 }
$arcPort = if ($env:ARC_PROXY_PORT) { [int]$env:ARC_PROXY_PORT } else { 8000 }
$apiPort = if ($env:WORKBENCH_API_PORT) { [int]$env:WORKBENCH_API_PORT } else { 8010 }
$webPort = if ($env:WORKBENCH_WEB_PORT) { [int]$env:WORKBENCH_WEB_PORT } else { 5173 }
$children = New-Object System.Collections.Generic.List[System.Diagnostics.Process]

$pythonFileName = "python"
$pythonPrefix = ""
$uvCmd = Get-Command uv -ErrorAction SilentlyContinue
if ($uvCmd) {
    $pythonFileName = "uv"
    $pythonPrefix = "run python "
}

function Get-PortOwner {
    param([int]$Port)
    return Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
        Select-Object -First 1
}

function Stop-KnownPortOwner {
    param([int]$Port, [string[]]$AllowedCommandParts)
    $connection = Get-PortOwner -Port $Port
    if ($null -eq $connection) { return }
    $owner = Get-CimInstance Win32_Process -Filter "ProcessId=$($connection.OwningProcess)" -ErrorAction SilentlyContinue
    $commandLine = [string]$owner.CommandLine
    $known = $false
    foreach ($part in $AllowedCommandParts) {
        if ($commandLine -like "*$part*") { $known = $true; break }
    }
    if (-not $known) {
        throw "Port ${Port} is already used by PID $($owner.ProcessId): $commandLine"
    }
    Write-Host "Stopping stale owned process on port ${Port}: PID $($owner.ProcessId)"
    Stop-Process -Id $owner.ProcessId -Force
}

function Find-WebPort {
    param([int]$Preferred)
    $candidate = $Preferred
    while ($null -ne (Get-PortOwner -Port $candidate)) { $candidate += 1 }
    return $candidate
}

function Wait-HttpReady {
    param([string]$Url, [int]$TimeoutSeconds = 20)
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        try {
            $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 2
            if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 500) { return }
        } catch {
            Start-Sleep -Milliseconds 200
        }
    }
    throw "Timed out waiting for $Url"
}

function Start-OwnedProcess {
    param([string]$FileName, [string]$Arguments, [hashtable]$Environment = @{})
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
        if ($null -eq $child -or $child.HasExited) { continue }
        Write-Host "Stopping PID $($child.Id)"
        try { $child.Kill($true) } catch { Stop-Process -Id $child.Id -Force -ErrorAction SilentlyContinue }
    }
}

Stop-KnownPortOwner -Port $runtimePort -AllowedCommandParts @("puzzlescript_interface/runtime/server.js")
Stop-KnownPortOwner -Port $arcPort -AllowedCommandParts @("puzzlescript_interface.api.main")
Stop-KnownPortOwner -Port $apiPort -AllowedCommandParts @("workbench.main", "workbench/main.py")
$webPort = Find-WebPort -Preferred $webPort

try {
    Start-OwnedProcess -FileName "node" -Arguments "puzzlescript_interface/runtime/server.js" -Environment @{ PORT = $runtimePort }
    Start-OwnedProcess -FileName $pythonFileName -Arguments "${pythonPrefix}-m puzzlescript_interface.api.main" -Environment @{
        ARC_PROXY_PORT = $arcPort
        PUZZLESCRIPT_SERVER_URL = "http://127.0.0.1:$runtimePort"
    }
    Wait-HttpReady -Url "http://127.0.0.1:$arcPort/api/games"
    Start-OwnedProcess -FileName $pythonFileName -Arguments "${pythonPrefix}-m workbench.main" -Environment @{
        WORKBENCH_API_PORT = $apiPort
    }
    Wait-HttpReady -Url "http://127.0.0.1:$apiPort/api/workbench/health"
    Start-OwnedProcess -FileName "node" -Arguments "node_modules/vite/bin/vite.js --config website/vite.config.js --host 127.0.0.1 --port $webPort --strictPort" -Environment @{
        WORKBENCH_API_PORT = $apiPort
    }
    Wait-HttpReady -Url "http://127.0.0.1:$webPort/"

    Write-Host ""
    Write-Host "Workbench: http://127.0.0.1:$webPort"
    Write-Host "Workbench API: http://127.0.0.1:$apiPort/api/workbench/health"
    Write-Host "Press Ctrl+C, or close this terminal, to stop all owned processes."
    Write-Host ""

    $startedAt = Get-Date
    while ($true) {
        foreach ($child in $children) {
            if ($child.HasExited) { throw "Process PID $($child.Id) exited with code $($child.ExitCode)." }
        }
        if ($ExitAfterSeconds -gt 0 -and ((Get-Date) - $startedAt).TotalSeconds -ge $ExitAfterSeconds) { return }
        Start-Sleep -Milliseconds 500
    }
} finally {
    Stop-Children
}

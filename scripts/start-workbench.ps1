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
$tailscaleDnsName = [string]$env:WORKBENCH_ALLOWED_HOSTS

try {
    $tailscale = Get-Command tailscale -ErrorAction Stop
    $tailscaleStatus = (& $tailscale.Source status --json | ConvertFrom-Json)
    $detectedDnsName = ([string]$tailscaleStatus.Self.DNSName).TrimEnd(".")
    if ($detectedDnsName) { $tailscaleDnsName = $detectedDnsName }
} catch {
    # Keep an explicitly configured hostname when Tailscale is temporarily unavailable.
}

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
        Where-Object { $_.LocalAddress -in @('127.0.0.1', '0.0.0.0', '::1', '::') } |
        Select-Object -First 1
}

function Test-HttpReady {
    param([string]$Url, [string]$Pattern)
    try {
        $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 2
        return $response.StatusCode -eq 200 -and $response.Content -match $Pattern
    } catch {
        return $false
    }
}

function Test-KnownPortOwner {
    param([int]$Port, [string[]]$AllowedCommandParts, [string]$HealthUrl, [string]$HealthPattern)
    $connection = Get-PortOwner -Port $Port
    if ($null -eq $connection) { return $false }
    $owner = Get-CimInstance Win32_Process -Filter "ProcessId=$($connection.OwningProcess)" -ErrorAction SilentlyContinue
    $commandLine = [string]$owner.CommandLine
    $known = $false
    foreach ($part in $AllowedCommandParts) {
        if ($commandLine -like "*$part*") { $known = $true; break }
    }
    # Some existing services have no readable command line. Their exact local
    # health response is enough to reuse them without touching their process.
    if (-not $known -and -not $commandLine) {
        $known = Test-HttpReady -Url $HealthUrl -Pattern $HealthPattern
    }
    if (-not $known) {
        throw "Port ${Port} is already used by PID $($owner.ProcessId): $commandLine"
    }
    if (-not (Test-HttpReady -Url $HealthUrl -Pattern $HealthPattern)) {
        throw "Service on port ${Port} is not healthy (PID $($owner.ProcessId))"
    }
    return $true
}

function Wait-HttpReady {
    param([string]$Url, [string]$Pattern, [int]$TimeoutSeconds = 20)
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        if (Test-HttpReady -Url $Url -Pattern $Pattern) { return }
        Start-Sleep -Milliseconds 200
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

try {
    $reportedReady = $false
    $lastError = ""
    $startedAt = Get-Date
    while ($true) {
        try {
            $runtimeUrl = "http://127.0.0.1:$runtimePort/health"
            $runtimePattern = '"service"\s*:\s*"puzzlescript-runtime"'
            if (-not (Test-KnownPortOwner -Port $runtimePort -AllowedCommandParts @("puzzlescript_interface/runtime/server.js") -HealthUrl $runtimeUrl -HealthPattern $runtimePattern)) {
                [void](Start-OwnedProcess -FileName "node" -Arguments "puzzlescript_interface/runtime/server.js" -Environment @{ PORT = $runtimePort })
                Wait-HttpReady -Url $runtimeUrl -Pattern $runtimePattern
            }

            $arcUrl = "http://127.0.0.1:$arcPort/api/games"
            $arcPattern = '"game_id"\s*:'
            if (-not (Test-KnownPortOwner -Port $arcPort -AllowedCommandParts @("puzzlescript_interface.api.main") -HealthUrl $arcUrl -HealthPattern $arcPattern)) {
                [void](Start-OwnedProcess -FileName $pythonFileName -Arguments "${pythonPrefix}-m puzzlescript_interface.api.main" -Environment @{
                    ARC_PROXY_PORT = $arcPort
                    PUZZLESCRIPT_SERVER_URL = "http://127.0.0.1:$runtimePort"
                })
                Wait-HttpReady -Url $arcUrl -Pattern $arcPattern
            }

            $apiUrl = "http://127.0.0.1:$apiPort/api/workbench/health"
            $apiPattern = '"ok"\s*:\s*true'
            if (-not (Test-KnownPortOwner -Port $apiPort -AllowedCommandParts @("workbench.main", "workbench/main.py") -HealthUrl $apiUrl -HealthPattern $apiPattern)) {
                [void](Start-OwnedProcess -FileName $pythonFileName -Arguments "${pythonPrefix}-m workbench.main" -Environment @{ WORKBENCH_API_PORT = $apiPort })
                Wait-HttpReady -Url $apiUrl -Pattern $apiPattern
            }

            $webUrl = "http://127.0.0.1:$webPort/"
            $webPattern = '<title>[^<]*Research Workbench'
            if (-not (Test-KnownPortOwner -Port $webPort -AllowedCommandParts @("vite.js", "vite/bin/vite") -HealthUrl $webUrl -HealthPattern $webPattern)) {
                [void](Start-OwnedProcess -FileName "node" -Arguments "website/app/node_modules/vite/bin/vite.js --config website/app/vite.config.ts --host 127.0.0.1 --port $webPort --strictPort" -Environment @{
                    WORKBENCH_API_PORT = $apiPort
                    WORKBENCH_ALLOWED_HOSTS = $tailscaleDnsName
                })
                Wait-HttpReady -Url $webUrl -Pattern $webPattern
            }
            if (-not (Test-HttpReady -Url "http://127.0.0.1:$webPort/api/workbench/health" -Pattern $apiPattern)) {
                throw "Website cannot reach the Workbench API"
            }
            if ($tailscaleDnsName) {
                if (-not (Test-HttpReady -Url "http://$tailscaleDnsName/" -Pattern $webPattern)) {
                    throw "Tailscale URL http://$tailscaleDnsName/ is not serving the Workbench"
                }
            }
            if (-not $reportedReady) {
                Write-Host "Workbench ready: $webUrl"
                if ($tailscaleDnsName) { Write-Host "Tailscale: http://$tailscaleDnsName/" }
                Write-Host "Press Ctrl+C, or close this terminal, to stop owned processes."
                $reportedReady = $true
            }
            $lastError = ""
        } catch {
            $message = $_.Exception.Message
            if ($message -ne $lastError) { Write-Warning "Workbench not ready: $message" }
            $lastError = $message
            $reportedReady = $false
        }
        if ($ExitAfterSeconds -gt 0 -and ((Get-Date) - $startedAt).TotalSeconds -ge $ExitAfterSeconds) { return }
        Start-Sleep -Seconds 5
    }
} finally {
    Stop-Children
}

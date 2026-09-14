$ErrorActionPreference = "Continue"

$repoRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$workbenchPath = Join-Path $repoRoot "scripts\start-workbench.ps1"

if (-not (Test-Path -LiteralPath $workbenchPath)) {
    throw "Workbench launcher is missing at $workbenchPath"
}

Set-Location -LiteralPath $repoRoot
$env:WORKBENCH_ALLOWED_HOSTS = "adampalace-pc.tail65f3f9.ts.net"
$Host.UI.RawUI.WindowTitle = "PuzzleScript Workbench - keep this terminal open"

# Replace the temporary hidden scheduled instance when this visible launcher starts.
$scheduledTask = Get-ScheduledTask -TaskName "PuzzleScript AVO Website" -ErrorAction SilentlyContinue
if ($scheduledTask.State -eq "Running") {
    Stop-ScheduledTask -TaskName $scheduledTask.TaskName
    $deadline = (Get-Date).AddSeconds(10)
    do {
        $listener = Get-NetTCPConnection -LocalPort 5173 -State Listen -ErrorAction SilentlyContinue |
            Where-Object LocalAddress -eq "127.0.0.1" |
            Select-Object -First 1
        if (-not $listener) {
            break
        }
        Start-Sleep -Milliseconds 250
    } while ((Get-Date) -lt $deadline)
}

Write-Host "Starting the PuzzleScript website, workbench API, and game services." -ForegroundColor Green
Write-Host "Windows:  http://127.0.0.1:5173/"
Write-Host "Fedora:   http://adampalace-pc.tail65f3f9.ts.net:5173/"
Write-Host "Keep this terminal open. If the workbench exits, it will restart automatically."

while ($true) {
    try {
        & $workbenchPath
    } catch {
        Write-Host "Workbench failed: $($_.Exception.Message)" -ForegroundColor Red
    }
    Write-Host "Workbench stopped; restarting in 2 seconds..." -ForegroundColor Yellow
    Start-Sleep -Seconds 2
}

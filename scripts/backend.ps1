param(
    [ValidateSet("up", "stop", "status", "logs", "build")]
    [string]$Action = "status"
)
$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$compose = @("compose", "--project-directory", $repoRoot, "-f", (Join-Path $repoRoot "compose.yaml"))
switch ($Action) {
    "up" { & docker @compose up -d --wait --wait-timeout 120 }
    "stop" { & docker @compose stop }
    "status" { & docker @compose ps -a }
    "logs" { & docker @compose logs --follow --tail 100 }
    "build" { & docker @compose build }
}
if ($LASTEXITCODE -ne 0) { throw "Backend '$Action' failed. Check that Docker Desktop is running and the ports are available." }

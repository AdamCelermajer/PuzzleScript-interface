# SSH tunnel for the self-hosted vLLM on vast.ai: localhost:18100 -> instance 127.0.0.1:18000.
# Reconnects until stopped. Docker game containers reach it at host.docker.internal:18100.
#   Start: Start-Process powershell -WindowStyle Hidden -ArgumentList '-NoProfile','-ExecutionPolicy','Bypass','-File','scripts\vast-tunnel.ps1'
#   Stop:  Get-CimInstance Win32_Process | ? CommandLine -match 'vast-tunnel|18100:127.0.0.1:18000' | % { Stop-Process -Id $_.ProcessId -Force }
param([string]$HostName = "99.148.65.9", [int]$Port = 18609, [int]$LocalPort = 18100)
while ($true) {
    ssh -i "$env:USERPROFILE\.ssh\vastai_ed25519" -p $Port -N -L "127.0.0.1:${LocalPort}:127.0.0.1:18000" `
        -o ServerAliveInterval=15 -o ServerAliveCountMax=3 -o ExitOnForwardFailure=yes -o BatchMode=yes `
        -o StrictHostKeyChecking=accept-new "root@$HostName"
    Start-Sleep -Seconds 5
}

# Information Frontier Launcher Script
# Auto-start backend and frontend, clean up old processes on exit

$ErrorActionPreference = "Stop"

# Config
$BackendPort = 8472
$FrontendPort = 5175
$CondaEnv = "ifrontier"
$BackendDir = "e:\GitClone\Demo\backend\src"
$FrontendDir = "e:\GitClone\Demo\frontend"

# Store child processes for cleanup
$global:ChildProcesses = @()

function Write-Header {
    param([string]$text)
    Write-Host "`n========================================" -ForegroundColor Cyan
    Write-Host $text -ForegroundColor Cyan
    Write-Host "========================================`n" -ForegroundColor Cyan
}

function Write-Info {
    param([string]$text)
    Write-Host "[INFO] $text" -ForegroundColor Green
}

function Write-Warn {
    param([string]$text)
    Write-Host "[WARN] $text" -ForegroundColor Yellow
}

function Write-Err {
    param([string]$text)
    Write-Host "[ERROR] $text" -ForegroundColor Red
}

# Kill process on specific port
function Kill-PortProcess {
    param([int]$port)
    try {
        $connections = Get-NetTCPConnection -LocalPort $port -ErrorAction SilentlyContinue | Where-Object { $_.State -eq "Listen" }
        if ($connections) {
            foreach ($conn in $connections) {
                try {
                    $proc = Get-Process -Id $conn.OwningProcess -ErrorAction SilentlyContinue
                    if ($proc) {
                        Write-Warn "Port $port occupied by: $($proc.ProcessName) (PID: $($proc.Id))"
                        Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
                    }
                } catch {}
            }
        }
    } catch {}
}

# Kill old game processes
function Kill-OldGameProcesses {
    Write-Header "Cleaning old processes"
    
    Kill-PortProcess -port $BackendPort
    Kill-PortProcess -port $FrontendPort
    
    # Quick kill by port is usually enough, skip process enumeration
}

# Start backend (no wait, fire and forget)
function Start-Backend {
    Write-Info "Starting backend (Port: $BackendPort)..."
    
    $procArgs = @("-NoExit", "-Command", "cd '$BackendDir'; `$env:PYTHONPATH='$BackendDir'; conda activate $CondaEnv; Write-Host 'Backend starting...' -ForegroundColor Green; uvicorn ifrontier.app.main:app --reload --port $BackendPort --app-dir .")
    
    try {
        $proc = Start-Process -FilePath "powershell" -ArgumentList $procArgs -PassThru
        $global:ChildProcesses += $proc
        Write-Info "Backend started (PID: $($proc.Id))"
        return $true
    } catch {
        Write-Err "Failed to start backend: $_"
        return $false
    }
}

# Start frontend (no wait)
function Start-Frontend {
    Write-Info "Starting frontend..."
    
    $procArgs = @("-NoExit", "-Command", "cd '$FrontendDir'; npm run dev")
    
    try {
        $proc = Start-Process -FilePath "powershell" -ArgumentList $procArgs -PassThru
        $global:ChildProcesses += $proc
        Write-Info "Frontend started (PID: $($proc.Id))"
        return $true
    } catch {
        Write-Err "Failed to start frontend: $_"
        return $false
    }
}

# Cleanup function
function Cleanup {
    Write-Header "Cleaning up processes"
    
    foreach ($proc in $global:ChildProcesses) {
        try {
            if ($proc -and -not $proc.HasExited) {
                Write-Warn "Killing child process PID: $($proc.Id)"
                Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
            }
        } catch {
            Write-Warn "Error cleaning process $($proc.Id): $_"
        }
    }
    
    Write-Info "Cleanup done"
}

# Register exit handler
try {
    Register-EngineEvent -SourceIdentifier PowerShell.Exiting -Action { Cleanup } -ErrorAction SilentlyContinue | Out-Null
} catch {}

# Main logic
function Main {
    Write-Header "Information Frontier Launcher"
    
    # Step 1: Quick clean
    Kill-OldGameProcesses
    
    # Step 2: Start both in parallel (fire and forget)
    Start-Backend
    Start-Frontend
    
    Write-Header "Services starting..."
    Write-Info "Backend: http://127.0.0.1:$BackendPort"
    Write-Info "Frontend: http://localhost:$FrontendPort"
    Write-Info "Close this window to stop all services`n"
    
    # Keep script running
    try {
        while ($true) {
            Start-Sleep -Seconds 5
            
            # Check if children still running
            $allExited = $true
            foreach ($proc in $global:ChildProcesses) {
                if ($proc -and -not $proc.HasExited) {
                    $allExited = $false
                    break
                }
            }
            
            if ($allExited -and $global:ChildProcesses.Count -gt 0) {
                Write-Warn "All child processes exited"
                break
            }
        }
    } finally {
        Cleanup
    }
}

# Run main
try {
    Main
} catch {
    Write-Err "Error: $_"
    Cleanup
    exit 1
}

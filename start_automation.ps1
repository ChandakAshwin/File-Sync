# Box File Sync - Quick Start Script
# This script starts all required services and automation in the correct order

Write-Output "Starting Box File Synchronization System..."
Write-Output ""

# Step 1: Start WSL services
Write-Output "Step 1: Starting required services in WSL..."
wsl sudo service postgresql start
Start-Sleep 2

wsl sudo service redis-server start
Start-Sleep 2  

wsl sudo service elasticsearch start
Start-Sleep 3

# Verify services started
Write-Output "Checking service status..."
$pgStatus = wsl sudo service postgresql status
$redisStatus = wsl sudo service redis-server status
$esStatus = wsl sudo service elasticsearch status

if ($pgStatus -match "online" -or $pgStatus -match "active") {
    Write-Output "PostgreSQL: Running"
} else {
    Write-Output "PostgreSQL: Failed to start"
    exit 1
}

if ($redisStatus -match "running" -or $redisStatus -match "active") {
    Write-Output "Redis: Running"
} else {
    Write-Output "Redis: Failed to start" 
    exit 1
}

if ($esStatus -match "running" -or $esStatus -match "active") {
    Write-Output "Elasticsearch: Running"
} else {
    Write-Output "Elasticsearch: Failed to start"
    exit 1
}

Write-Output ""

# Step 2: Auto-detect WSL IP for Redis (like the working fileSync project)
Write-Output "Step 2: Auto-detecting WSL IP for Redis connection..."
$wslIP = (wsl hostname -I).Trim()
Write-Output "WSL IP detected: $wslIP"

$redisUrl = "redis://${wslIP}:6379/0"
Write-Output "Using Redis URL: $redisUrl"

# Update Redis configuration in OAuth files (like working project)
$workerContent = Get-Content "automated_worker_oauth.py" -Raw
$workerContent = $workerContent -replace "redis://[^']*:6379/0", $redisUrl
$workerContent | Set-Content "automated_worker_oauth.py"

$beatContent = Get-Content "automated_beat_oauth.py" -Raw  
$beatContent = $beatContent -replace "redis://[^']*:6379/0", $redisUrl
$beatContent | Set-Content "automated_beat_oauth.py"

Write-Output "Redis configuration updated successfully"

# Step 3: Navigate to project directory
Set-Location "C:\Users\Dell\Desktop\local\WokeloFileSync"

# Step 4: Stop any existing jobs
Write-Output "Step 5: Cleaning up any existing automation jobs..."
Stop-Job -Name Worker, Scheduler -ErrorAction SilentlyContinue
Remove-Job -Name Worker, Scheduler -ErrorAction SilentlyContinue

# Step 4: Start automation
Write-Output "Step 6: Starting Box automation..."

Start-Job -Name Worker -ScriptBlock {
    Set-Location "C:\Users\Dell\Desktop\local\WokeloFileSync"
    python automated_worker_oauth.py
}

Start-Sleep 2

Start-Job -Name Scheduler -ScriptBlock {
    Set-Location "C:\Users\Dell\Desktop\local\WokeloFileSync"
    python automated_beat_oauth.py
}

# Step 5: Wait and verify
Write-Output "Step 7: Verifying automation started..."
Start-Sleep 5

$jobs = Get-Job
$workerState = ($jobs | Where-Object Name -eq "Worker").State
$schedulerState = ($jobs | Where-Object Name -eq "Scheduler").State

if ($workerState -eq "Running") {
    Write-Output "Worker: Running"
} else {
    Write-Output "Worker: $workerState"
}

if ($schedulerState -eq "Running") {
    Write-Output "Scheduler: Running"
} else {
    Write-Output "Scheduler: $schedulerState"
}

Write-Output ""
Write-Output "Box File Synchronization System Started!"
Write-Output ""
Write-Output "What is running:"
Write-Output "  - File sync every 2 minutes"
Write-Output "  - Cleanup check every 5 minutes" 
Write-Output "  - Automatic OAuth token refresh"
Write-Output ""
Write-Output "To monitor activity, run:"
Write-Output "  Receive-Job -Name Worker -Keep | Select-Object -Last 10"
Write-Output ""
Write-Output "To stop automation, run:"
Write-Output "  Stop-Job -Name Worker, Scheduler; Remove-Job -Name Worker, Scheduler"

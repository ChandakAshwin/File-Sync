# Box File Sync - Stop Automation Script
# This script safely stops all running automation jobs

Write-Output "🛑 Stopping Box File Synchronization System..."
Write-Output ""

# Check current job status
$jobs = Get-Job -ErrorAction SilentlyContinue

if ($jobs) {
    Write-Output "Current running jobs:"
    $jobs | Format-Table Name, State -AutoSize
    
    # Stop all jobs
    Write-Output "Stopping automation jobs..."
    Stop-Job -Name Worker, Scheduler -ErrorAction SilentlyContinue
    
    # Wait a moment for graceful shutdown
    Start-Sleep 3
    
    # Remove completed jobs
    Remove-Job -Name Worker, Scheduler -ErrorAction SilentlyContinue
    
    Write-Output "✅ All automation jobs stopped successfully"
} else {
    Write-Output "ℹ️  No automation jobs were running"
}

Write-Output ""
Write-Output "📋 What was stopped:"
Write-Output "  • File synchronization (every 2 minutes)"
Write-Output "  • Cleanup tasks (every 5 minutes)"
Write-Output ""
Write-Output "Note: WSL services (PostgreSQL, Redis, Elasticsearch) are still running"
Write-Output "      These services can continue running in the background"
Write-Output ""
Write-Output "🚀 To restart automation, run: start_automation.ps1"
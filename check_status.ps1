# Box File Sync - System Status Checker
# This script provides a comprehensive status overview of your automation system

Write-Output "📊 Box File Synchronization - System Status Dashboard"
Write-Output "=" * 60
Write-Output ""

# Check Celery Jobs
Write-Output "🤖 AUTOMATION STATUS:"
$jobs = Get-Job -ErrorAction SilentlyContinue
if ($jobs) {
    $jobs | Format-Table Name, State, HasMoreData -AutoSize
    
    # Show recent worker activity
    $workerJob = $jobs | Where-Object Name -eq "Worker"
    if ($workerJob -and $workerJob.State -eq "Running") {
        Write-Output "Recent Worker Activity (last 5 messages):"
        Receive-Job -Name Worker -Keep | Select-Object -Last 5 | ForEach-Object {
            Write-Output "  $_"
        }
        Write-Output ""
    }
} else {
    Write-Output "❌ No automation jobs running"
    Write-Output "   Run 'start_automation.ps1' to start the system"
    Write-Output ""
}

# Check WSL Services
Write-Output "🛠️  WSL SERVICES:"
try {
    $pgStatus = wsl sudo service postgresql status 2>$null
    if ($pgStatus -match "online|active|running") {
        Write-Output "✅ PostgreSQL: Running"
    } else {
        Write-Output "❌ PostgreSQL: Stopped"
    }
} catch {
    Write-Output "❓ PostgreSQL: Cannot check status"
}

try {
    $redisStatus = wsl sudo service redis-server status 2>$null
    if ($redisStatus -match "running|active") {
        Write-Output "✅ Redis: Running"
    } else {
        Write-Output "❌ Redis: Stopped"
    }
} catch {
    Write-Output "❓ Redis: Cannot check status"
}

try {
    $esStatus = wsl sudo service elasticsearch status 2>$null
    if ($esStatus -match "running|active") {
        Write-Output "✅ Elasticsearch: Running"
    } else {
        Write-Output "❌ Elasticsearch: Stopped"
    }
} catch {
    Write-Output "❓ Elasticsearch: Cannot check status"
}

Write-Output ""

# Check File Counts
Write-Output "📁 FILE STATUS:"
try {
    $localFiles = Get-ChildItem "documents\box" -File -ErrorAction SilentlyContinue
    $localCount = if ($localFiles) { $localFiles.Count } else { 0 }
    Write-Output "📄 Local Files: $localCount"
    
    if ($localCount -gt 0) {
        Write-Output "   Most recent: $($localFiles | Sort-Object LastWriteTime -Descending | Select-Object -First 1 | ForEach-Object { "$($_.Name) ($($_.LastWriteTime.ToString('yyyy-MM-dd HH:mm')))" })"
    }
} catch {
    Write-Output "📄 Local Files: Cannot access directory"
}

# Check Database
Write-Output ""
Write-Output "💾 DATABASE STATUS:"
try {
    $dbCount = wsl psql postgresql://filesync:password@127.0.0.1:5432/filesync -c "SELECT COUNT(*) FROM document;" -t -A 2>$null
    if ($dbCount -match "^\d+$") {
        Write-Output "📊 Database Records: $dbCount"
        
        # Get recent document
        $recentDoc = wsl psql postgresql://filesync:password@127.0.0.1:5432/filesync -c "SELECT title FROM document ORDER BY created_at DESC LIMIT 1;" -t -A 2>$null
        if ($recentDoc -and $recentDoc.Trim()) {
            Write-Output "   Most recent: $($recentDoc.Trim())"
        }
    } else {
        Write-Output "❌ Database: Connection failed"
    }
} catch {
    Write-Output "❌ Database: Cannot connect"
}

# Check Elasticsearch
Write-Output ""
Write-Output "🔍 SEARCH INDEX STATUS:"
try {
    $esResponse = Invoke-RestMethod http://172.27.64.1:9200/documents/_count -TimeoutSec 5 2>$null
    if ($esResponse.count -ne $null) {
        Write-Output "🔍 Indexed Documents: $($esResponse.count)"
        
        # Get a sample document title
        $sampleDoc = Invoke-RestMethod http://172.27.64.1:9200/documents/_search -Method Post -ContentType "application/json" -Body '{"query": {"match_all": {}}, "size": 1}' -TimeoutSec 5 2>$null
        if ($sampleDoc.hits.hits.Count -gt 0) {
            Write-Output "   Sample document: $($sampleDoc.hits.hits[0]._source.title)"
        }
    } else {
        Write-Output "❌ Elasticsearch: No response"
    }
} catch {
    Write-Output "❌ Elasticsearch: Cannot connect (check if service is running)"
}

# Check OAuth Status
Write-Output ""
Write-Output "🔐 OAUTH STATUS:"
try {
    $oauthResult = python -c "from box_token_manager import BoxTokenManager; print('✅ OAuth: Working' if BoxTokenManager().test_connection() else '❌ OAuth: Failed')" 2>$null
    if ($oauthResult) {
        Write-Output $oauthResult
    } else {
        Write-Output "❓ OAuth: Cannot test (check if token_manager.py exists)"
    }
} catch {
    Write-Output "❓ OAuth: Cannot test connection"
}

Write-Output ""
Write-Output "=" * 60

# System recommendations
$issues = @()
if (-not $jobs -or $jobs.Count -eq 0) {
    $issues += "Automation not running"
}
if ($jobs | Where-Object { $_.State -eq "Failed" -or $_.State -eq "Completed" }) {
    $issues += "Some jobs have stopped"  
}

if ($issues.Count -gt 0) {
    Write-Output ""
    Write-Output "⚠️  RECOMMENDATIONS:"
    foreach ($issue in $issues) {
        Write-Output "   • $issue - Run 'start_automation.ps1' to fix"
    }
} else {
    Write-Output "✅ System appears to be running normally!"
}

Write-Output ""
Write-Output "🔄 Data sync runs every 2 minutes • Cleanup every 5 minutes"
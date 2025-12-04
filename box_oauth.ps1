# Box OAuth helper for WokeloFileSync
# Usage:
# 1) Ensure the API server is running in another terminal:
#      .\.venv\Scripts\Activate.ps1
#      python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
# 2) Run this script (in a new PowerShell window in the project folder):
#      pwsh -NoProfile -File .\box_oauth.ps1
#    If your execution policy blocks the script:
#      powershell -NoProfile -ExecutionPolicy Bypass -File .\box_oauth.ps1

$ErrorActionPreference = "Stop"
$ApiBaseUrl = "http://127.0.0.1:8000"

function Get-AuthUrl {
  try {
Write-Host "Starting OAuth flow..." -ForegroundColor Cyan
    $auth = Invoke-RestMethod -Uri "$ApiBaseUrl/auth/box/start" -Method GET
    if (-not $auth -or -not $auth.redirect_url) {
      throw "API did not return a redirect_url"
    }
    return $auth.redirect_url
  }
  catch {
    Write-Host "Failed to start OAuth. Is the API server running on $ApiBaseUrl?" -ForegroundColor Red
    Write-Host "Start it in another terminal:"
    Write-Host ".\\.venv\\Scripts\\Activate.ps1" -ForegroundColor Yellow
    Write-Host "python -m uvicorn app.main:app --host 127.0.0.1 --port 8000" -ForegroundColor Yellow
    throw
  }
}

function Parse-QueryString($uri) {
  $result = @{}
  try {
    $u = [System.Uri]$uri
  }
  catch {
    throw "Invalid URL pasted. Please paste the full redirect URL as shown in your browser."
  }
  $qs = $u.Query.TrimStart('?')
  if ([string]::IsNullOrWhiteSpace($qs)) { return $result }
  $pairs = $qs -split '&' | Where-Object { $_ }
  foreach ($p in $pairs) {
    $kv = $p -split '=', 2
    $k = if ($kv.Count -ge 1) { [System.Net.WebUtility]::UrlDecode($kv[0]) } else { '' }
    $v = if ($kv.Count -ge 2) { [System.Net.WebUtility]::UrlDecode($kv[1]) } else { '' }
    if ($k) { $result[$k] = $v }
  }
  return $result
}

try {
  # 1) Get Box authorization URL from API and open it
  $authorizeUrl = Get-AuthUrl
Write-Host "Opening Box consent page in your browser..." -ForegroundColor Cyan
  Write-Host $authorizeUrl -ForegroundColor DarkGray
  try { Start-Process $authorizeUrl } catch { Write-Host "Could not auto-open the browser. Copy the URL above and open it manually." -ForegroundColor Yellow }
  Write-Host "Note: You have ~10 minutes to complete authorization before the state expires." -ForegroundColor DarkYellow

  # 2) Prompt user to paste the redirect URL after consenting
  $redirect = Read-Host "Paste the FULL redirect URL (http://127.0.0.1:8000/auth/box/callback?code=...&state=...)"
  $parsed = Parse-QueryString $redirect
  $code  = $parsed['code']
  $state = $parsed['state']
  if (-not $code -or -not $state) {
    throw "Missing code or state in the URL. Restart the script to generate a fresh OAuth state."
  }

  # 3) Call API callback to exchange code for tokens
  $cbUrl = "$ApiBaseUrl/auth/box/callback?code=$([uri]::EscapeDataString($code))&state=$([uri]::EscapeDataString($state))"
Write-Host "Completing OAuth with API..." -ForegroundColor Cyan
  $resp = Invoke-RestMethod -Uri $cbUrl -Method GET

  if ($resp -and $resp.credential_id) {
    Write-Host ("Success. Credential ID: {0}" -f $resp.credential_id) -ForegroundColor Green
    if ($resp.redirect_url) {
      Write-Host ("Redirect URL: {0}" -f $resp.redirect_url) -ForegroundColor DarkGray
    }
  }
  else {
    Write-Host "OAuth completed, but response did not include a credential_id:" -ForegroundColor Yellow
    $resp | ConvertTo-Json -Depth 5 | Write-Host
  }
}
catch {
  Write-Host ("Error: {0}" -f $_.Exception.Message) -ForegroundColor Red
  exit 1
}

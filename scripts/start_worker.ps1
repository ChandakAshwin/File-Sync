param()
$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

if (-not (Test-Path "$root\venv")) {
  py -3 -m venv venv
}
. "$root\venv\Scripts\Activate.ps1"

pip install -r requirements.txt

$env:PYTHONPATH = $root
celery -A workers.celery_worker_functional worker --loglevel=info --concurrency=1

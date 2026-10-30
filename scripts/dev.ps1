# Local Development Startup Script for Windows PowerShell
Write-Host "Starting Mega-Project services locally..." -ForegroundColor Cyan

# Ensure upload directory exists
$uploadDir = Join-Path $PSScriptRoot "..\uploads"
if (-not (Test-Path $uploadDir)) {
    New-Item -ItemType Directory -Path $uploadDir | Out-Null
}

# Start ML-Service in background job
Write-Host "Starting ML-Service on port 8001..." -ForegroundColor Yellow
$mlJob = Start-Job -ScriptBlock {
    param($root)
    Set-Location (Join-Path $root "..\ml-service")
    python -m uvicorn main:app --host 0.0.0.0 --port 8001
} -ArgumentList $PSScriptRoot

# Start Backend in background job
Write-Host "Starting Backend on port 8000..." -ForegroundColor Yellow
$backendJob = Start-Job -ScriptBlock {
    param($root)
    Set-Location (Join-Path $root "..\backend")
    python -m uvicorn main:app --host 0.0.0.0 --port 8000
} -ArgumentList $PSScriptRoot

Start-Sleep -Seconds 3

Write-Host "Services started!" -ForegroundColor Green
Write-Host "Backend API: http://localhost:8000/api"
Write-Host "Backend UI:  http://localhost:8000/ui"
Write-Host "ML-Service:  http://localhost:8001/api/health"
Write-Host "Press Ctrl+C to stop all background jobs."

try {
    while ($true) {
        Start-Sleep -Seconds 2
    }
} finally {
    Write-Host "Stopping services..." -ForegroundColor Red
    Stop-Job $mlJob, $backendJob -ErrorAction SilentlyContinue
    Remove-Job $mlJob, $backendJob -ErrorAction SilentlyContinue
}

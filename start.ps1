# Start AI Trading Arena backend + frontend
# Backend: Python uvicorn on port 7077
# Frontend: Next.js dev server on port 7078

$root = $PSScriptRoot

Write-Host "Starting AI Trading Arena backend on port 7077..." -ForegroundColor Cyan
Start-Process -NoNewWindow -FilePath "python" `
    -ArgumentList "-m", "uvicorn", "backend.app:app", "--host", "0.0.0.0", "--port", "7077" `
    -WorkingDirectory $root

Write-Host "Starting AI Trading Arena frontend on port 7078..." -ForegroundColor Cyan
$frontendDir = Join-Path $root "frontend"
if (Test-Path $frontendDir) {
    Start-Process -NoNewWindow -FilePath "npm" `
        -ArgumentList "run", "dev" `
        -WorkingDirectory $frontendDir
} else {
    Write-Host "frontend/ not yet present, skipping frontend start." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "Backend  -> http://localhost:7077" -ForegroundColor Green
Write-Host "Frontend -> http://localhost:7078" -ForegroundColor Green
Write-Host "Health   -> http://localhost:7077/health" -ForegroundColor Green

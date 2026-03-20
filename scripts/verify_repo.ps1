\
# ECE496 verifier (PowerShell)
# Usage:
#   .\scripts\verify_repo.ps1
#   .\scripts\verify_repo.ps1 -Full
#   .\scripts\verify_repo.ps1 -Full -RunBuild

param(
  [switch]$Full,
  [switch]$RunBuild
)

$repoRoot = Split-Path -Parent $PSScriptRoot

Write-Host "ECE496 verify starting..." -ForegroundColor Cyan
Write-Host "Repo root: $repoRoot"

$python = "py"
if (-not (Get-Command $python -ErrorAction SilentlyContinue)) {
  $python = "python"
}

$args = @("$repoRoot\scripts\verify_repo.py")
if ($Full) { $args += "--full" }
if ($RunBuild) { $args += "--run-build" }

& $python @args
exit $LASTEXITCODE

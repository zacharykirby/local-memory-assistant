# Memoria launcher for Windows: run from repo root (e.g. via Windows Terminal).
# Activates venv and runs python src/chat.py. Vault path comes from .env in repo.

$ErrorActionPreference = "Stop"

# Repo root = parent of launcher directory (where this script lives)
$LauncherDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Split-Path -Parent $LauncherDir
Set-Location $RepoRoot

$EnvFile = Join-Path $RepoRoot ".env"
$VenvPython = Join-Path $RepoRoot "venv\Scripts\python.exe"

# ---- First-run check: vault path from .env ----
function Test-VaultConfig {
    if (-not (Test-Path $EnvFile)) {
        Write-Host "Warning: No .env found. Copy .env.example to .env and set OBSIDIAN_PATH." -ForegroundColor Yellow
        return $false
    }
    $content = Get-Content $EnvFile -Raw
    if ($content -match 'OBSIDIAN_PATH=(.+)') {
        $path = $matches[1].Trim().Trim('"').Trim("'")
        if ([string]::IsNullOrWhiteSpace($path)) {
            Write-Host "Warning: OBSIDIAN_PATH not set in .env." -ForegroundColor Yellow
            return $false
        }
        if (-not (Test-Path -LiteralPath $path -PathType Container)) {
            Write-Host "Warning: Vault path does not exist: $path" -ForegroundColor Yellow
            return $false
        }
        $obsidianFolder = Join-Path $path ".obsidian"
        if (-not (Test-Path -LiteralPath $obsidianFolder -PathType Container)) {
            Write-Host "Warning: Obsidian vault folder not detected (no .obsidian in vault)." -ForegroundColor Yellow
        }
        return $true
    }
    Write-Host "Warning: OBSIDIAN_PATH not set in .env." -ForegroundColor Yellow
    return $false
}

if (-not (Test-VaultConfig)) {
    $continue = Read-Host "Fix .env and OBSIDIAN_PATH, then run Memoria again. Continue anyway? [y/N]"
    if ($continue -notmatch '^[yY]') { exit 1 }
}

# ---- Run Memoria ----
if (-not (Test-Path -LiteralPath $VenvPython)) {
    Write-Host "Error: venv not found. Run: python -m venv venv; pip install -r requirements.txt" -ForegroundColor Red
    exit 1
}

& $VenvPython src/chat.py @args

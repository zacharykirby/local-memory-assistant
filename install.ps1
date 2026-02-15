# Install Memoria launcher on Windows 11: shortcut to run AutoHotkey script (hotkey Ctrl+Alt+M).
# Run from repo root. Vault path is read from .env (single config for both platforms).
# Requires: AutoHotkey v1.1+, Windows Terminal (wt.exe).

$ErrorActionPreference = "Stop"

$RepoRoot = if ($PSScriptRoot) { $PSScriptRoot } else { (Get-Location).Path }
$LauncherDir = Join-Path $RepoRoot "launcher"
$EnvFile = Join-Path $RepoRoot ".env"
$EnvExample = Join-Path $RepoRoot ".env.example"

Write-Host "Memoria launcher install (Windows)"
Write-Host "Repo: $RepoRoot"
Write-Host ""

# Ensure .env exists
if (-not (Test-Path $EnvFile)) {
    if (Test-Path $EnvExample) {
        Write-Host "No .env found. Copying .env.example to .env — please set OBSIDIAN_PATH."
        Copy-Item $EnvExample $EnvFile
    } else {
        Write-Host "Error: No .env or .env.example in repo." -ForegroundColor Red
        exit 1
    }
}

# First-run check: vault path
if (Test-Path $EnvFile) {
    $content = Get-Content $EnvFile -Raw
    if ($content -match 'OBSIDIAN_PATH=(.+)') {
        $path = $matches[1].Trim().Trim('"').Trim("'")
        if ([string]::IsNullOrWhiteSpace($path) -or $path -eq "/path/to/your/obsidian/vault") {
            Write-Host "Warning: OBSIDIAN_PATH is not set or still the placeholder in .env." -ForegroundColor Yellow
            Write-Host "  Edit $EnvFile and set OBSIDIAN_PATH to your Obsidian vault path."
        } else {
            if (-not (Test-Path -LiteralPath $path -PathType Container)) {
                Write-Host "Warning: Vault path does not exist: $path" -ForegroundColor Yellow
            } elseif (-not (Test-Path -LiteralPath (Join-Path $path ".obsidian") -PathType Container)) {
                Write-Host "Warning: Obsidian vault folder not detected (no .obsidian in vault)." -ForegroundColor Yellow
            }
        }
    }
}

# Find AutoHotkey
$ahkExe = $null
$paths = @(
    "$env:ProgramFiles\AutoHotkey\AutoHotkey.exe",
    "${env:ProgramFiles(x86)}\AutoHotkey\AutoHotkey.exe",
    "$env:LOCALAPPDATA\Programs\AutoHotkey\AutoHotkey.exe"
)
foreach ($p in $paths) {
    if (Test-Path $p) { $ahkExe = $p; break }
}
if (-not $ahkExe) {
    Write-Host "AutoHotkey not found. Install from https://www.autohotkey.com/ and run install again." -ForegroundColor Yellow
    Write-Host "You can still run Memoria from a terminal: cd repo; .\venv\Scripts\Activate.ps1; python src\chat.py"
}

# Create shortcut: Desktop + Start Menu (run AHK script for global hotkey Ctrl+Alt+M)
$ahkScript = Join-Path $LauncherDir "memoria.ahk"
$WshShell = New-Object -ComObject WScript.Shell

if ($ahkExe) {
    $shortcutDir = [Environment]::GetFolderPath("Desktop")
    $shortcutPath = Join-Path $shortcutDir "Memoria.lnk"
    $shortcut = $WshShell.CreateShortcut($shortcutPath)
    $shortcut.TargetPath = $ahkExe
    $shortcut.Arguments = "`"$ahkScript`""
    $shortcut.WorkingDirectory = $RepoRoot
    $shortcut.Description = "Memoria launcher (Ctrl+Alt+M opens session)"
    $shortcut.Save()
    Write-Host "Shortcut created: $shortcutPath"

    $startMenu = [Environment]::GetFolderPath("StartMenu")
    $programs = Join-Path $startMenu "Programs"
    $memoriaFolder = Join-Path $programs "Memoria"
    if (-not (Test-Path $memoriaFolder)) { New-Item -ItemType Directory -Path $memoriaFolder -Force | Out-Null }
    $startShortcut = Join-Path $memoriaFolder "Memoria.lnk"
    $sc = $WshShell.CreateShortcut($startShortcut)
    $sc.TargetPath = $ahkExe
    $sc.Arguments = "`"$ahkScript`""
    $sc.WorkingDirectory = $RepoRoot
    $sc.Description = "Memoria launcher (Ctrl+Alt+M opens session)"
    $sc.Save()
    Write-Host "Start Menu shortcut: $startShortcut"
}

Write-Host ""
Write-Host "Done. Double-click the shortcut (or run memoria.ahk) so the hotkey is active."
Write-Host "Then press Ctrl+Alt+M anywhere to open a Memoria session in Windows Terminal."
Write-Host "Optional: add the shortcut to Startup for hotkey at login."

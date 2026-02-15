; Memoria launcher for Windows 11
; Requires: AutoHotkey v1.1+, Windows Terminal (wt.exe)
; Hotkey: Ctrl+Alt+M — globally opens Windows Terminal running Memoria (venv + python src/chat.py)
; Run this script at startup (or via shortcut) for one-keypress access.

#NoTrayIcon
#SingleInstance Ignore

; Repo root = parent of directory containing this script
ScriptDir := A_ScriptDir
RepoRoot := RegExReplace(ScriptDir, "\\launcher$", "")

; Windows Terminal: start in repo, run PowerShell launcher
RunMemo() {
    global RepoRoot
    RunScript := RepoRoot . "\launcher\run_memoria.ps1"
    ; wt -d = start in directory, then run PowerShell
    Run wt -d "`"" . RepoRoot . "`"" powershell.exe -NoProfile -ExecutionPolicy Bypass -File "`"" . RunScript . "`""
}

^!m::RunMemo()

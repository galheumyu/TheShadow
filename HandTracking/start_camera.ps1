$ErrorActionPreference = 'Stop'
# Resolve everything relative to this module, including paths containing spaces.
& (Join-Path $PSScriptRoot 'setup_python.ps1')
& (Join-Path $PSScriptRoot '.venv\Scripts\python.exe') (Join-Path $PSScriptRoot 'tracker\hand_distance.py') @args
if ($LASTEXITCODE -ne 0) { throw 'Camera tracker stopped with an error. Read the message above.' }

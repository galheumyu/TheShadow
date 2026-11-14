$ErrorActionPreference = 'Stop'
# Test UDP and colors without installing camera packages or downloading a model.
& (Join-Path $PSScriptRoot 'setup_python.ps1') -SkipDependencies
& (Join-Path $PSScriptRoot '.venv\Scripts\python.exe') (Join-Path $PSScriptRoot 'tracker\hand_distance.py') --simulate @args
if ($LASTEXITCODE -ne 0) { throw 'Simulation stopped with an error.' }

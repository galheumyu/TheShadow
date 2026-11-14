param([switch]$SkipDependencies)
$ErrorActionPreference = 'Stop'
$environmentPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'

# Build a machine-local environment; never depend on another checkout's paths.
if (-not (Test-Path -LiteralPath $environmentPython)) {
    $pythonCommand = $null
    $pythonArguments = @()
    # Also check standard install locations when Explorer has an older PATH.
    $pythonCandidates = @('py', 'python', 'python3', (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python311\python.exe'), (Join-Path $env:ProgramFiles 'Python311\python.exe'))
    foreach ($candidate in $pythonCandidates) {
        if (-not (Get-Command $candidate -ErrorAction SilentlyContinue)) { continue }
        $candidateArguments = @()
        if ($candidate -eq 'py') { $candidateArguments = @('-3.11') }
        # Avoid embedded quotes: Windows PowerShell 5.1 can strip them in native arguments.
        try {
            $version = & $candidate @candidateArguments -c 'import sys; print(sys.version_info.major * 100 + sys.version_info.minor)' 2>$null
        } catch { continue }
        if ($LASTEXITCODE -eq 0 -and "$version".Trim() -eq '311') {
            $pythonCommand = $candidate
            $pythonArguments = $candidateArguments
            break
        }
    }
    if (-not $pythonCommand) {
        throw 'Install Python 3.11 (64-bit) from python.org, enable Add Python to PATH, then run this launcher again.'
    }
    Write-Host 'Creating local Python environment...'
    & $pythonCommand @pythonArguments -m venv (Join-Path $PSScriptRoot '.venv')
    if ($LASTEXITCODE -ne 0) { throw 'Could not create the Python environment.' }
}

# Simulation uses only the standard library; no camera packages are needed.
if (-not $SkipDependencies) {
    $requirements = Join-Path $PSScriptRoot 'tracker\requirements.txt'
    $marker = Join-Path $PSScriptRoot '.venv\handtracking-requirements.sha256'
    $expectedHash = (Get-FileHash -LiteralPath $requirements -Algorithm SHA256).Hash
    $installedHash = ''
    if (Test-Path -LiteralPath $marker) { $installedHash = (Get-Content -LiteralPath $marker -Raw).Trim() }
    # Catch probe failures so a missing package triggers installation, not exit.
    try { & $environmentPython -c 'import cv2; import mediapipe' 2>$null } catch { }
    $importsWork = $LASTEXITCODE -eq 0
    if (-not $importsWork -or $installedHash -ne $expectedHash) {
        Write-Host 'Installing camera dependencies (first run requires Internet)...'
        & $environmentPython -m pip install -r $requirements
        if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed. Check your Internet connection and retry.' }
        & $environmentPython -c 'import cv2; import mediapipe'
        if ($LASTEXITCODE -ne 0) { throw 'Camera dependencies could not be loaded.' }
        Set-Content -LiteralPath $marker -Value $expectedHash
    }
}

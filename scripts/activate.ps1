# Dot-source from PowerShell: . .\scripts\activate.ps1
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONNOUSERSITE = "1"
$OutputEncoding = [System.Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = $OutputEncoding
$projectDirectory = Split-Path -Parent $PSScriptRoot
$projectPrefix = Join-Path $projectDirectory ".conda"
if (-not (Test-Path -LiteralPath (Join-Path $projectPrefix "python.exe"))) {
    throw "Missing project environment. See docs/local-setup.md."
}

$condaCommand = Get-Command conda -ErrorAction SilentlyContinue
$condaExecutable = if ($env:CONDA_EXE) {
    $env:CONDA_EXE
} elseif ($condaCommand -and $condaCommand.Source) {
    $condaCommand.Source
} elseif (Test-Path -LiteralPath "D:\Conda\Scripts\conda.exe") {
    "D:\Conda\Scripts\conda.exe"
} else {
    throw "Conda was not found. Open an Anaconda PowerShell Prompt and activate .\.conda."
}

# Initialize this terminal only; do not change the user's PowerShell profile or global PATH.
(& $condaExecutable "shell.powershell" "hook") | Out-String | Invoke-Expression
conda activate $projectPrefix
if ($LASTEXITCODE -ne 0) { throw "Could not activate the project Conda environment." }
Write-Host "EduMS: $projectPrefix"

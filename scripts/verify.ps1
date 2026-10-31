param(
    [string]$PythonCommand = "python"
)

$ErrorActionPreference = "Stop"

function Invoke-Checked {
    param([string[]]$Arguments)
    & $PythonCommand @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Validation command failed: $PythonCommand $($Arguments -join ' ')"
    }
}

Invoke-Checked @("-m", "pip", "check")
Invoke-Checked @("-m", "pytest", "-q", "--basetemp=.pytest-recon-verify", "-o", "cache_dir=.pytest-recon-cache")
Invoke-Checked @("-m", "ruff", "check", "src", "tests")
Invoke-Checked @("-m", "mypy", "src")

Write-Host "All validation gates passed." -ForegroundColor Green


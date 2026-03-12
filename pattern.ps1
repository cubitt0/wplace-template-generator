<#
.SYNOPSIS
    Generate random pattern images from PNG source files using Docker.

.DESCRIPTION
    PowerShell wrapper for the pattern generator Python script, run via Docker.

.EXAMPLE
    .\pattern.ps1 --preset las-igla --size 3000x2000

.EXAMPLE
    .\pattern.ps1 --all --size 3000x2000

.EXAMPLE
    .\pattern.ps1 --groups krzak kwiat --fill --size 3000x2000

.EXAMPLE
    .\pattern.ps1 --groups krzak kwiat lisc --fill --size 4000x3000 --priority lisc

.EXAMPLE
    .\pattern.ps1 --groups igla grzyb --size 2000x1500 --density 7 --spacing 20-60

.NOTES
    All arguments are passed through to the Python script inside Docker.
    Run: .\pattern.ps1 --help for full argument list.
#>

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$ImageName = "pattern-generator"

# Expand --all flag into --groups (excluding fill) + --fill
$DockerArgs = @()
foreach ($arg in $args) {
    if ($arg -eq "--all") {
        $DockerArgs += "--fill"
        $DockerArgs += "--groups"
        Get-ChildItem -Path $ScriptDir -Directory | ForEach-Object {
            $group = $_.Name
            # Skip hidden directories, the fill group, and presets directory
            if ($group -match "^\.") { return }
            if ($group -eq "fill") { return }
            if ($group -eq "presets") { return }
            $DockerArgs += $group
        }
    } else {
        $DockerArgs += $arg
    }
}

# Build Docker image if not already built (or if Dockerfile changed)
Write-Host "==> Ensuring Docker image '$ImageName' is up to date..."
docker build -q -t $ImageName $ScriptDir | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Error "Docker build failed."
    exit 1
}

Write-Host "==> Running pattern generator..."
docker run --rm `
    -v "${ScriptDir}:/patterns" `
    $ImageName @DockerArgs

if ($LASTEXITCODE -ne 0) {
    Write-Error "Pattern generation failed."
    exit 1
}

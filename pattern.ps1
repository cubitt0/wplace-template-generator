<#
.SYNOPSIS
    Generate random pattern images from PNG source files using Docker.

.DESCRIPTION
    PowerShell wrapper for the pattern generator Python script, run via Docker.

.EXAMPLE
    .\pattern.ps1 --preset forest-conifer --size 3000x2000

.EXAMPLE
    .\pattern.ps1 --all --size 3000x2000

.EXAMPLE
    .\pattern.ps1 --groups bush flower --fill --size 3000x2000

.EXAMPLE
    .\pattern.ps1 --groups bush flower leaf --fill --size 4000x3000 --priority leaf

.EXAMPLE
    .\pattern.ps1 --groups conifer shroom --size 2000x1500 --density 7 --spacing 20-60

.NOTES
    All arguments are passed through to the Python script inside Docker.
    Run: .\pattern.ps1 --help for full argument list.
#>

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$ImageName = "pattern-generator"

# Show help without requiring Docker
if ($args -contains "--help" -or $args -contains "-h") {
    @"
🌿 Pattern Generator — generate random pattern images from PNG source files

Usage:
  .\pattern.ps1 --size WIDTHxHEIGHT [OPTIONS]

Required:
  --size WIDTHxHEIGHT       Output image size (e.g. 3000x2000)

  At least one of --groups, --fill, or --preset must be provided.

Options:
  --groups GROUP [...]      Group names to include (bush flower leaf conifer shroom animals)
  --fill                    Enable fill group (placed last, ignores --repeats)
  --preset NAME             Load a preset from presets/<name>.json
  --all                     Use all group directories + fill (wrapper-only flag)
  --priority GROUP          Group that should appear more often
  --priority-weight N       Multiplier for priority group (default: 3)
  --spacing MIN-MAX         Pixel spacing between images (default: 30-80)
  --density N               How packed, 1-10 (default: 5)
  --repeats N               Max times a single PNG can appear (default: unlimited)
  --flip                    50% chance to flip each image horizontally
  --output FILE             Output filename (default: pattern_output.png)
  --seed N                  Fix random seed for reproducibility
  -h, --help                Show this help message

Available presets:
  forest-conifer            Dense conifer forest (conifer, bush, shroom)
  forest-leaf               Leafy forest (leaf, bush, flower)
  meadow                    Flower meadow (flower, bush)

Examples:
  .\pattern.ps1 --preset meadow --size 3000x2000
  .\pattern.ps1 --groups bush flower --fill --size 3000x2000
  .\pattern.ps1 --all --size 5000x3000
  .\pattern.ps1 --groups leaf bush --fill --size 4000x3000 --priority leaf --flip
"@
    exit 0
}

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

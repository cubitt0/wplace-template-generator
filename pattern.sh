#!/usr/bin/env bash
#
# pattern.sh - Generate random pattern images from PNG source files using Docker
#
# Usage:
#   ./pattern.sh --groups fill krzak kwiat --size 3000x2000
#   ./pattern.sh --groups fill krzak kwiat lisc --size 4000x3000 --priority lisc
#   ./pattern.sh --groups igla grzyb --size 2000x1500 --density 7 --spacing 20-60
#
# Parameters:
#   --groups          Group names to include (required), e.g. fill krzak kwiat lisc igla grzyb
#   --size            Output size as WIDTHxHEIGHT (required), e.g. 3000x2000
#   --priority        Group that should appear more often, e.g. lisc
#   --priority-weight How many times more the priority appears (default: 3)
#   --spacing         Min-max pixel spacing between images (default: 30-80)
#   --density         How packed, 1-10 (default: 5). Higher = more images
#   --output          Output filename (default: pattern_output.png)
#   --seed            Fix random seed for reproducibility (omit for random)
#
# All arguments are passed through to the Python script inside Docker.
# Run ./pattern.sh --help for full argument list.
#

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
IMAGE_NAME="pattern-generator"

# Build Docker image if not already built (or if Dockerfile changed)
echo "==> Ensuring Docker image '${IMAGE_NAME}' is up to date..."
docker build -q -t "${IMAGE_NAME}" "${SCRIPT_DIR}" > /dev/null

echo "==> Running pattern generator..."
docker run --rm \
    -v "${SCRIPT_DIR}:/patterns" \
    -u "$(id -u):$(id -g)" \
    "${IMAGE_NAME}" "$@"

#!/usr/bin/env bash
#
# pattern.sh - Generate random pattern images from PNG source files using Docker
#
# Usage:
#   ./pattern.sh --preset forest-conifer --size 3000x2000
#   ./pattern.sh --all --size 3000x2000
#   ./pattern.sh --groups bush flower --fill --size 3000x2000
#   ./pattern.sh --groups bush flower leaf --fill --size 4000x3000 --priority leaf
#   ./pattern.sh --groups conifer shroom --size 2000x1500 --density 7 --spacing 20-60
#
# Parameters:
#   --preset          Load a preset from presets/<name>.json (e.g. forest-conifer, forest-leaf, meadow)
#   --all             Use all group directories (adds --fill + all others as --groups)
#   --groups          Group names to include (e.g. bush flower leaf conifer shroom)
#   --fill            Enable fill group (placed last, ignores --repeats, uses spacing+density)
#   --size            Output size as WIDTHxHEIGHT (required), e.g. 3000x2000
#   --priority        Group that should appear more often, e.g. leaf
#   --priority-weight How many times more the priority appears (default: 3)
#   --spacing         Min-max pixel spacing between images (default: 30-80)
#   --density         How packed, 1-10 (default: 5). Higher = more images
#   --repeats         Max times a single PNG can appear on the result (default: unlimited, fill ignores this)
#   --output          Output filename (default: pattern_output.png)
#   --seed            Fix random seed for reproducibility (omit for random)
#
# All arguments are passed through to the Python script inside Docker.
# Run ./pattern.sh --help for full argument list.
#

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
IMAGE_NAME="pattern-generator"

# Show help without requiring Docker
for arg in "$@"; do
    if [[ "$arg" == "--help" || "$arg" == "-h" ]]; then
        cat <<'EOF'
🌿 Pattern Generator — generate random pattern images from PNG source files

Usage:
  ./pattern.sh --size WIDTHxHEIGHT [OPTIONS]

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
  ./pattern.sh --preset meadow --size 3000x2000
  ./pattern.sh --groups bush flower --fill --size 3000x2000
  ./pattern.sh --all --size 5000x3000
  ./pattern.sh --groups leaf bush --fill --size 4000x3000 --priority leaf --flip
EOF
        exit 0
    fi
done

# Expand --all flag into --groups (excluding fill) + --fill
ARGS=()
for arg in "$@"; do
    if [[ "$arg" == "--all" ]]; then
        ARGS+=("--fill")
        ARGS+=("--groups")
        for dir in "${SCRIPT_DIR}"/*/; do
            group="$(basename "$dir")"
            # Skip hidden directories, the fill group, and presets directory
            [[ "$group" == .* ]] && continue
            [[ "$group" == "fill" ]] && continue
            [[ "$group" == "presets" ]] && continue
            ARGS+=("$group")
        done
    else
        ARGS+=("$arg")
    fi
done

# Build Docker image if not already built (or if Dockerfile changed)
echo "==> Ensuring Docker image '${IMAGE_NAME}' is up to date..."
docker build -q -t "${IMAGE_NAME}" "${SCRIPT_DIR}" > /dev/null

echo "==> Running pattern generator..."
docker run --rm \
    -v "${SCRIPT_DIR}:/patterns" \
    -u "$(id -u):$(id -g)" \
    "${IMAGE_NAME}" "${ARGS[@]}"

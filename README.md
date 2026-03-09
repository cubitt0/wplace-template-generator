# Pattern Generator

Generate random pattern images by compositing PNG elements from categorized groups onto a transparent canvas. Elements are placed using pixel-level collision detection to prevent overlapping.

## Groups

Source images are organized into folders by type:

| Group   | Count | Description        |
|---------|-------|--------------------|
| `fill`  | 4     | Fill elements      |
| `grzyb` | 1     | Mushroom           |
| `igla`  | 5     | Needles            |
| `krzak` | 2     | Bushes             |
| `kwiat` | 51    | Flowers (multiple color variants) |
| `lisc`  | 4     | Leaves             |

## Quick Start

### Using Docker (recommended)

```bash
./pattern.sh --groups fill krzak kwiat --size 3000x2000
```

### Using Python directly

Requires Python 3.12+ and Pillow:

```bash
pip install Pillow
python generate_pattern.py --groups fill krzak kwiat --size 3000x2000
```

## Usage

```
python generate_pattern.py --groups GROUP [GROUP ...] --size WIDTHxHEIGHT [OPTIONS]
```

### Required Arguments

| Argument   | Description                           | Example           |
|------------|---------------------------------------|-------------------|
| `--groups` | Group names to include                | `fill krzak kwiat` |
| `--size`   | Output image size as WIDTHxHEIGHT     | `3000x2000`       |

### Optional Arguments

| Argument            | Default            | Description                                      |
|---------------------|--------------------|--------------------------------------------------|
| `--spacing`         | `30-80`            | Min-max random spacing in pixels between images   |
| `--priority`        | *(none)*           | Group name that should appear more often           |
| `--priority-weight` | `3`                | How many times more the priority group appears     |
| `--density`         | `5`                | How packed the images are (1–10)                   |
| `--output`          | `pattern_output.png` | Output filename                                  |
| `--seed`            | *(random)*         | Random seed for reproducibility                    |

## Examples

```bash
# Basic pattern with fill, bushes, and flowers
./pattern.sh --groups fill krzak kwiat --size 3000x2000

# Dense pattern with leaves prioritized
./pattern.sh --groups fill krzak kwiat lisc --size 4000x3000 --priority lisc --spacing 20-60

# Sparse pattern with needles and mushrooms
./pattern.sh --groups igla grzyb --size 2000x1500 --density 7

# Reproducible output with a fixed seed
./pattern.sh --groups fill kwiat --size 3000x2000 --seed 42
```

## Output

The generated image is saved as a transparent PNG (RGBA) to the specified output path.

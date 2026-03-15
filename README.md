# 🌿 Pattern Generator

Generate seamless, randomized pattern images by compositing PNG elements onto a transparent canvas.
Elements are placed using **pixel-level collision detection** with a coarse-grid acceleration, so nothing overlaps.

![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue)
![Docker](https://img.shields.io/badge/docker-ready-blue)

---

## 📂 Asset Groups

Source images live in folders by type. Mix and match them to create your pattern:

| Group | Count | Description |
|-------|------:|-------------|
| 🌲 `conifer` | 6 | Conifer needles / branches |
| 🌳 `bush` | 4 | Bush elements |
| 🌸 `flower` | 52 | Flowers (many color variants) |
| 🍂 `leaf` | 10 | Leafy trees (deciduous) |
| 🍄 `shroom` | 1 | Mushroom |
| 🐾 `animals` | 2 | Animals |
| 🟩 `fill` | 4 | Background fill elements (special — see below) |

> **Fill group** is a special layer placed **last**, ignores `--repeats`, and uses spacing + density just like other groups. Enable it with the `--fill` flag.

---

## 🚀 Quick Start

### 🐳 Docker (recommended)

```bash
# Linux / macOS
./pattern.sh --preset meadow --size 300x200

# Windows (PowerShell)
.\pattern.ps1 --preset meadow --size 300x200
```

### 🐍 Python directly

Requires **Python 3.12+**, **Pillow**, **NumPy**, and **SciPy**:

```bash
pip install Pillow numpy scipy
python generate_pattern.py --groups bush flower --fill --size 300x200
```

---

## 🎛️ All Parameters

### Required

| Argument | Description | Example |
|----------|-------------|---------|
| `--size` | Output image size as `WIDTHxHEIGHT` | `300x200` |

> ⚠️ At least one of `--groups`, `--fill`, or `--preset` must be provided.

### Optional

| Argument | Default | Description |
|----------|---------|-------------|
| `--groups` | *(none)* | One or more group names to include (e.g. `bush flower leaf`) |
| `--fill` | `false` | Enable the fill group (placed last, ignores `--repeats`) |
| `--preset` | *(none)* | Load a preset from `presets/<name>.json` — sets groups, fill, priority, density, spacing, etc. |
| `--all` | *(flag)* | 🔥 Use **all** group directories — adds `--fill` + every group as `--groups` (shell wrappers only) |
| `--priority` | *(none)* | Group name that should appear more often |
| `--priority-weight` | `3` | Multiplier for how often the priority group appears |
| `--spacing` | `30-80` | Min-max random spacing in pixels between images (format: `MIN-MAX`) |
| `--density` | `5` | How packed images are, `1`–`10` (higher = more images placed) |
| `--repeats` | *(unlimited)* | Max times a single PNG can appear on the canvas (fill ignores this) |
| `--flip` | `false` | Each placed image has a **50% chance** of being flipped horizontally |
| `--output` | `pattern_output.png` | Output filename (presets auto-name to `<preset>.png`) |
| `--seed` | *(random)* | Fix random seed for reproducible output |

---

## 📋 Presets

Presets are JSON files in the `presets/` folder. They pre-configure groups, fill, priority, density, spacing, and more — so you get a curated look with minimal flags.

| Preset | File | Groups | Priority | Density | Spacing | Fill | Flip |
|--------|------|--------|----------|---------|---------|------|------|
| 🌲 Forest Conifer | `forest-conifer.json` | conifer, bush, shroom | conifer (10×) | 10 | 0–2 | ✅ | ✅ |
| 🍃 Forest Leaf | `forest-leaf.json` | leaf, bush, flower | leaf (10×) | 10 | 0–2 | ✅ | ✅ |
| 🌻 Meadow | `meadow.json` | flower, bush | flower | 10 | 1–2 | ✅ | ✅ |

**CLI args always override preset values**, so you can fine-tune any preset:

```bash
./pattern.sh --preset forest-leaf --size 400x300 --density 7 --spacing 10-30
```

### 📝 Creating Your Own Preset

Add a JSON file to `presets/` with any of these keys:

```json
{
  "groups": ["leaf", "bush", "flower"],
  "fill": true,
  "flip": true,
  "priority": "leaf",
  "priority_weight": 10,
  "density": 10,
  "spacing": "0-2"
}
```

Then use it: `./pattern.sh --preset my-preset --size 300x200`

---

## 💡 Examples

```bash
# 🌲 Dense conifer forest using a preset
./pattern.sh --preset forest-conifer --size 300x200

# 🌻 Meadow with flowers and bushes
./pattern.sh --preset meadow --size 400x300

# 🎨 Custom mix: bushes + flowers + fill layer
./pattern.sh --groups bush flower --fill --size 300x200

# 🍂 Leaf-heavy pattern with priority
./pattern.sh --groups bush flower leaf --fill --size 400x300 --priority leaf --spacing 20-60

# 🌲 Sparse conifers with mushrooms
./pattern.sh --groups conifer shroom --size 200x150 --density 3 --spacing 40-100

# 🔄 Reproducible output with a fixed seed
./pattern.sh --groups fill flower --size 300x200 --seed 42

# 🔥 Everything at once
./pattern.sh --all --size 500x300

# 🪞 Flip images randomly for more variety
./pattern.sh --preset forest-leaf --size 300x200 --flip

# 🎯 Limit repeats: each image used at most 3 times
./pattern.sh --groups bush flower leaf --fill --size 300x200 --repeats 3
```

---

## 🐳 Docker Details

The shell wrappers (`pattern.sh` / `pattern.ps1`) automatically:

1. **Build** the Docker image (`pattern-generator`) if it doesn't exist or the Dockerfile changed
2. **Mount** the project directory into the container
3. **Run** the Python script with all provided arguments

The Docker image uses `python:3.12-slim` with Pillow, NumPy, and SciPy pre-installed.

---

## 📤 Output

The generated image is saved as a **transparent PNG (RGBA)** to the specified output path.
A progress bar is displayed during generation showing placement progress.

> ⏱️ **Performance note:** Generation time scales with canvas area. A `300x200` image finishes in seconds, while `3000x2000` can take **10+ minutes**. Start small to preview, then scale up for final output.

---

## ⚙️ How It Works

1. **Load** — PNGs from each requested group folder are loaded
2. **Pool** — A weighted pool is built (priority group gets extra draws)
3. **Phase 1** — Every unique image is placed once (largest first) to guarantee variety
4. **Phase 2** — Remaining capacity is filled from the weighted pool
5. **Fill pass** — If `--fill` is enabled, fill elements are placed on top
6. **Collision** — Each placement checks pixel-level alpha collision with a coarse 32px grid for speed
7. **Save** — Final RGBA canvas is saved as PNG

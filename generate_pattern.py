#!/usr/bin/env python3
"""
Generate a random pattern image from PNG source files.

Usage:
  python generate_pattern.py --groups bush flower --fill --size 3000x2000 [--spacing 30-80] [--priority leaf] [--output pattern.png]

Arguments:
  --groups     : One or more group names (e.g. bush flower leaf conifer shroom)
  --fill       : Enable the fill group (placed last, ignores --repeats, uses spacing+density)
  --preset     : Load a preset from presets/<name>.json (sets groups, fill, priority, density, spacing)
  --size       : Output image size as WIDTHxHEIGHT (e.g. 3000x2000)
  --spacing    : Min-max random spacing in pixels between images (default: 30-80)
  --priority   : Group name that should appear more often (2-3x weight)
  --priority-weight : How much more often priority group appears (default: 3)
  --density    : How packed the images are, 1-10 (default: 5). Higher = more attempts to place images
  --repeats    : Max times a single PNG image can be drawn on the result (default: unlimited, fill ignores this)
  --flip       : Each placed image has a 50% chance of being flipped horizontally
  --output     : Output filename (default: pattern_output.png)
  --seed       : Optional random seed for reproducibility (omit for random each run)
"""

import argparse
import glob
import json
import os
import random
import sys
import time

import numpy as np
from PIL import Image
from scipy.ndimage import binary_dilation


def find_group_files(directory, group_name):
    """Find all PNG files matching a group name in its subfolder."""
    group_dir = os.path.join(directory, group_name)
    if not os.path.isdir(group_dir):
        return []
    pattern = os.path.join(group_dir, f"{group_name}*.png")
    files = sorted(glob.glob(pattern))
    return files


def load_images(file_list):
    """Load images from file list, return list of (filename, PIL.Image) tuples."""
    images = []
    for f in file_list:
        try:
            img = Image.open(f).convert("RGBA")
            images.append((os.path.basename(f), img))
        except Exception as e:
            print(f"Warning: Could not load {f}: {e}", file=sys.stderr)
    return images


def build_weighted_pool(group_images, priority_group, priority_weight):
    """
    Build a weighted list of (group_name, images_list) for random selection.
    Priority group gets extra weight. All images from each group are included.
    Returns list of (group_name, images_list) tuples with priority groups repeated.
    """
    weighted_groups = []
    for group_name, images in group_images.items():
        if not images:
            continue

        weight = priority_weight if group_name == priority_group else 1
        for _ in range(weight):
            weighted_groups.append((group_name, images))

    return weighted_groups


def create_occupancy_mask(width, height):
    """Create a boolean occupancy grid for pixel-level collision."""
    return np.zeros((height, width), dtype=bool)


def _get_alpha_mask(img, _cache={}):
    """Extract alpha channel as a boolean NumPy array (True where opaque). Cached per image."""
    img_id = id(img)
    expected_shape = (img.size[1], img.size[0])  # (height, width)
    if img_id not in _cache or _cache[img_id].shape != expected_shape:
        alpha = np.array(img.split()[-1])
        _cache[img_id] = alpha > 0
    return _cache[img_id]


def mark_occupied(mask, x, y, img, spacing):
    """Mark pixels as occupied for a placed image, including spacing buffer."""
    w, h = img.size
    mask_h, mask_w = mask.shape

    alpha_mask = _get_alpha_mask(img)

    if spacing > 0:
        # Pad the alpha mask so dilation can expand beyond the image bounds
        padded = np.pad(alpha_mask, spacing, mode='constant', constant_values=False)
        dilation_size = 2 * spacing + 1
        struct = np.ones((dilation_size, dilation_size), dtype=bool)
        expanded = binary_dilation(padded, structure=struct)
    else:
        expanded = alpha_mask

    # The expanded mask's top-left corresponds to (x - spacing, y - spacing) on canvas
    exp_h, exp_w = expanded.shape
    origin_y = y - spacing if spacing > 0 else y
    origin_x = x - spacing if spacing > 0 else x

    # Clip to canvas bounds
    src_y0 = max(0, -origin_y)
    src_x0 = max(0, -origin_x)
    dst_y0 = max(0, origin_y)
    dst_x0 = max(0, origin_x)
    dst_y1 = min(mask_h, origin_y + exp_h)
    dst_x1 = min(mask_w, origin_x + exp_w)
    copy_h = dst_y1 - dst_y0
    copy_w = dst_x1 - dst_x0

    if copy_h > 0 and copy_w > 0:
        mask[dst_y0:dst_y1, dst_x0:dst_x1] |= expanded[src_y0:src_y0 + copy_h, src_x0:src_x0 + copy_w]


def can_place_image(mask, x, y, img):
    """Check if image can be placed without overlapping occupied pixels."""
    w, h = img.size
    mask_h, mask_w = mask.shape

    # Bounds check
    if x < 0 or y < 0 or x + w > mask_w or y + h > mask_h:
        return False

    alpha_mask = _get_alpha_mask(img)

    # Check overlap: any pixel that is both opaque and already occupied
    region = mask[y:y + h, x:x + w]
    return not np.any(region & alpha_mask)


CELL_SIZE = 32  # coarse grid cell size in pixels


def _build_coarse_grid(mask):
    """Build a coarse grid indicating which cells have ANY free space."""
    h, w = mask.shape
    rows = (h + CELL_SIZE - 1) // CELL_SIZE
    cols = (w + CELL_SIZE - 1) // CELL_SIZE
    grid = np.ones((rows, cols), dtype=bool)  # True = has free space
    for r in range(rows):
        for c in range(cols):
            block = mask[r * CELL_SIZE:(r + 1) * CELL_SIZE, c * CELL_SIZE:(c + 1) * CELL_SIZE]
            if block.all():  # fully occupied
                grid[r, c] = False
    return grid


def _update_coarse_grid(grid, mask, x, y, w, h, spacing):
    """Update coarse grid cells affected by a newly placed image."""
    r0 = max(0, (y - spacing) // CELL_SIZE)
    c0 = max(0, (x - spacing) // CELL_SIZE)
    r1 = min(grid.shape[0], (y + h + spacing) // CELL_SIZE + 1)
    c1 = min(grid.shape[1], (x + w + spacing) // CELL_SIZE + 1)
    mask_h, mask_w = mask.shape
    for r in range(r0, r1):
        for c in range(c0, c1):
            block = mask[r * CELL_SIZE:min((r + 1) * CELL_SIZE, mask_h),
                         c * CELL_SIZE:min((c + 1) * CELL_SIZE, mask_w)]
            if block.all():
                grid[r, c] = False


def try_place_image(canvas_w, canvas_h, img, mask, coarse_grid):
    """
    Try to find a random position where the image's non-transparent pixels
    don't overlap with already-occupied pixels.
    Uses coarse grid to focus searches on free areas.
    Returns (x, y) or None.
    """
    img_w, img_h = img.size
    max_x = max(0, canvas_w - img_w)
    max_y = max(0, canvas_h - img_h)
    if max_x == 0 and max_y == 0:
        if can_place_image(mask, 0, 0, img):
            return (0, 0)
        return None

    # Find coarse-grid cells that have free space and could fit the image
    free_cells = np.argwhere(coarse_grid)
    if len(free_cells) == 0:
        return None

    # Batch: generate many candidate positions at once in free cells
    batch_size = 64
    max_rounds = 16  # 64 * 16 = 1024 total attempts max

    for _ in range(max_rounds):
        # Pick random free cells
        cell_indices = np.random.randint(0, len(free_cells), size=batch_size)
        cells = free_cells[cell_indices]

        # Generate random offsets within each cell
        offsets_y = np.random.randint(0, CELL_SIZE, size=batch_size)
        offsets_x = np.random.randint(0, CELL_SIZE, size=batch_size)

        xs = np.clip(cells[:, 1] * CELL_SIZE + offsets_x, 0, max_x).astype(int)
        ys = np.clip(cells[:, 0] * CELL_SIZE + offsets_y, 0, max_y).astype(int)

        for i in range(batch_size):
            if can_place_image(mask, int(xs[i]), int(ys[i]), img):
                return (int(xs[i]), int(ys[i]))

    return None


def generate_pattern(
    directory,
    groups,
    output_width,
    output_height,
    spacing_min,
    spacing_max,
    priority_group,
    priority_weight,
    density,
    output_path,
    max_repeats=None,
    use_fill=False,
    flip=False,
):
    """Main generation logic."""
    t_start = time.time()

    # Step 1: Find and load images for each group
    group_images = {}
    total_found = 0
    for group in groups:
        files = find_group_files(directory, group)
        if not files:
            print(f"Warning: No files found for group '{group}'", file=sys.stderr)
            continue
        images = load_images(files)
        group_images[group] = images
        total_found += len(images)
        print(f"  Group '{group}': {len(images)} images found")

    # Load fill group separately if requested
    fill_images = []
    if use_fill:
        fill_files = find_group_files(directory, "fill")
        if not fill_files:
            print("Warning: No files found for fill group", file=sys.stderr)
        else:
            fill_images = load_images(fill_files)
            print(f"  Fill group: {len(fill_images)} images found")

    if total_found == 0 and not fill_images:
        print("Error: No images found for any specified group.", file=sys.stderr)
        sys.exit(1)

    # Step 2: Create canvas and occupancy mask
    canvas = Image.new("RGBA", (output_width, output_height), (255, 255, 255, 0))
    occupancy = create_occupancy_mask(output_width, output_height)
    placed_count = 0

    # Step 3: Place main group images (if any groups specified)
    if group_images:
        weighted_groups = build_weighted_pool(group_images, priority_group, priority_weight)
        if not weighted_groups:
            print("Warning: Main image pool is empty, skipping to fill.", file=sys.stderr)
        else:
            placed_count = _place_images(
                canvas, occupancy, weighted_groups,
                output_width, output_height,
                spacing_min, spacing_max, density,
                max_repeats=max_repeats,
                label="main",
                flip=flip,
            )

    # Step 4: Fill pass — no repeat limit, uses spacing + density
    if fill_images:
        fill_pool = [("fill", fill_images)]
        fill_placed = _place_images(
            canvas, occupancy, fill_pool,
            output_width, output_height,
            spacing_min, spacing_max, density,
            max_repeats=None,
            label="fill",
            flip=flip,
        )
        placed_count += fill_placed

    print(f"  Total placed: {placed_count} images on canvas")

    # Step 5: Save output (transparent background)
    canvas.save(output_path, "PNG")
    elapsed = time.time() - t_start
    print(f"  Output saved to: {output_path}")
    print(f"  Completed in {elapsed:.1f}s")


def _place_images(
    canvas, occupancy, weighted_groups,
    output_width, output_height,
    spacing_min, spacing_max, density,
    max_repeats=None,
    label="main",
    flip=False,
):
    """Place images from weighted_groups onto canvas/occupancy. Returns count placed."""

    # Count total unique images available
    all_images = []
    for _, subset in weighted_groups:
        all_images.extend(subset)
    unique_count = len(set(id(img) for _, img in all_images))
    print(f"  [{label}] Pool: {len(weighted_groups)} weighted groups, {unique_count} unique images")

    # Estimate how many images could reasonably fit
    area = output_width * output_height
    avg_opaque_pixels = 0
    count = 0
    seen = set()
    for _, subset in weighted_groups:
        for fname, img in subset:
            img_id = id(img)
            if img_id not in seen:
                seen.add(img_id)
                opaque = int(np.count_nonzero(_get_alpha_mask(img)))
                avg_opaque_pixels += opaque
                count += 1
    avg_opaque_pixels = avg_opaque_pixels / max(count, 1)

    avg_spacing = (spacing_min + spacing_max) / 2
    avg_side = avg_opaque_pixels ** 0.5
    effective_side = avg_side + avg_spacing
    effective_area = effective_side * effective_side
    estimated_fit = int(area / max(effective_area, 1)) if effective_area > 0 else 50
    fill_ratio = min(1.5, 0.2 + density * 0.12)
    target_images = max(10, int(estimated_fit * fill_ratio))
    max_consecutive_failures = 500

    print(f"  [{label}] Target: ~{target_images} images (estimated fit: {estimated_fit})...")

    placed_count = 0
    consecutive_failures = 0
    attempts = 0
    max_total_attempts = target_images * 10
    repeat_counts = {}

    # Build coarse grid for fast free-space lookup
    coarse_grid = _build_coarse_grid(occupancy)

    # Compute opaque pixel count for sorting (cached via _get_alpha_mask)
    def _sort_key(item):
        _, img = item
        return int(np.count_nonzero(_get_alpha_mask(img)))

    # --- Phase 1: Place every unique image at least once (largest first) ---
    # This guarantees all groups get representation before priority weighting kicks in.
    unique_pool = {}
    for _, images in weighted_groups:
        for fname, img in images:
            if id(img) not in unique_pool:
                unique_pool[id(img)] = (fname, img)
    unique_list = sorted(unique_pool.values(), key=_sort_key, reverse=True)
    print(f"  [{label}] Phase 1: placing {len(unique_list)} unique images (largest first)...")

    for fname, img in unique_list:
        if placed_count >= target_images or attempts >= max_total_attempts:
            break
        attempts += 1

        # Progress bar
        pct = placed_count / target_images
        bar_len = 40
        filled = int(bar_len * pct)
        bar = "█" * filled + "░" * (bar_len - filled)
        print(f"\r  [{label}] {bar} {pct:5.1%}  ({placed_count}/{target_images})", end="", flush=True)

        # Randomly flip horizontally with 50% chance
        if flip and random.random() < 0.5:
            img = img.transpose(Image.FLIP_LEFT_RIGHT)

        pos = try_place_image(output_width, output_height, img, occupancy, coarse_grid)
        if pos is not None:
            x, y = pos
            spacing = random.randint(spacing_min, spacing_max)
            mark_occupied(occupancy, x, y, img, spacing)
            _update_coarse_grid(coarse_grid, occupancy, x, y, img.size[0], img.size[1], spacing)
            canvas.paste(img, (x, y), img)
            placed_count += 1
            repeat_counts[id(img)] = repeat_counts.get(id(img), 0) + 1

    # --- Phase 2: Fill remaining capacity with priority-weighted pool (largest first) ---
    # Build the full weighted pool, sorted by size with randomized tiers
    flat_pool = []
    for _, images in weighted_groups:
        for fname, img in images:
            flat_pool.append((fname, img))

    flat_pool.sort(key=_sort_key, reverse=True)

    # Group by size tiers so images of similar size are shuffled randomly,
    # while the overall order stays largest-first
    def _build_tiered_pool(pool):
        sizes = [_sort_key(item) for item in pool]
        if not sizes:
            return pool
        max_s = max(sizes)
        tier_s = max(1, max_s // 10)
        result = []
        cur_tier = []
        cur_tid = sizes[0] // tier_s
        for i, item in enumerate(pool):
            tid = sizes[i] // tier_s
            if tid != cur_tid:
                random.shuffle(cur_tier)
                result.extend(cur_tier)
                cur_tier = [item]
                cur_tid = tid
            else:
                cur_tier.append(item)
        random.shuffle(cur_tier)
        result.extend(cur_tier)
        return result

    flat_pool = _build_tiered_pool(flat_pool)
    pool_index = 0

    while placed_count < target_images and attempts < max_total_attempts:
        attempts += 1

        # Progress bar
        pct = placed_count / target_images
        bar_len = 40
        filled = int(bar_len * pct)
        bar = "█" * filled + "░" * (bar_len - filled)
        print(f"\r  [{label}] {bar} {pct:5.1%}  ({placed_count}/{target_images})", end="", flush=True)

        # Cycle through size-sorted pool; re-tier on wrap
        filename, img = flat_pool[pool_index]
        pool_index += 1
        if pool_index >= len(flat_pool):
            pool_index = 0
            flat_pool = _build_tiered_pool(flat_pool)

        # Randomly flip horizontally with 50% chance
        if flip and random.random() < 0.5:
            img = img.transpose(Image.FLIP_LEFT_RIGHT)

        # Skip if this image has reached its repeat limit
        if max_repeats is not None and repeat_counts.get(id(img), 0) >= max_repeats:
            all_maxed = all(
                repeat_counts.get(id(im), 0) >= max_repeats
                for _, im in flat_pool
            )
            if all_maxed:
                print(f"  [{label}] Stopping: all images reached max repeats ({max_repeats})")
                break
            continue

        # Try to place using pixel-level collision with coarse grid acceleration
        pos = try_place_image(output_width, output_height, img, occupancy, coarse_grid)
        if pos is None:
            consecutive_failures += 1
            if consecutive_failures >= max_consecutive_failures:
                print(f"\n  [{label}] Stopping: {max_consecutive_failures} consecutive failures (canvas full)")
                break
            continue

        consecutive_failures = 0
        x, y = pos

        spacing = random.randint(spacing_min, spacing_max)
        mark_occupied(occupancy, x, y, img, spacing)
        _update_coarse_grid(coarse_grid, occupancy, x, y, img.size[0], img.size[1], spacing)
        canvas.paste(img, (x, y), img)
        placed_count += 1

        repeat_counts[id(img)] = repeat_counts.get(id(img), 0) + 1

    # Final progress bar at 100% (or actual end state)
    pct = placed_count / target_images if target_images > 0 else 1.0
    filled = int(40 * min(pct, 1.0))
    bar = "█" * filled + "░" * (40 - filled)
    print(f"\r  [{label}] {bar} {pct:5.1%}  ({placed_count}/{target_images})")
    print(f"  [{label}] Placed {placed_count} images")
    return placed_count


def parse_size(size_str):
    """Parse WIDTHxHEIGHT string."""
    parts = size_str.lower().split("x")
    if len(parts) != 2:
        raise argparse.ArgumentTypeError(f"Size must be WIDTHxHEIGHT, got: {size_str}")
    try:
        w, h = int(parts[0]), int(parts[1])
    except ValueError:
        raise argparse.ArgumentTypeError(f"Size must be integers, got: {size_str}")
    if w <= 0 or h <= 0:
        raise argparse.ArgumentTypeError("Size dimensions must be positive")
    return w, h


def parse_spacing(spacing_str):
    """Parse MIN-MAX spacing string."""
    parts = spacing_str.split("-")
    if len(parts) != 2:
        raise argparse.ArgumentTypeError(f"Spacing must be MIN-MAX, got: {spacing_str}")
    try:
        mn, mx = int(parts[0]), int(parts[1])
    except ValueError:
        raise argparse.ArgumentTypeError(f"Spacing must be integers, got: {spacing_str}")
    if mn < 0 or mx < mn:
        raise argparse.ArgumentTypeError("Spacing: need 0 <= MIN <= MAX")
    return mn, mx


def main():
    parser = argparse.ArgumentParser(
        description="Generate a random pattern image from PNG source files.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --preset forest-conifer --size 3000x2000
  %(prog)s --preset meadow --size 4000x3000 --repeats 5
  %(prog)s --groups bush flower --fill --size 3000x2000
  %(prog)s --groups bush flower leaf --fill --size 4000x3000 --priority leaf --spacing 20-60
  %(prog)s --groups conifer shroom --size 2000x1500 --density 7
        """,
    )
    parser.add_argument(
        "--groups", nargs="+", default=[],
        help="Group names to include (e.g. bush flower leaf conifer shroom)"
    )
    parser.add_argument(
        "--fill", action="store_true", default=False,
        help="Enable fill group (placed last, ignores --repeats, uses spacing+density)"
    )
    parser.add_argument(
        "--preset", default=None,
        help="Load a preset from presets/<name>.json (sets groups, fill, priority, density, spacing)"
    )
    parser.add_argument(
        "--size", required=True,
        help="Output image size as WIDTHxHEIGHT (e.g. 3000x2000)"
    )
    parser.add_argument(
        "--spacing", default="30-80",
        help="Min-max random spacing between images in pixels (default: 30-80)"
    )
    parser.add_argument(
        "--priority", default=None,
        help="Group name that should appear more often"
    )
    parser.add_argument(
        "--priority-weight", type=int, default=3,
        help="How much more often priority group appears (default: 3)"
    )
    parser.add_argument(
        "--density", type=int, default=5,
        help="How packed images are, 1-10 (default: 5). Higher = more attempts"
    )
    parser.add_argument(
        "--output", default="pattern_output.png",
        help="Output filename (default: pattern_output.png)"
    )
    parser.add_argument(
        "--repeats", type=int, default=None,
        help="Max times a single PNG image can be drawn on the result (default: unlimited)"
    )
    parser.add_argument(
        "--flip", action="store_true", default=False,
        help="Each placed image has a 50%% chance of being flipped horizontally"
    )
    parser.add_argument(
        "--seed", type=int, default=None,
        help="Random seed (omit for different result each run)"
    )

    args = parser.parse_args()

    # Determine working directory (where the source PNGs are)
    script_dir = os.path.dirname(os.path.abspath(__file__))

    # Load preset if specified (preset values act as defaults, CLI args override)
    if args.preset:
        preset_path = os.path.join(script_dir, "presets", f"{args.preset}.json")
        if not os.path.isfile(preset_path):
            available = [f.replace(".json", "") for f in os.listdir(os.path.join(script_dir, "presets")) if f.endswith(".json")]
            parser.error(f"Preset '{args.preset}' not found. Available: {', '.join(sorted(available))}")
        with open(preset_path) as f:
            preset = json.load(f)
        print(f"  Loading preset: {args.preset}")
        # Apply preset values as defaults (CLI args take precedence)
        if not args.groups and "groups" in preset:
            args.groups = preset["groups"]
        if not args.fill and preset.get("fill", False):
            args.fill = True
        # For these, check if the user explicitly provided them on CLI
        # by comparing against parser defaults
        if args.priority is None and "priority" in preset:
            args.priority = preset["priority"]
        if args.density == 5 and "density" in preset:  # 5 is the argparse default
            args.density = preset["density"]
        if args.spacing == "30-80" and "spacing" in preset:  # "30-80" is the argparse default
            args.spacing = preset["spacing"]
        if args.priority_weight == 3 and "priority_weight" in preset:  # 3 is the argparse default
            args.priority_weight = preset["priority_weight"]
        if not args.flip and preset.get("flip", False):
            args.flip = True
        if args.output == "pattern_output.png":  # default not overridden by user
            args.output = f"{args.preset}.png"

    # Parse complex args
    output_width, output_height = parse_size(args.size)
    spacing_min, spacing_max = parse_spacing(args.spacing)

    # Set random seed
    if args.seed is not None:
        random.seed(args.seed)
    else:
        random.seed(int(time.time() * 1000) ^ os.getpid())

    # Validate
    if args.density < 1 or args.density > 20:
        print("Warning: density outside recommended range 1-10", file=sys.stderr)

    if not args.groups and not args.fill:
        parser.error("At least one of --groups, --fill, or --preset is required")

    # Remove 'fill' from groups if accidentally included — use --fill instead
    if "fill" in args.groups:
        print("Warning: 'fill' removed from --groups. Use --fill flag for the fill group.", file=sys.stderr)
        args.groups = [g for g in args.groups if g != "fill"]
        args.fill = True

    if args.priority and args.priority not in args.groups:
        print(f"Warning: priority group '{args.priority}' not in --groups list, adding it", file=sys.stderr)
        args.groups.append(args.priority)

    print(f"Generating pattern: {output_width}x{output_height}")
    if args.groups:
        print(f"  Groups: {', '.join(args.groups)}")
    print(f"  Fill: {'yes' if args.fill else 'no'}")
    print(f"  Spacing: {spacing_min}-{spacing_max}px")
    print(f"  Density: {args.density}")
    if args.priority:
        print(f"  Priority: '{args.priority}' (weight: {args.priority_weight}x)")
    if args.repeats:
        print(f"  Max repeats per image: {args.repeats} (fill ignores this)")
    if args.flip:
        print(f"  Flip: random horizontal (50% chance)")

    generate_pattern(
        directory=script_dir,
        groups=args.groups,
        output_width=output_width,
        output_height=output_height,
        spacing_min=spacing_min,
        spacing_max=spacing_max,
        priority_group=args.priority,
        priority_weight=args.priority_weight,
        density=args.density,
        output_path=os.path.join(script_dir, args.output),
        max_repeats=args.repeats,
        use_fill=args.fill,
        flip=args.flip,
    )


if __name__ == "__main__":
    main()

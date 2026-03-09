#!/usr/bin/env python3
"""
Generate a random pattern image from PNG source files.

Usage:
  python generate_pattern.py --groups fill krzak kwiat --size 3000x2000 [--spacing 30-80] [--priority lisc] [--scale 0.5] [--output pattern.png]

Arguments:
  --groups     : One or more group names (e.g. fill krzak kwiat lisc)
  --size       : Output image size as WIDTHxHEIGHT (e.g. 3000x2000)
  --spacing    : Min-max random spacing in pixels between images (default: 30-80)
  --priority   : Group name that should appear more often (2-3x weight)
  --priority-weight : How much more often priority group appears (default: 3)
  --density    : How packed the images are, 1-10 (default: 5). Higher = more attempts to place images
  --output     : Output filename (default: pattern_output.png)
  --seed       : Optional random seed for reproducibility (omit for random each run)
"""

import argparse
import glob
import os
import random
import sys
import time

from PIL import Image


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
    Priority group gets extra weight.
    Each group contributes a random subset of its images (not all).
    Returns list of (group_name, subset) tuples with priority groups repeated.
    """
    weighted_groups = []
    for group_name, images in group_images.items():
        if not images:
            continue
        # Randomly select a subset (at least half, up to all)
        subset_size = random.randint(max(1, len(images) // 2), len(images))
        subset = random.sample(images, subset_size)

        weight = priority_weight if group_name == priority_group else 1
        for _ in range(weight):
            weighted_groups.append((group_name, subset))

    return weighted_groups


def create_occupancy_mask(width, height):
    """Create a boolean occupancy grid for pixel-level collision."""
    return [[False] * width for _ in range(height)]


def mark_occupied(mask, x, y, img, spacing):
    """Mark pixels as occupied for a placed image, including spacing buffer."""
    w, h = img.size
    mask_h = len(mask)
    mask_w = len(mask[0])

    for iy in range(h):
        for ix in range(w):
            _, _, _, a = img.getpixel((ix, iy))
            if a > 0:
                # Mark this pixel and spacing buffer around it
                for dy in range(-spacing, spacing + 1):
                    for dx in range(-spacing, spacing + 1):
                        my = y + iy + dy
                        mx = x + ix + dx
                        if 0 <= my < mask_h and 0 <= mx < mask_w:
                            mask[my][mx] = True


def can_place_image(mask, x, y, img):
    """Check if image can be placed without overlapping occupied pixels."""
    w, h = img.size
    mask_h = len(mask)
    mask_w = len(mask[0])

    for iy in range(h):
        for ix in range(w):
            _, _, _, a = img.getpixel((ix, iy))
            if a > 0:
                my = y + iy
                mx = x + ix
                if my < 0 or my >= mask_h or mx < 0 or mx >= mask_w:
                    return False
                if mask[my][mx]:
                    return False
    return True


def try_place_image(canvas_w, canvas_h, img, mask):
    """
    Try to find a random position where the image's non-transparent pixels
    don't overlap with already-occupied pixels. Returns (x, y) or None.
    """
    img_w, img_h = img.size
    max_attempts = 1000
    for _ in range(max_attempts):
        x = random.randint(0, max(0, canvas_w - img_w))
        y = random.randint(0, max(0, canvas_h - img_h))

        if can_place_image(mask, x, y, img):
            return (x, y)

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
):
    """Main generation logic."""

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

    if total_found == 0:
        print("Error: No images found for any specified group.", file=sys.stderr)
        sys.exit(1)

    # Step 2: Build weighted group list
    weighted_groups = build_weighted_pool(group_images, priority_group, priority_weight)
    if not weighted_groups:
        print("Error: Image pool is empty.", file=sys.stderr)
        sys.exit(1)

    # Count total unique images available
    all_images = []
    for _, subset in weighted_groups:
        all_images.extend(subset)
    unique_count = len(set(id(img) for _, img in all_images))
    print(f"  Pool: {len(weighted_groups)} weighted groups, {unique_count} unique images")

    # Step 3: Create canvas
    canvas = Image.new("RGBA", (output_width, output_height), (255, 255, 255, 0))

    # Step 4: Place images randomly using pixel-level occupancy mask
    occupancy = create_occupancy_mask(output_width, output_height)
    placed_count = 0

    # Estimate how many images could reasonably fit
    area = output_width * output_height
    # Count actual non-transparent pixels per image for better estimates
    avg_opaque_pixels = 0
    count = 0
    seen = set()
    for _, subset in weighted_groups:
        for fname, img in subset:
            img_id = id(img)
            if img_id not in seen:
                seen.add(img_id)
                w, h = img.size
                opaque = sum(1 for iy in range(h) for ix in range(w) if img.getpixel((ix, iy))[3] > 0)
                avg_opaque_pixels += opaque
                count += 1
    avg_opaque_pixels = avg_opaque_pixels / max(count, 1)

    # Account for spacing in area estimate
    avg_spacing = (spacing_min + spacing_max) / 2
    avg_side = avg_opaque_pixels ** 0.5
    effective_side = avg_side + avg_spacing
    effective_area = effective_side * effective_side
    estimated_fit = int(area / max(effective_area, 1)) if effective_area > 0 else 50
    # density 1-10 controls how much of estimated_fit we try to place
    # density 1 = ~30%, density 5 = ~75%, density 10 = ~120% (overshoot to fill gaps)
    fill_ratio = min(1.5, 0.2 + density * 0.12)
    target_images = max(10, int(estimated_fit * fill_ratio))
    max_consecutive_failures = 500  # Stop after this many failures in a row

    print(f"  Target: ~{target_images} images (estimated fit: {estimated_fit})...")

    consecutive_failures = 0
    attempts = 0
    max_total_attempts = target_images * 10  # Safety cap
    recently_used = []  # Track last N images to avoid streaks
    max_recent = max(3, unique_count // 2)  # Avoid repeating within last N picks

    while placed_count < target_images and attempts < max_total_attempts:
        attempts += 1

        # Pick a random weighted group, then a random image from it
        # Avoid picking the same image as recently used
        for _pick_try in range(10):
            _, subset = random.choice(weighted_groups)
            filename, img = random.choice(subset)
            if id(img) not in recently_used or _pick_try == 9:
                break

        # Use image at original size (no scaling, no rotation)
        rw, rh = img.size

        # Try to place using pixel-level collision
        pos = try_place_image(output_width, output_height, img, occupancy)
        if pos is None:
            consecutive_failures += 1
            if consecutive_failures >= max_consecutive_failures:
                print(f"  Stopping: {max_consecutive_failures} consecutive placement failures (canvas full)")
                break
            continue

        consecutive_failures = 0
        x, y = pos

        # Mark occupied pixels with spacing buffer
        spacing = random.randint(spacing_min, spacing_max)
        mark_occupied(occupancy, x, y, img, spacing)

        # Paste with alpha compositing
        canvas.paste(img, (x, y), img)
        placed_count += 1

        # Track recently used to ensure variety
        recently_used.append(id(img))
        if len(recently_used) > max_recent:
            recently_used.pop(0)

    print(f"  Placed {placed_count} images on canvas")

    # Step 5: Save output (transparent background)
    canvas.save(output_path, "PNG")
    print(f"  Output saved to: {output_path}")


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
  %(prog)s --groups fill krzak kwiat --size 3000x2000
  %(prog)s --groups fill krzak kwiat lisc --size 4000x3000 --priority lisc --spacing 20-60
  %(prog)s --groups igla grzyb --size 2000x1500 --density 7
        """,
    )
    parser.add_argument(
        "--groups", nargs="+", required=True,
        help="Group names to include (e.g. fill krzak kwiat)"
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
        "--seed", type=int, default=None,
        help="Random seed (omit for different result each run)"
    )

    args = parser.parse_args()

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
    if args.priority and args.priority not in args.groups:
        print(f"Warning: priority group '{args.priority}' not in --groups list, adding it", file=sys.stderr)
        args.groups.append(args.priority)

    # Determine working directory (where the source PNGs are)
    script_dir = os.path.dirname(os.path.abspath(__file__))

    print(f"Generating pattern: {output_width}x{output_height}")
    print(f"  Groups: {', '.join(args.groups)}")
    print(f"  Spacing: {spacing_min}-{spacing_max}px")
    print(f"  Density: {args.density}")
    if args.priority:
        print(f"  Priority: '{args.priority}' (weight: {args.priority_weight}x)")

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
    )


if __name__ == "__main__":
    main()

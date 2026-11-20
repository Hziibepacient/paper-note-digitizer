#!/usr/bin/env python3
"""Export one paper note with its original outline and a short contact shadow."""

import argparse
import io
import json
import math
import os
from pathlib import Path
from tempfile import NamedTemporaryFile

from PIL import Image, ImageCms, ImageDraw, ImageFilter, ImageOps


SRGB = ImageCms.ImageCmsProfile(ImageCms.createProfile('sRGB'))
EDGE_ALPHA = [max(0, min(255, round((value - 22) * 255 / 212))) for value in range(256)]


def read_outline(path, size):
    data = json.loads(path.read_text(encoding='utf-8-sig'))
    if isinstance(data, dict):
        data = data.get('points')
    if not isinstance(data, list) or len(data) < 3:
        raise ValueError('The outline needs at least three [x, y] points.')

    width, height = size
    points = []
    for index, point in enumerate(data, start=1):
        if (
            not isinstance(point, list)
            or len(point) != 2
            or any(type(value) not in (int, float) or not math.isfinite(value) for value in point)
        ):
            raise ValueError(f'Outline point {index} must be a finite [x, y] pair.')
        x, y = point
        if not (0 <= x < width and 0 <= y < height):
            raise ValueError(f'Outline point {index} is outside the oriented {width} × {height} photo.')
        points.append((x, y))

    twice_area = sum(
        x * next_y - next_x * y
        for (x, y), (next_x, next_y) in zip(points, points[1:] + points[:1])
    )
    if abs(twice_area) < 2:
        raise ValueError('The outline must trace a perimeter enclosing at least one pixel of paper.')
    return points


def normalize_color(image):
    profile = image.info.get('icc_profile')
    transform_input = image
    if image.mode == 'LA':
        transform_input = image.getchannel('L')
    elif image.mode not in ('RGB', 'CMYK', 'L', 'LAB'):
        transform_input = image.convert('RGB')
    if not profile:
        return transform_input.convert('RGB')

    try:
        return ImageCms.profileToProfile(
            transform_input, io.BytesIO(profile), SRGB, outputMode='RGB'
        )
    except (ImageCms.PyCMSError, OSError, ValueError) as error:
        raise ValueError(f'Cannot convert the source ICC profile to sRGB: {error}') from error


def extract_face(image, image_format, outline_path):
    if outline_path is None:
        if image_format != 'PNG':
            raise ValueError('Use a transparent PNG or supply --outline for the source photo.')
        alpha = image.convert('RGBA').getchannel('A')
        if alpha.getextrema() != (0, 255):
            raise ValueError('The PNG needs a transparent background and opaque paper. Supply --outline to cut it out.')
        alpha = alpha.point(EDGE_ALPHA)
        bounds = alpha.getbbox()
        face = normalize_color(image.crop(bounds)).convert('RGBA')
        face.putalpha(alpha.crop(bounds))
        return face

    points = read_outline(outline_path, image.size)
    xs, ys = zip(*points)
    left = max(0, math.floor(min(xs)) - 3)
    top = max(0, math.floor(min(ys)) - 3)
    right = min(image.width, math.ceil(max(xs)) + 4)
    bottom = min(image.height, math.ceil(max(ys)) + 4)
    bounds = left, top, right, bottom
    face = normalize_color(image.crop(bounds)).convert('RGBA')

    # Supersample the mask only. Leave the actual photographic pixels at source resolution.
    scale = 4
    mask = Image.new('L', (face.width * scale, face.height * scale))
    polygon = [((x - left + 0.5) * scale, (y - top + 0.5) * scale) for x, y in points]
    ImageDraw.Draw(mask).polygon(polygon, fill=255)
    alpha = mask.resize(face.size, Image.Resampling.LANCZOS).point(EDGE_ALPHA)
    if alpha.getextrema()[1] != 255:
        raise ValueError('The outline does not contain enough paper to make an opaque cutout.')
    face.putalpha(alpha)
    return face.crop(alpha.getbbox())


def shadow_layer(alpha, color, opacity, radius, offset):
    mask = Image.new('L', alpha.size)
    shadow = alpha.filter(ImageFilter.GaussianBlur(radius))
    mask.paste(shadow.point(lambda value: round(value * opacity)), offset)
    layer = Image.new('RGBA', alpha.size, (*color, 0))
    layer.putalpha(mask)
    return layer


def render_note(face):
    # Scale the lighting to the paper, independently of the source photo's canvas.
    scale = min(face.size) / 1089
    padding = max(6, math.ceil(78 * scale))
    canvas = Image.new('RGBA', (face.width + 2 * padding, face.height + 2 * padding))
    canvas.paste(face, (padding, padding))
    alpha = canvas.getchannel('A')
    result = Image.new('RGBA', canvas.size)
    for color, opacity, blur, (dx, dy) in (
        ((65, 60, 49), 0.35, 12, (9, 17)),      # Soft falloff
        ((70, 65, 54), 0.49, 2.8, (3, 6)),     # Tight contact shadow
        ((130, 123, 108), 0.78, 0.5, (1, 3)),   # Narrow paper thickness
    ):
        offset = round(dx * scale), max(1, round(dy * scale))
        result = Image.alpha_composite(result, shadow_layer(alpha, color, opacity, blur * scale, offset))
    result = Image.alpha_composite(result, canvas)
    left, top, right, bottom = result.getchannel('A').getbbox()
    margin = max(2, round(9 * scale))
    return result.crop((left - margin, top - margin, right + margin, bottom + margin))


def write_png(image, path, overwrite):
    path.parent.mkdir(parents=True, exist_ok=True)
    if overwrite:
        # Write completely before replacing a previous successful render.
        temp_path = None
        try:
            with NamedTemporaryFile(dir=path.parent, delete=False) as output:
                temp_path = Path(output.name)
                image.save(output, format='PNG', icc_profile=SRGB.tobytes(), optimize=True)
            os.replace(temp_path, path)
        finally:
            if temp_path is not None:
                temp_path.unlink(missing_ok=True)
        return

    # Encode before opening the destination. Exclusive creation also works on FAT/exFAT volumes.
    encoded = io.BytesIO()
    image.save(encoded, format='PNG', icc_profile=SRGB.tobytes(), optimize=True)
    try:
        output = path.open('xb')
    except FileExistsError as error:
        raise ValueError(f'Output already exists: {path}. Use --overwrite to replace it.') from error
    try:
        with output:
            output.write(encoded.getbuffer())
    except OSError:
        path.unlink(missing_ok=True)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', type=Path, help='Transparent PNG or source photo')
    parser.add_argument('output', type=Path, help='Destination PNG')
    parser.add_argument('--outline', type=Path, help='JSON array of [x,y] points in the EXIF-oriented image')
    parser.add_argument('--rotate', type=int, choices=(0, 90, 180, 270), default=0,
                        help='Clockwise rotation after cutting and before adding the shadow')
    parser.add_argument('--overwrite', action='store_true', help='Replace an existing output PNG')
    args = parser.parse_args()

    try:
        if args.output.suffix.lower() != '.png':
            raise ValueError('Output filename must end in .png.')
        source_paths = (args.input, args.outline) if args.outline is not None else (args.input,)
        if any(args.output.resolve() == path.resolve() for path in source_paths):
            raise ValueError('Choose an output different from the input and outline.')
        with Image.open(args.input) as source:
            face = extract_face(ImageOps.exif_transpose(source), source.format, args.outline)
        if args.rotate:
            face = face.rotate(-args.rotate, expand=True)
        result = render_note(face)
        write_png(result, args.output, args.overwrite)
    except (OSError, ValueError, Image.DecompressionBombError) as error:
        parser.exit(1, f'Error: {error}\n')

    print(f'{args.output} ({result.width} x {result.height})')


if __name__ == '__main__':
    main()

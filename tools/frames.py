"""Split and pack a Work Pets v2 sprite sheet without changing its RGBA pixels."""

import argparse
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory

from PIL import Image


CELL = (192, 208)
COLUMNS = 8
STANDARD_ROWS = (
    ("idle", 6),
    ("running-right", 8),
    ("running-left", 8),
    ("waving", 4),
    ("jumping", 5),
    ("failed", 8),
    ("waiting", 6),
    ("running", 6),
    ("review", 6),
)
LOOK_ROWS = (
    ("look-row-9", ("000", "022.5", "045", "067.5", "090", "112.5", "135", "157.5")),
    ("look-row-10", ("180", "202.5", "225", "247.5", "270", "292.5", "315", "337.5")),
)
ATLAS_SIZE = (COLUMNS * CELL[0], (len(STANDARD_ROWS) + len(LOOK_ROWS)) * CELL[1])


def cells():
    """Yield row, column, relative path and whether the cell holds a pose."""
    for row, (state, count) in enumerate(STANDARD_ROWS):
        for column in range(COLUMNS):
            name = f"{column:02d}.png" if column < count else f"unused-{column:02d}.png"
            yield row, column, Path(state) / name, column < count
    for row, (state, angles) in enumerate(LOOK_ROWS, start=len(STANDARD_ROWS)):
        for column, angle in enumerate(angles):
            yield row, column, Path(state) / f"{angle}.png", True


def check_cell(image, path, used):
    if image.size != CELL:
        raise ValueError(f"{path}: expected {CELL[0]}x{CELL[1]}, got {image.size}")
    visible = image.getchannel("A").getbbox() is not None
    if visible != used:
        expected = "visible artwork" if used else "a fully transparent unused cell"
        raise ValueError(f"{path}: expected {expected}")


def split(source, output):
    if output.exists():
        raise ValueError(f"Output already exists: {output}")
    with Image.open(source) as image:
        if image.size != ATLAS_SIZE:
            raise ValueError(f"Expected {ATLAS_SIZE[0]}x{ATLAS_SIZE[1]}, got {image.size}")
        atlas = image.convert("RGBA")

    output.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=output.parent) as temporary:
        staging = Path(temporary) / "frames"
        for row, column, path, used in cells():
            x, y = column * CELL[0], row * CELL[1]
            frame = atlas.crop((x, y, x + CELL[0], y + CELL[1]))
            check_cell(frame, path, used)
            target = staging / path
            target.parent.mkdir(parents=True, exist_ok=True)
            frame.save(target)
        # Reserve a fresh destination before moving the completed rows into place.
        output.mkdir()
        for folder in staging.iterdir():
            folder.rename(output / folder.name)


def pack(source, output):
    if output.suffix.lower() != ".png":
        raise ValueError("Choose a .png output file")
    atlas = Image.new("RGBA", ATLAS_SIZE)
    for row, column, path, used in cells():
        with Image.open(source / path) as image:
            frame = image.convert("RGBA")
        check_cell(frame, path, used)
        # Pasting without an alpha mask preserves semitransparent and hidden RGB.
        atlas.paste(frame, (column * CELL[0], row * CELL[1]))
    encoded = BytesIO()
    atlas.save(encoded, format="PNG")
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("xb") as destination:
        destination.write(encoded.getbuffer())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for command, help_text, source, output in (
        ("split", "extract all 88 cells", "ATLAS", "NEW_DIRECTORY"),
        ("pack", "rebuild the v2 PNG", "FRAMES_DIRECTORY", "NEW_PNG"),
    ):
        sub = commands.add_parser(command, help=help_text)
        sub.add_argument("source", type=Path, metavar=source)
        sub.add_argument("output", type=Path, metavar=output)
    args = parser.parse_args()
    try:
        if args.command == "split":
            split(args.source, args.output)
        else:
            pack(args.source, args.output)
    except (OSError, ValueError) as exc:
        parser.exit(1, f"{parser.prog}: {exc}\n")


if __name__ == "__main__":
    main()

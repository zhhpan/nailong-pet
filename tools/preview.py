"""Render 25 fps GIF and MP4 previews from a Work Pets v2 atlas and optional laugh strip."""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont


FPS = 25
CELL = (192, 208)
PANEL = (320, 352)
MATTE = (248, 246, 239)
PAD = 24
ROWS = (
    ("idle", "待机", (280, 110, 110, 140, 140, 320)),
    ("running-right", "向右跑", (120,) * 7 + (220,)),
    ("running-left", "向左跑", (120,) * 7 + (220,)),
    ("waving", "挥手", (140,) * 3 + (280,)),
    ("jumping", "跳跃", (140,) * 4 + (280,)),
    ("failed", "沮丧", (140,) * 7 + (240,)),
    ("waiting", "等你回应", (150,) * 5 + (260,)),
    ("running", "思考", (120,) * 5 + (220,)),
    ("review", "检查", (150,) * 5 + (280,)),
)


def sources(atlas_path, laugh_strip):
    with Image.open(atlas_path) as source:
        if source.size != (1536, 2288):
            raise ValueError("A 1536×2288 v2 atlas is required")
        atlas = source.convert("RGBA")

    def crop(row, col):
        x, y = col * CELL[0], row * CELL[1]
        return np.asarray(atlas.crop((x, y, x + CELL[0], y + CELL[1])))

    for row, (name, label, timing) in enumerate(ROWS):
        yield name, label, timing, [crop(row, col) for col in range(len(timing))]
    yield "look-loop", "环顾四周", (150,) * 16, [crop(i // 8 + 9, i % 8) for i in range(16)]
    if laugh_strip:
        with Image.open(laugh_strip) as strip:
            if strip.size != (1536, 208) or strip.mode != "RGBA":
                raise ValueError("Expected a 1536×208 RGBA laugh strip with eight 192×208 cells")
            frames = [np.asarray(strip.crop((i*192, 0, (i+1)*192, 208))) for i in range(8)]
        yield "laugh", "捧腹大笑", (160, 160, 200, 200, 240, 200, 200, 200), frames


def preview_font(chosen):
    if chosen:
        return ImageFont.truetype(str(chosen), 20), True
    fonts = [
        Path("/System/Library/Fonts/PingFang.ttc"),
        Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
        Path("/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc"),
    ]
    if os.environ.get("WINDIR"):
        fonts.insert(0, Path(os.environ["WINDIR"]) / "Fonts" / "msyh.ttc")
    for path in fonts:
        if path.is_file():
            return ImageFont.truetype(str(path), 20), True
    return ImageFont.load_default(size=20), False


def floating_images(rgba):
    alpha = rgba[:, :, 3:4].astype(np.float32) / 255
    visible = rgba[:, :, :3].astype(np.float32) * alpha
    # A darker estimation background gives the pale belly and limbs unambiguous edges.
    gray = cv2.cvtColor((visible + 48 * (1 - alpha)).astype("uint8"), cv2.COLOR_RGB2GRAY)
    matte = np.asarray(MATTE, dtype=np.float32)
    color = np.dstack((visible + (1 - alpha) * matte, alpha * 255))
    yy, xx = np.where(alpha[:, :, 0] > 0.5)
    if not xx.size:
        raise ValueError("Blank input frame")
    center = np.array([(xx.max() + xx.min()) / 2, (yy.max() + yy.min()) / 2], dtype=np.float32)
    gray = cv2.copyMakeBorder(gray, PAD, PAD, PAD, PAD, cv2.BORDER_CONSTANT, value=48)
    color = cv2.copyMakeBorder(color, PAD, PAD, PAD, PAD, cv2.BORDER_CONSTANT, value=(*MATTE, 0))
    return gray, color, center


def sample(source, coords):
    return cv2.remap(source, coords, None, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)


class PairMotion:
    def __init__(self, first, second, solver):
        gray0, self.first, center0 = first
        gray1, color1, center1 = second
        height, width = gray0.shape
        self.grid = np.stack(np.meshgrid(np.arange(width), np.arange(height)), axis=-1).astype(np.float32)
        # Remove coarse translation before fitting local limb, eye and silhouette motion.
        self.shift = center1 - center0
        aligned = self.grid + self.shift
        gray1 = sample(gray1, aligned)
        self.second = sample(color1, aligned)
        self.fwd = self.regularize(solver.calc(gray0, gray1, None))
        self.bwd = self.regularize(solver.calc(gray1, gray0, None))

    @staticmethod
    def regularize(flow):
        # Isolated disoccluded feature matches should not fold the warp over itself.
        return cv2.GaussianBlur(np.clip(flow, -12, 12), (0, 0), 8)

    def frame(self, t):
        target = self.grid - t * self.shift
        # Estimate the inverse map at the middle position using both directions.
        flow = (1 - t) * sample(self.fwd, target) - t * sample(self.bwd, target)
        map0 = target - t * flow
        map1 = target + (1 - t) * flow
        first, second = sample(self.first, map0), sample(self.second, map1)
        # Avoid double edges and half-transparent limbs by selecting the closer
        # warped keyframe wherever it offers a materially different appearance.
        disagreement = np.max(np.abs(first - second), axis=2)
        conflicts = (disagreement >= 24).astype(np.float32)
        # Include the interior of an eye or paw in the same occlusion decision.
        conflicts = cv2.dilate(conflicts, np.ones((7, 7), np.uint8))
        conflict = cv2.GaussianBlur(conflicts, (0, 0), 1.0)
        blend = (t * (1 - conflict) + int(t > 0.5) * conflict)[:, :, None]
        frame = first * (1 - blend) + second * blend
        frame = frame[PAD:-PAD, PAD:-PAD]
        alpha = frame[:, :, 3:4] / 255
        rgb = (frame[:, :, :3] - (1 - alpha) * MATTE) / np.maximum(alpha, 0.001)
        return np.clip(np.dstack((rgb, frame[:, :, 3])) + 0.5, 0, 255).astype(np.uint8)


def interpolate(keys, timing, solver):
    inputs = [floating_images(key) for key in keys]
    boundaries = np.cumsum((0, *timing))
    count = max(len(keys), round(boundaries[-1] * FPS / 1000))
    frames, midpoints = [], []
    for i in range(len(keys)):
        pair = PairMotion(inputs[i], inputs[(i + 1) % len(inputs)], solver)
        midpoints.append(Image.fromarray(pair.frame(0.5)))
        for tick in range(count):
            when = tick * boundaries[-1] / count
            if boundaries[i] <= when < boundaries[i + 1]:
                t = (when - boundaries[i]) / timing[i]
                frames.append(Image.fromarray(pair.frame(t)))
    return frames, midpoints


def on_panel(frame, label, font):
    panel = Image.new("RGB", PANEL, MATTE)
    frame = frame.resize((264, 286), Image.Resampling.LANCZOS)
    panel.paste(frame, (28, 12), frame)
    ImageDraw.Draw(panel).text((PANEL[0] // 2, 320), label, anchor="mm", font=font, fill=(60, 52, 43))
    return panel


def encode(ffmpeg, frames, destination, fps):
    base = [ffmpeg, "-hide_banner", "-loglevel", "error", "-n", "-f", "rawvideo", "-pix_fmt",
            "rgb24", "-video_size", f"{PANEL[0]}x{PANEL[1]}", "-framerate", str(fps), "-i", "pipe:0"]
    if destination.suffix == ".gif":
        args = ["-filter_complex", "split[p][v];[p]palettegen=stats_mode=diff[pal];"
                "[v][pal]paletteuse=dither=bayer:bayer_scale=4", "-loop", "0"]
    else:
        args = ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "16", "-movflags", "+faststart"]
    with subprocess.Popen([*base, *args, destination], stdin=subprocess.PIPE) as process:
        for frame in frames:
            process.stdin.write(frame.tobytes())
        process.stdin.close()
        if process.wait():
            raise RuntimeError(f"FFmpeg failed while writing {destination}")


def digests(frames):
    return {hashlib.blake2s(frame.tobytes()).digest() for frame in frames}


def gif_metrics(path):
    with Image.open(path) as gif:
        unique = set()
        durations = []
        for i in range(gif.n_frames):
            gif.seek(i)
            unique.add(hashlib.blake2s(gif.convert("RGB").tobytes()).digest())
            durations.append(gif.info.get("duration", 0))
        return {"encoded_frames": len(durations), "unique_encoded_gif_frames": len(unique),
                "encoded_frame_duration_ms": sorted(set(durations)), "encoded_seconds": sum(durations) / 1000}


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("atlas", type=Path, help="1536×2288 transparent v2 sprite sheet")
    cli.add_argument("new_output", type=Path, help="new directory for the overview, per-state clips and QA")
    cli.add_argument("--laugh-strip", type=Path, help="optional 1536×208 RGBA strip for the separate laugh loop")
    cli.add_argument("--ffmpeg", default=shutil.which("ffmpeg"), help="FFmpeg executable (default: ffmpeg on PATH)")
    cli.add_argument("--font", type=Path, help="font with Chinese glyphs; English labels are used if no CJK font is found")
    cli.add_argument("--overview-loops", type=int, default=1, help="cycles per state in the overview (default: 1)")
    args = cli.parse_args()
    if not args.ffmpeg or not shutil.which(args.ffmpeg):
        cli.error("Install FFmpeg on PATH or specify its executable with --ffmpeg")
    if args.overview_loops < 1:
        cli.error("--overview-loops must be at least 1")
    font, use_chinese = preview_font(args.font)
    output = args.new_output
    output.mkdir(parents=True, exist_ok=False)
    per_state = output / "states"
    qa = output / "qa"
    per_state.mkdir()
    qa.mkdir()
    cv2.setNumThreads(2)
    solver = cv2.DISOpticalFlow_create(cv2.DISOPTICAL_FLOW_PRESET_MEDIUM)
    solver.setFinestScale(0)
    solver.setGradientDescentIterations(30)
    solver.setVariationalRefinementIterations(5)
    overview, metrics = [], {}
    english = {"running": "Thinking", "failed": "Setback", "look-loop": "Looking around"}
    for name, label, timing, keys in sources(args.atlas, args.laugh_strip):
        if not use_chinese:
            label = english.get(name, name.replace("-", " ").capitalize())
        raw, midpoints = interpolate(keys, timing, solver)
        panels = [on_panel(frame, label, font) for frame in raw]
        for filetype in (".mp4", ".gif"):
            encode(args.ffmpeg, panels, per_state / (name + filetype), FPS)
        strip = Image.new("RGB", (len(keys) * CELL[0], CELL[1]), MATTE)
        for i, middle in enumerate(midpoints):
            strip.paste(middle, (CELL[0] * i, 0), middle)
        strip.save(qa / f"{name}-midpoints.png")
        if name == "laugh":
            raw[0].save(output / "laugh-transparent.webp", save_all=True, append_images=raw[1:],
                        duration=1000 // FPS, loop=0, lossless=True, method=6)
        metrics[name] = {"fps": FPS, "source_keys": len(keys), "raw_unique": len(digests(panels)),
                         **gif_metrics(per_state / (name + ".gif"))}
        overview.extend(panels * args.overview_loops)
        print(name, metrics[name], flush=True)
    for filetype in (".mp4", ".gif"):
        encode(args.ffmpeg, overview, output / ("all-states" + filetype), FPS)
    metrics["all-states"] = {"fps": FPS, "cycles_each": args.overview_loops,
                             "raw_unique": len(digests(overview)), **gif_metrics(output / "all-states.gif")}
    (qa / "timing.json").write_text(json.dumps(metrics, indent=2, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()

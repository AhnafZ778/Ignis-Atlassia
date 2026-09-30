#!/usr/bin/env python3
"""Render the local, silent 30-second FireAtlas evidence video from captured UI."""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FRAMES = ROOT / "docs" / "winning-plan" / "evidence" / "video-frames"
OUTPUT = ROOT / "docs" / "winning-plan" / "evidence" / "FireAtlas_30s_demo.mp4"
FPS = 30
WIDTH = 1600
HEIGHT = 900

SCENES = (
    {
        "image": "01-globe-home.png",
        "duration": 4,
        "label": "01 / NASA FIRMS · SENSOR RECORDS",
        "title": "One daily calendar for researchers and local planners.",
        "subtitle": "Compare dated MODIS + VIIRS detections on a shared UTC cell-day grid.",
    },
    {
        "image": "02-norcal-calendar.png",
        "duration": 8,
        "label": "02 / NORTHERN CALIFORNIA · JULY 2024",
        "title": "Comparison not usable.",
        "subtitle": "Only 1 comparable year; the result is shown as insufficient history.",
    },
    {
        "image": "03-norcal-july25.png",
        "duration": 3,
        "label": "03 / JULY 25 · DOCUMENTED S-NPP PROCESSING GAP",
        "title": "925.3 estimated cell-days.",
        "subtitle": "MODIS-based estimate; satellite pass and cloud status remain unknown.",
    },
    {
        "image": "04-park-source-rows.png",
        "duration": 3,
        "label": "04 / OPEN THE SOURCE ROWS",
        "title": "Inspect the original records.",
        "subtitle": "Acquisition time · native confidence · product version.",
    },
    {
        "image": "05-punjab-calendar.png",
        "duration": 6,
        "label": "05 / PUNJAB–HARYANA · OCTOBER 2024",
        "title": "A harvest-window view for local planners.",
        "subtitle": "Official context · heat detections do not confirm crop-residue fires.",
    },
    {
        "image": "06-calibration-norcal.png",
        "duration": 3,
        "label": "06 / HELD-OUT CHECK · 41 MONTH PAIRS EACH",
        "title": "The current uncertainty is under-calibrated.",
        "subtitle": "Nominal 95% intervals cover 41.5% / 39.0% of held-out pairs.",
    },
    {
        "image": None,
        "duration": 3,
        "label": "FIREATLAS · NASA MODIS + VIIRS",
        "title": "See the dates. Inspect the evidence.",
        "subtitle": "Local silent demo · public URL not verified · independent review pending.",
    },
)


def _textfile(directory: Path, name: str, value: str) -> Path:
    path = directory / f"{name}.txt"
    path.write_text(value, encoding="utf-8")
    return path


def _drawtext(font: str, textfile: Path, color: str, size: int, x: int, y: int) -> str:
    return (f"drawtext=fontfile={font}:textfile={textfile}:expansion=none:"
            f"fontcolor={color}:fontsize={size}:x={x}:y={y}")


def _verify_video(path: Path) -> None:
    probe = shutil.which("ffprobe")
    if not probe:
        raise RuntimeError("ffprobe is required to verify the rendered video")
    result = subprocess.run(
        [probe, "-v", "error", "-show_entries",
         "format=duration:stream=codec_name,codec_type,width,height,r_frame_rate",
         "-of", "json", str(path)],
        check=True, capture_output=True, text=True,
    )
    data = json.loads(result.stdout)
    streams = data.get("streams", [])
    video = [stream for stream in streams if stream.get("codec_type") == "video"]
    audio = [stream for stream in streams if stream.get("codec_type") == "audio"]
    if len(video) != 1 or audio:
        raise RuntimeError("Expected one silent video stream")
    stream = video[0]
    duration = float(data["format"]["duration"])
    if (stream.get("codec_name") != "h264" or stream.get("width") != WIDTH
            or stream.get("height") != HEIGHT or stream.get("r_frame_rate") != "30/1"
            or abs(duration - 30.0) > 0.1):
        raise RuntimeError(f"Unexpected video properties: {data}")


def render() -> Path:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("ffmpeg is required to render the video")
    for scene in SCENES:
        if scene["image"] and not (FRAMES / scene["image"]).is_file():
            raise FileNotFoundError(FRAMES / scene["image"])

    font_head = "fireatlas/static/fonts/space-grotesk.ttf"
    font_body = "fireatlas/static/fonts/dm-sans.ttf"
    for font in (ROOT / font_head, ROOT / font_body):
        if not font.is_file():
            raise FileNotFoundError(font)

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="fireatlas-winning-video-") as temp:
        temporary = Path(temp)
        command = [ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin", "-y"]
        filter_parts: list[str] = []
        video_labels: list[str] = []

        for index, scene in enumerate(SCENES):
            duration = scene["duration"]
            command += ["-f", "lavfi", "-i",
                        f"color=c=0x07131c:s={WIDTH}x{HEIGHT}:r={FPS}:d={duration}"]
            background_index = index * 2
            bg = f"bg{index}"
            if scene["image"]:
                image_path = FRAMES / scene["image"]
                command += ["-loop", "1", "-framerate", str(FPS), "-t", str(duration),
                            "-i", str(image_path)]
                image_index = background_index + 1
                image_label = f"img{index}"
                filter_parts.append(
                    f"[{image_index}:v]fps={FPS},scale=1440:810:"
                    "force_original_aspect_ratio=decrease,"
                    "pad=1440:810:(ow-iw)/2:(oh-ih)/2:color=0x07131c,"
                    f"setsar=1,format=rgba[{image_label}]"
                )
                filter_parts.append(
                    f"[{background_index}:v]fps={FPS},format=rgba[{bg}]"
                )
                composed = f"composed{index}"
                filter_parts.append(
                    f"[{bg}][{image_label}]overlay=80:16:shortest=1,"
                    "drawbox=x=79:y=15:w=1442:h=812:color=0x344b58:t=1,"
                    f"drawbox=x=80:y=832:w=1440:h=1:color=0x263c4a:t=fill[{composed}]"
                )
            else:
                filter_parts.append(
                    f"[{background_index}:v]fps={FPS},format=rgba,"
                    "drawbox=x=0:y=0:w=7:h=900:color=0xf39a68:t=fill,"
                    "drawbox=x=160:y=219:w=1280:h=1:color=0x344b58:t=fill,"
                    "drawtext=fontfile=" + font_body + ":text=FIREATLAS:"
                    "fontcolor=0xf39a68:fontsize=16:x=160:y=250,"
                    "drawtext=fontfile=" + font_head + ":text=FireAtlas:"
                    "fontcolor=0xf3f6f6:fontsize=72:x=160:y=300,"
                    "drawtext=fontfile=" + font_head + ":text=See the dates. Inspect the evidence.:"
                    "fontcolor=0xf3f6f6:fontsize=40:x=160:y=414,"
                    "drawtext=fontfile=" + font_body + ":text=MODIS Terra/Aqua C6.1 + VIIRS Suomi NPP C2:"
                    "fontcolor=0xa8bac2:fontsize=23:x=160:y=482,"
                    "drawbox=x=160:y=562:w=950:h=54:color=0x142833:t=fill,"
                    "drawtext=fontfile=" + font_body + ":text=LOCAL DEMO · PUBLIC URL NOT VERIFIED:"
                    "fontcolor=0xffae7b:fontsize=20:x=180:y=578,"
                    "drawtext=fontfile=" + font_body + ":text=Independent scientific review is pending.:"
                    "fontcolor=0x8ea4ad:fontsize=18:x=160:y=812,"
                    f"drawbox=x=80:y=832:w=1440:h=1:color=0x263c4a:t=fill[{bg}]"
                )

            progress_parts = []
            segment_width = 198
            gap = 9
            for progress_index in range(len(SCENES)):
                x = 80 + progress_index * (segment_width + gap)
                color = "0xf39a68" if progress_index == index else "0x2a3c46"
                progress_parts.append(
                    f"drawbox=x={x}:y=897:w={segment_width}:h=3:color={color}:t=fill"
                )
            captioned = f"captioned{index}"
            if scene["image"]:
                label_path = _textfile(temporary, f"scene-{index}-label", scene["label"])
                title_path = _textfile(temporary, f"scene-{index}-title", scene["title"])
                subtitle_path = _textfile(temporary, f"scene-{index}-subtitle", scene["subtitle"])
                filter_parts.append(
                    f"[composed{index}]"
                    f"{_drawtext(font_body, label_path, '0xf4a071', 12, 80, 837)},"
                    f"{_drawtext(font_head, title_path, '0xf2f5f5', 24, 80, 851)},"
                    f"{_drawtext(font_body, subtitle_path, '0xa5b7bf', 15, 80, 880)},"
                    f"{','.join(progress_parts)}[{captioned}]"
                )
            else:
                filter_parts.append(
                    f"[{bg}]{','.join(progress_parts)}[{captioned}]"
                )
            zoomed = f"zoomed{index}"
            filter_parts.append(
                f"[{captioned}]zoompan=z='min(zoom+0.00005,1.015)':d=1:"
                "x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
                f"s={WIDTH}x{HEIGHT}:fps={FPS},trim=duration={duration},"
                f"setpts=PTS-STARTPTS,format=yuv420p[{zoomed}]"
            )
            video_labels.append(f"[{zoomed}]")

        filter_parts.append(
            f"{''.join(video_labels)}concat=n={len(SCENES)}:v=1:a=0,"
            f"fps={FPS},format=yuv420p[outv]"
        )
        command += ["-filter_complex", ";".join(filter_parts),
                    "-map", "[outv]", "-an", "-t", "30", "-r", str(FPS),
                    "-c:v", "libx264", "-preset", "medium", "-crf", "20",
                    "-movflags", "+faststart", str(OUTPUT)]
        subprocess.run(command, cwd=ROOT, check=True)

    _verify_video(OUTPUT)
    return OUTPUT


if __name__ == "__main__":
    try:
        path = render()
    except (FileNotFoundError, RuntimeError, subprocess.CalledProcessError) as exc:
        raise SystemExit(str(exc)) from exc
    print(f"Rendered and verified: {path.relative_to(ROOT)}")

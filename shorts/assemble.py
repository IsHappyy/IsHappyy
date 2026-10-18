"""Step 6: stitch images + voice into a vertical MP4 and burn in the subtitles."""

import os
import subprocess

FPS = 30


def _run(args, cwd=None):
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *args], check=True, cwd=cwd)


def scene_clip(image, audio, seconds, out_path):
    """Still image with a slow zoom (Ken Burns) so the scene feels alive."""
    frames = int(seconds * FPS) + 1
    zoom = (
        f"scale=2160:3840,zoompan=z='min(zoom+0.0007,1.12)':d={frames}"
        f":x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=1080x1920:fps={FPS}"
    )
    _run(["-loop", "1", "-i", str(image), "-i", str(audio), "-vf", zoom,
          "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k",
          "-t", f"{seconds:.3f}", str(out_path)])


def concat(clips, out_path):
    listing = out_path.with_suffix(".txt")
    listing.write_text("".join(f"file '{c.resolve()}'\n" for c in clips), encoding="utf-8")
    _run(["-f", "concat", "-safe", "0", "-i", str(listing), "-c", "copy", str(out_path)])


def burn_subtitles(video, srt, out_path):
    style = "FontSize=13,Bold=1,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,Outline=2,MarginV=60"
    font = os.environ.get("SUBTITLE_FONT_NAME")
    if font:
        style += f",FontName={font}"
    # Run inside the subtitle's folder so the filter gets a plain relative path
    # (the subtitles filter is picky about colons and backslashes in paths).
    _run(["-i", str(video.resolve()), "-vf", f"subtitles={srt.name}:force_style='{style}'",
          "-c:a", "copy", str(out_path.resolve())], cwd=srt.parent)


def assemble(images, audios, durations, srt_path, project_dir):
    clip_dir = project_dir / "clips"
    clip_dir.mkdir(exist_ok=True)
    clips = []
    for i, (image, audio, seconds) in enumerate(zip(images, audios, durations), 1):
        clip = clip_dir / f"clip_{i:02d}.mp4"
        scene_clip(image, audio, seconds, clip)
        clips.append(clip)

    raw = project_dir / "video_no_subs.mp4"
    concat(clips, raw)
    final = project_dir / "final.mp4"
    burn_subtitles(raw, srt_path, final)
    return final

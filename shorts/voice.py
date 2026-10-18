"""Step 3: Thai voice-over, one audio file per scene."""

import os
import subprocess

import requests

ELEVENLABS_URL = "https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"


def elevenlabs(text, out_path):
    voice_id = os.environ["ELEVENLABS_VOICE_ID"]
    response = requests.post(
        ELEVENLABS_URL.format(voice_id=voice_id),
        headers={"xi-api-key": os.environ["ELEVENLABS_API_KEY"]},
        json={"text": text, "model_id": os.environ.get("ELEVENLABS_MODEL", "eleven_v3")},
        timeout=120,
    )
    response.raise_for_status()
    out_path.write_bytes(response.content)


def silent(text, out_path):
    """Offline stand-in for testing: silence as long as the line would take to read."""
    seconds = max(1.5, len(text) / 12)
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono",
         "-t", f"{seconds:.2f}", "-q:a", "9", str(out_path)],
        check=True,
    )


PROVIDERS = {"elevenlabs": elevenlabs, "silent": silent}


def duration(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
        check=True, capture_output=True, text=True,
    )
    return float(out.stdout.strip())


def voice_scenes(script, out_dir, provider):
    speak = PROVIDERS[provider]
    paths = []
    for i, scene in enumerate(script["scenes"], 1):
        path = out_dir / f"voice_{i:02d}.mp3"
        if not path.exists():
            speak(scene["narration"], path)
        paths.append(path)
    return paths

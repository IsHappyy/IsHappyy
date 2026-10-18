# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A Python pipeline that turns a topic into a Thai short video (TikTok / YouTube Shorts) for a
health / sports / news explainer channel with a cartoon mascot. User-facing docs are in Thai (`README.md`).

## Commands

```bash
pip install -r requirements.txt          # needs ffmpeg/ffprobe on PATH
python run.py ideas <category>           # topic ideas (Claude + web search)
python run.py new "<topic>"              # research.md + script.json in projects/<stamp>_<slug>/
python run.py render projects/<dir> [--voice silent]   # audio, subtitles.srt, final.mp4
```

`--voice silent` plus placeholder images lets `render` run fully offline — use it to test
changes to subtitles/visuals/assembly without API keys. There is no test suite yet.

## Architecture

`run.py` is the orchestrator: each step writes a file into the project folder and the next
step reads it, so a human can review/edit between steps (especially `script.json` before render).

- `shorts/claude.py` — single `ask()` helper: Claude API via `client.beta.messages.create`
  with `fallbacks="default"`, `pause_turn` continuation, and optional JSON-schema output.
- `shorts/research.py` → web search/fetch server tools → Thai research notes with URLs.
- `shorts/script.py` → strict JSON schema (`SCRIPT_SCHEMA`) of scenes: narration, on-screen text, image prompt.
- `shorts/voice.py` → per-scene mp3 via `PROVIDERS` registry (add new TTS vendors there).
- `shorts/subtitles.py` → SRT built from script text + audio durations (no speech recognition).
- `shorts/visuals.py` → uses `images/scene_XX.png` if present, else pastel placeholders; writes `images/prompts.txt`.
- `shorts/assemble.py` → FFmpeg zoompan per scene, concat, burn subtitles.

Channel persona (mascot, tone, art style, sign-off) lives in `channel.json` and is injected into the script prompt.
Secrets go in `.env` (git-ignored); `projects/` output is git-ignored.

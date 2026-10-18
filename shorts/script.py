"""Step 2: turn research notes into a scene-by-scene script (JSON)."""

import json

from .claude import ask

SCENE = {
    "type": "object",
    "properties": {
        "narration": {"type": "string", "description": "Thai voice-over line for this scene"},
        "on_screen_text": {"type": "string", "description": "Short Thai caption shown big on screen (max ~6 words)"},
        "visual_prompt": {"type": "string", "description": "English image prompt for the scene, featuring the mascot"},
    },
    "required": ["narration", "on_screen_text", "visual_prompt"],
    "additionalProperties": False,
}

SCRIPT_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "scenes": {"type": "array", "items": SCENE},
        "caption": {"type": "string", "description": "Post caption in Thai, ends with a short disclaimer for health topics"},
        "hashtags": {"type": "array", "items": {"type": "string"}},
        "sources": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"title": {"type": "string"}, "url": {"type": "string"}},
                "required": ["title", "url"],
                "additionalProperties": False,
            },
        },
        "review_notes": {
            "type": "string",
            "description": "Claims the human reviewer should double-check before publishing",
        },
    },
    "required": ["title", "scenes", "caption", "hashtags", "sources", "review_notes"],
    "additionalProperties": False,
}


def system_prompt(channel):
    return f"""You write scripts for the Thai short-video channel "{channel['name']}".
Tone: {channel['tone']}
Mascot (must appear in every visual_prompt, described the same way every time):
{channel['mascot']}
Art style for every visual_prompt: {channel['art_style']}

Script rules:
- Total narration about {channel['target_seconds']} seconds when read aloud in Thai
  (roughly 4-5 Thai syllables per second), split into 6-9 scenes.
- Scene 1 is the hook: a question or surprising fact that lands in under 3 seconds.
- Middle scenes: explain 2-3 key points simply, one idea per scene.
- Second-to-last scene: one thing the viewer can do today.
- Last scene: the mascot's sign-off line: "{channel['signoff']}"
- Use only facts present in the research notes. Never invent numbers or sources.
- Health topics: no dosages, no diagnosis, no cure claims."""


def write_script(research_notes, channel):
    prompt = "บันทึกการค้นคว้า:\n\n" + research_notes + "\n\nเขียนบทคลิปตามรูปแบบ JSON ที่กำหนด"
    return ask(system_prompt(channel), prompt, schema=SCRIPT_SCHEMA)


def save(script, path):
    path.write_text(json.dumps(script, ensure_ascii=False, indent=2), encoding="utf-8")

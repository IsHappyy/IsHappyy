"""Command line for the shorts pipeline: research -> script -> voice -> subtitles -> video.

    python run.py ideas สุขภาพ                 # topic ideas for a category
    python run.py new "นอนน้อยทำให้อ้วนจริงไหม"  # research + script, then stop for review
    python run.py render projects/<folder>     # voice + subtitles + video from script.json
    python run.py auto "หัวข้อ"                 # everything in one go (still review before posting!)
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).parent


def load_env():
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip())


def channel():
    return json.loads((ROOT / "channel.json").read_text(encoding="utf-8"))


def new_project_dir(topic):
    slug = re.sub(r"[^\w]+", "-", topic).strip("-")[:40]
    path = ROOT / "projects" / f"{datetime.now():%Y%m%d-%H%M}_{slug}"
    path.mkdir(parents=True, exist_ok=True)
    return path


def cmd_ideas(args):
    from shorts.research import ideas

    print(ideas(args.category, args.count))


def cmd_new(args):
    from shorts import research, script

    project = new_project_dir(args.topic)
    print(f"[1/2] ค้นข้อมูล: {args.topic}")
    notes = research.research(args.topic)
    (project / "research.md").write_text(notes, encoding="utf-8")

    print("[2/2] เขียนบท")
    result = script.write_script(notes, channel())
    script.save(result, project / "script.json")

    print(f"\nเสร็จแล้ว: {project}")
    print("ตรวจ script.json (โดยเฉพาะ review_notes) แล้วรัน:")
    print(f'  python run.py render "{project}"')
    return project


def cmd_render(args):
    from shorts import assemble, subtitles, visuals, voice

    project = Path(args.project)
    data = json.loads((project / "script.json").read_text(encoding="utf-8"))

    print(f"[1/4] พากย์เสียง ({args.voice})")
    audio_dir = project / "audio"
    audio_dir.mkdir(exist_ok=True)
    audios = voice.voice_scenes(data, audio_dir, args.voice)
    durations = [voice.duration(a) + 0.3 for a in audios]  # small breath between scenes

    print("[2/4] ซับไทเทิล")
    srt = project / "subtitles.srt"
    srt.write_text(subtitles.build_srt([s["narration"] for s in data["scenes"]], durations), encoding="utf-8")

    print("[3/4] ภาพประกอบ")
    images = visuals.scene_images(data, project)

    print("[4/4] ตัดต่อ")
    final = assemble.assemble(images, audios, durations, srt, project)

    caption = data["caption"] + "\n\n" + " ".join(data["hashtags"])
    (project / "caption.txt").write_text(caption, encoding="utf-8")
    print(f"\nคลิป: {final}\nแคปชัน: {project / 'caption.txt'}")
    if any(p.name.startswith("placeholder") for p in images):
        print(f"หมายเหตุ: ยังใช้ภาพชั่วคราวอยู่ ใส่ภาพจริงตาม {project / 'images' / 'prompts.txt'} แล้ว render ใหม่")


def cmd_auto(args):
    args.project = cmd_new(args)
    cmd_render(args)


def main():
    load_env()
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(required=True)

    p = sub.add_parser("ideas", help="เสนอหัวข้อคลิป")
    p.add_argument("category")
    p.add_argument("--count", type=int, default=10)
    p.set_defaults(func=cmd_ideas)

    p = sub.add_parser("new", help="ค้นข้อมูล + เขียนบท")
    p.add_argument("topic")
    p.set_defaults(func=cmd_new)

    voices = ["elevenlabs", "silent"]
    p = sub.add_parser("render", help="พากย์ + ซับ + ตัดต่อ จาก script.json")
    p.add_argument("project")
    p.add_argument("--voice", choices=voices, default="elevenlabs")
    p.set_defaults(func=cmd_render)

    p = sub.add_parser("auto", help="ทำทุกขั้นในคำสั่งเดียว")
    p.add_argument("topic")
    p.add_argument("--voice", choices=voices, default="elevenlabs")
    p.set_defaults(func=cmd_auto)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    sys.exit(main())

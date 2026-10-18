"""Step 4: one 9:16 image per scene.

Real artwork goes in <project>/images/scene_01.png, scene_02.png, ...
(made from images/prompts.txt in Midjourney, Flux, Canva, etc.). Any scene
without artwork gets a pastel placeholder card so the pipeline still runs.
"""

import os

from PIL import Image, ImageDraw, ImageFont

SIZE = (1080, 1920)
PASTELS = ["#FFD6E0", "#C1E7E3", "#FFF1C1", "#D7C9FF", "#C9F2C7", "#FFE0C2"]


def write_prompts(script, image_dir):
    lines = [f"scene_{i:02d}.png\n{s['visual_prompt']}\n" for i, s in enumerate(script["scenes"], 1)]
    (image_dir / "prompts.txt").write_text("\n".join(lines), encoding="utf-8")


def _font(size):
    path = os.environ.get("THAI_FONT_PATH")
    return ImageFont.truetype(path, size) if path else ImageFont.load_default(size)


def placeholder(text, index, path):
    image = Image.new("RGB", SIZE, PASTELS[index % len(PASTELS)])
    draw = ImageDraw.Draw(image)
    draw.text((SIZE[0] / 2, 500), f"SCENE {index + 1}", font=_font(90), fill="#555", anchor="mm")
    # Thai glyphs need a Thai font (set THAI_FONT_PATH); the default font shows boxes.
    if os.environ.get("THAI_FONT_PATH"):
        draw.text((SIZE[0] / 2, SIZE[1] / 2), text, font=_font(80), fill="#333", anchor="mm")
    image.save(path)


def scene_images(script, project_dir):
    image_dir = project_dir / "images"
    image_dir.mkdir(exist_ok=True)
    write_prompts(script, image_dir)
    paths = []
    for i, scene in enumerate(script["scenes"]):
        path = image_dir / f"scene_{i + 1:02d}.png"
        if not path.exists():
            placeholder(scene["on_screen_text"], i, image_dir / f"placeholder_{i + 1:02d}.png")
            path = image_dir / f"placeholder_{i + 1:02d}.png"
        paths.append(path)
    return paths

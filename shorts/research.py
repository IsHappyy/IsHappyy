"""Step 1: research a topic on the web and write fact notes with sources."""

from .claude import ask

WEB_TOOLS = [
    {"type": "web_search_20260209", "name": "web_search", "max_uses": 8},
    {"type": "web_fetch_20260209", "name": "web_fetch", "max_uses": 5},
]

SYSTEM = """You are the research desk for a Thai short-video channel that explains health,
sports and science news to a general audience with cute cartoon animation.

Research the topic on the web and write research notes in Thai for the script writer.
Rules:
- Prefer primary and authoritative sources: WHO, CDC, NIH, Thai Department of Disease
  Control / Ministry of Public Health, peer-reviewed studies, official league or federation sites.
- Every factual claim must carry the source URL it came from.
- Flag anything uncertain, disputed, or based on a single small study.
- For health topics: no drug names with doses, no diagnosis, no claims that something cures a disease.
- Finish with 3-5 "surprising but true" angles that would make a strong 3-second hook."""

IDEAS_SYSTEM = """You plan topics for a Thai short-video channel (TikTok / YouTube Shorts)
that explains health, sports and science news with cute cartoon animation.
Search the web for what is current and what Thai viewers are asking about."""


def research(topic):
    prompt = f"หัวข้อ: {topic}\n\nค้นข้อมูลและเขียนบันทึกการค้นคว้า (research notes) พร้อมลิงก์แหล่งอ้างอิงทุกข้อ"
    return ask(SYSTEM, prompt, tools=WEB_TOOLS)


def ideas(category, count=10):
    prompt = (
        f"เสนอหัวข้อคลิปหมวด '{category}' จำนวน {count} หัวข้อ เป็นภาษาไทย "
        "แต่ละข้อให้มี: ชื่อหัวข้อ, ประโยคเปิด 3 วินาที, เหตุผลที่คนน่าจะสนใจตอนนี้, แหล่งข้อมูลหลัก 1 ลิงก์"
    )
    return ask(IDEAS_SYSTEM, prompt, tools=WEB_TOOLS, effort="medium")

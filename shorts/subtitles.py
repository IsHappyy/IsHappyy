"""Step 5: build an .srt file straight from the script text and voice durations."""

MAX_CHARS = 22  # Thai characters per subtitle line that stay readable on a phone


def chunks(text):
    """Split on the spaces Thai writing uses between phrases, packing up to MAX_CHARS."""
    out, current = [], ""
    for word in text.split():
        if current and len(current) + 1 + len(word) > MAX_CHARS:
            out.append(current)
            current = word
        else:
            current = f"{current} {word}".strip()
    if current:
        # A tiny tail ("นะ", "ครับ") would flash for a split second; keep it with the line before.
        if out and len(current) < 6:
            out[-1] = f"{out[-1]} {current}"
        else:
            out.append(current)
    return out


def _stamp(seconds):
    ms = int(round(seconds * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def build_srt(narrations, durations):
    """Each scene's time is shared among its chunks in proportion to their length."""
    entries, start = [], 0.0
    for text, length in zip(narrations, durations):
        parts = chunks(text)
        total = sum(len(p) for p in parts) or 1
        t = start
        for part in parts:
            end = t + length * len(part) / total
            entries.append((t, end, part))
            t = end
        start += length
    return "\n".join(
        f"{n}\n{_stamp(a)} --> {_stamp(b)}\n{text}\n" for n, (a, b, text) in enumerate(entries, 1)
    )

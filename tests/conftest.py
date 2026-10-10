import pymupdf
import pytest


def make_vector_pdf(path):
    """A small Pioneer-style vector drawing: title block (value above label) and a
    TAG | X LOC | Y LOC | SIZE hole table. Enough vector paths to classify as VECTOR."""
    doc = pymupdf.open()
    page = doc.new_page(width=842, height=595)
    for i in range(30):  # frame + view lines
        page.draw_line((40 + i * 10, 300), (40 + i * 10, 420))
    page.draw_rect(pymupdf.Rect(20, 20, 822, 575))

    def t(x, y, s):
        page.insert_text((x, y), s, fontsize=8)

    # dimensions in the view
    t(200, 440, "200")
    t(20 + 10, 360, "150")

    # hole table
    t(500, 60, "TAG"); t(540, 60, "X LOC"); t(590, 60, "Y LOC"); t(700, 60, "SIZE")
    rows = [("A1", 75), ("A2", 87), ("A3", 99), ("A4", 111),
            ("B1", 123), ("B2", 135), ("C1", 147), ("C2", 159)]
    for i, (tag, y) in enumerate(rows):
        t(500, y, tag); t(540, y, f"{20 + i * 15:.2f}"); t(590, y, f"{30 + i * 10:.2f}")
    t(700, 87, "6.6 THRU"); t(700, 99, "11 6.5")
    t(700, 129, "M6x1.0 - 6H 12")
    t(700, 153, "8.0 THRU H7")

    # title block: values sit above their labels
    t(420, 520, "TK-2638-01"); t(420, 535, "Dwg No.")
    t(560, 520, "BASE PLATE"); t(560, 535, "PART NAME")
    t(660, 520, "SS400 t=12"); t(660, 535, "MATERIAL")
    t(760, 520, "2"); t(760, 535, "Q'TY")
    t(660, 560, "BLACK OXIDE"); t(660, 575, "FINISHING")
    doc.save(path)
    return path


@pytest.fixture
def vector_pdf(tmp_path):
    return make_vector_pdf(tmp_path / "TK-2638-01.pdf")

# Drawing-to-Quote (TPT) — วิเคราะห์ว่าทำไมตัน และแผนใหม่

_อ้างอิง: ไฟล์สถานะ "Drawing-to-Quote AI Agent Pipeline (TPT) — สถานะและแผนจนเสร็จ", คู่มือหลัก "คู่มือสร้าง AI Agents ประเมินราคาชิ้นงานจาก Drawing" และ skill `tpt-machining-quote` (estimate.py, parse_vector.py, prep_scan.py, inspect_pdf.py, shop_profile.json)_

## สรุปสั้นที่สุด

งานที่ทำมา **ไม่ได้ผิดทาง** — reading agents, คลังสัญลักษณ์ และบทเรียน 6 ข้อมีค่ามาก แต่ที่ตันเพราะ **ขัดเกลาขั้นอ่านแบบโดยไม่มีราคาออกมาเป็นตัววัด** ทุก edge case เลยดูสำคัญเท่ากันหมด

แนวทางใหม่: **ทำให้ครบวงจรก่อน (vertical slice) แล้วให้ "ผลต่อราคา" เป็นตัวเลือกว่าจะแก้อะไรต่อ** — AI กรอกใบประเมินล่วงหน้า, คนยืนยัน 1–2 นาที, โค้ดคิดราคา, ทุกการแก้ของคนกลายเป็นข้อมูล eval

---

## 1. วินิจฉัย: ทำไมถึงตัน (5 สาเหตุราก)

### 1.1 ไม่มีวงจรครบ → ขั้นอ่านแบบไม่มีเส้นชัย
ขั้น 2–3 "ใกล้เสร็จ" มาหลายรอบ แต่ทุกรอบเจอเรื่องใหม่ (⌵ vs ╲╱, Summit 5 sub-template, groove, hatch legend) แผนข้อ 1–5 ที่เขียนไว้ก็ยังเป็นงานฝั่งอ่านทั้งหมด เพราะยังไม่มีราคาออกมา จึงไม่มีทางบอกได้ว่าข้อผิดพลาดไหน "พอรับได้" และข้อไหน "ต้องแก้ก่อน"

### 1.2 เป้าหมายการอ่านคือ "ถอดแบบให้ครบ" แทน "สิ่งที่ราคาต้องใช้"
ตัวคิดราคาที่มีอยู่แล้ว (estimate.py — feature-count model) ใช้แค่: วัสดุ, t/L/W, qty, จำนวน setup, tolerance class, finish และ **จำนวน** op แต่ละประเภท — พิกัด X/Y ของ hole table มีผลต่อราคา **0 บาท**

ความไวของราคา (คิดจาก `shop_profile.json` ค่า default — machine 750 ฿/ชม., programming 600 ฿/ชม.):

| อ่านผิดแบบนี้ | กระทบราคา |
|---|---|
| รูเจาะหาย/เกิน 1 รู (AL) | ~5 บาท (<1%) |
| เกลียว M6 หาย 1 รู | ~10 บาท |
| L อ่านผิด 10 มม. บนแผ่น 200×150 (ทดสอบจริงใน eval) | −0.7% |
| setup ผิด 1 ครั้ง | ~200+ บาท (setup 15 นาที + probe + load) |
| tolerance general ↔ H7 | เวลาตัดทั้งชิ้น ×1.4 |
| วัสดุ AL ↔ SUS / SKD11 | เวลาตัด ×3–4, ค่าวัสดุ ~×1.8 |

→ การพิสูจน์ 21/21 และ 33/33 รูด้วย tag matching คือการลงแรงในจุดที่ราคาอ่อนไหว **น้อยที่สุด** ขณะที่ setup / วัสดุ / tolerance (ตัวที่แพงจริง) ยังไม่มีขั้นไหนตรวจจริงจัง

### 1.3 "Runtime" คือการสั่ง Claude Code ในแชท ไม่ใช่โปรแกรม
สองปัญหาที่ดูแยกกัน มาจากรากเดียว:
- บทเรียนข้อ 5: Claude Code เขียน Python เลียนแบบกฎแทนเรียกโมเดล
- ปัญหาค้างข้อ 1: ไม่แน่ใจว่ารันด้วย `feature_reader.md` เวอร์ชันไหน

รากคือ prompt อยู่ `D:\AI\MD file\` นอก version control และมี agent อีกตัวตีความคำสั่ง "รัน" ให้ทุกครั้ง → ผลไม่ reproducible และ regression ต้องทำมือ
**แก้ถาวร:** prompt อยู่ใน git, โค้ดเรียก API ตรง, บันทึก `prompt_sha` + โมเดลที่ตอบจริง ลงผลทุกครั้ง (ทำแล้วใน repo นี้)

### 1.4 ใช้ AI ทำงานที่เป็นกฎตายตัว (ขัดหลักการของตัวเอง)
- Pioneer 205/215 ไฟล์มี text layer → hole table `TAG | X LOC | Y LOC | SIZE` ดึงด้วยโค้ดได้แม่น 100% (`parse_vector.py::tag_table()` ทำอยู่แล้ว)
- "จับคู่ด้วย tag เท่านั้น" คือ join ธรรมดา → ควรเป็นโค้ด; AI ควรรับเฉพาะ **เศษที่จับคู่ไม่ได้** (feature ไม่มี tag, dedup ข้าม view)
- สคริปต์ที่ Claude Code เคยเขียนเอง จริง ๆ คือสัญญาณว่าขั้นนี้ deterministic — ไม่ใช่ความผิดพลาดของมัน

### 1.5 มีของที่ทำงานครบวงจรอยู่แล้ว แต่ถูกแยกไว้อีกสาย
skill `tpt-machining-quote` มีครบ: classify → อ่าน vector/scan → parts.json → estimate.py (3 rate + วัสดุ + finishing + calibration K) → ธงเตือนภาษาไทย ซึ่งคือขั้น 1, 4 (บางส่วน), 7, 8 ของ pipeline 8 ขั้น สิ่งที่ขาดจริงมีแค่ **ตัวแปลงผลอ่านแบบ → parts.json** (โค้ดล้วน) และ **หน้าจอให้คนยืนยัน** — ทั้งสองอย่างทำแล้วใน repo นี้

### ข้อสังเกตทางเทคนิคที่ต้องรู้
- **`temperature=0` ในคู่มือหลัก (`pipeline/llm.py` ตัวอย่าง) ใช้กับโมเดลรุ่นปัจจุบันไม่ได้แล้ว** — API ปฏิเสธ request ที่ส่ง temperature มา ความคงที่ต้องได้จาก (1) บันทึก prompt sha + โมเดล, (2) cache ผล, (3) double-read แล้ว diff — ไม่ใช่จากค่า sampling
- ความลึกในการคิดตั้งด้วย `output_config.effort` (ใน `.env`: `READ_EFFORT`)
- เปิด server-side fallback (`LLM_FALLBACKS=default`) ไว้ ถ้าโมเดลปฏิเสธคำขอ API จะลองโมเดลสำรองให้เอง และ `manifest.json` บันทึกว่าโมเดลไหนตอบจริง

---

## 2. Concept ที่แนะนำ: Quote-driven, human-in-the-loop, vertical slice

**เปลี่ยนโจทย์** จาก "AI อ่านแบบให้สมบูรณ์แล้ว quote อัตโนมัติ" → "AI กรอกใบประเมินล่วงหน้า, คนยืนยัน, โค้ดคิดราคา"

ตัวชี้วัดหลักเปลี่ยนจาก feature recall → **เวลาคนตรวจต่อ 1 แบบ** และ **% ราคาคลาด** (แยกเป็น "อ่านผิด→ราคา" กับ "โมเดลราคา→ราคาจริง" ไม่ปนกัน)

### สัญญากลาง: `QuoteSpec` (`pipeline/schemas.py`)
= schema `parts.json` ของ skill + **evidence ต่อ field** (`source`: text_layer / vision / rule / human, `raw_text`, `confidence`, `note`)
- ฝั่งอ่านแบบทั้งหมดมีหน้าที่เดียว: เติม QuoteSpec
- ฝั่งราคารับแค่ QuoteSpec
- PartSpec เต็ม (feature list ที่ทำมา) ยังเก็บเป็น "หลักฐาน" ให้คนตรวจ แต่ไม่ใช่ประตูที่ต้องสมบูรณ์ก่อนไปต่อ

### สถาปัตยกรรม v2 — จาก 8 ขั้นเหลือ 6, AI แค่ 2 จุด

| ขั้น | ใครทำ | ไฟล์ |
|---|---|---|
| 1. Ingest + classify + เดา template ลูกค้า | โค้ด | `pipeline/s1_ingest.py`, `config/customers.json` |
| 2a. VECTOR: title block + hole table จาก text layer | โค้ด | `pipeline/s2_vector.py` |
| 2b. Vision: เติมช่องว่าง (สัญลักษณ์ที่หาย, ด้านที่ต้องเข้า tool, notes) / SCAN: อ่านทั้งหมด | **AI** | `pipeline/s2_vision.py` + prompt v3 ของคุณ |
| 3. Assemble QuoteSpec: นับ op, join by tag, merge, เสนอ setup | โค้ด (+**AI** เฉพาะเศษ) | `pipeline/s3_assemble.py`, `config/feature_map.json` |
| 4. Validate → block / warn / info + risk premium | โค้ด | `pipeline/s4_validate.py` |
| 5. Human checkpoint | คน | `app.py` (Streamlit) |
| 6. ราคา | โค้ด | `pipeline/s6_price.py` (= estimate.py ทุกบาท) |

**เลื่อนออกไป:**
- **Process planning agent** — feature-count model ไม่ต้องใช้ process plan; ทำเมื่อ eval ชี้ว่างานหมวดไหน (mould / pocket ลึก / กลึงหนัก) โมเดลนี้พัง
- **Report agent** — ใช้ข้อความจากโค้ดก่อน (ธงเตือนภาษาไทยมีอยู่แล้ว)

### ไอเดียเสริมที่คุ้มมาก
1. **เปิดดู zip/7z/rar 10–20 ไฟล์ (จาก 469)** — ถ้ามี DXF/STEP ในสัดส่วนสูง นับรูด้วย `ezdxf` ได้แม่นแบบ deterministic ใช้แทน vision ได้ทั้งลูกค้า ลงแรง 1–2 ชม. แต่อาจเปลี่ยนกลยุทธ์ทั้งหมด
2. **เริ่มเก็บเวลาจริง (check sheet) ตั้งแต่วันนี้** — ค่าคงที่ใน shop_profile เป็นค่ากลางอุตสาหกรรม ±20% ความคลาดจาก calibration อาจใหญ่กว่าความคลาดจากการอ่านแบบ และไม่ต้องใช้ AI เลย
3. **Similar-job lookup** (Phase 3 เมื่อมี ≥30 งานที่รู้ราคา) — โชว์ราคางานเก่าที่คล้ายกันข้างราคาที่คำนวณ งาน jig ของ Pioneer (TK-26xx) น่าจะเป็นตระกูลเดียวกันเยอะ
4. **Summit ใช้โหมด "กรอกเอง" ใน app ได้ทันที** — แม้ AI ยังอ่านสแกนไม่ดี ก็ได้ใบประเมินมาตรฐาน + ราคาที่คงที่ และทุกใบที่กรอกกลายเป็น truth สำหรับ eval

---

## 3. Roadmap (มีเกณฑ์ผ่านทุกเฟส)

### Phase 0 — รวมศูนย์ + freeze (0.5–1 วัน) ← เริ่มตรงนี้
- [ ] คัดลอก `feature_reader.md`, `table_reader.md`, `reconciler.md` (v3) จาก `D:\AI\MD file\` → `prompts/` แล้ว commit
- [ ] (ถ้ามี) `title_reader.md` → `prompts/`
- [ ] PDF no3 / no4 (+ Summit 1–2 ไฟล์) → `samples/` (ไม่เข้า git)
- [ ] เทียบ enum `feature_type` ใน `reconciler.md` กับ `config/feature_map.json`
- [ ] `cp .env.example .env` ใส่ API key + ชื่อโมเดล
- [ ] **หยุดเพิ่มกฎใน prompt จนกว่า Phase 1 เสร็จ**
- **เกณฑ์ผ่าน:** `python -m pipeline.run samples/no3.pdf` ได้ `manifest.json` ที่มี prompt sha; รันซ้ำด้วย `--no-cache` แล้ว `python eval/run_eval.py --diff RUN_A RUN_B` รายงานความต่างออกมาได้ (ไม่ต้องเดาว่ารันด้วย prompt ไหน)

### Phase 1 — Vertical slice กับ Pioneer vector (2–4 วัน)
- [ ] รัน no3 / no4 → ตรวจใน `streamlit run app.py` → บันทึก
- [ ] ถ้า output ของ reconciler ไม่ตรงกับที่ `s3_assemble.hole_from_feature()` คาด ให้แก้ฟังก์ชันนั้นที่เดียว
- [ ] `python eval/run_eval.py --promote runs/<run> no3` สร้าง truth ตัวแรก
- [ ] เทียบราคาที่ได้กับราคาที่ TPT เคยเสนอจริง (ถ้าหาเจอ ใส่ `quoted_price`)
- **เกณฑ์ผ่าน:** no3, no4 ออกราคาได้ ใช้เวลาคนตรวจ < 5 นาที/แบบ (`review_seconds` ใน corrections.json)

### Phase 2 — Eval + calibration (1–2 สัปดาห์ ขนานกับงานร้าน)
- [ ] รวบรวม 10–20 แบบเก่าที่หาราคาเจอ (คละ vector/scan, กัด/กลึง) เข้า `eval/golden/`
- [ ] check sheet เวลาจริง → ใส่ `actual_minutes` → ปรับ `shop_calibration_K`
- **เกณฑ์ผ่าน:** มี baseline ของ `reading_impact_pct` และ `model_error_pct` และจัดอันดับแหล่งความคลาดได้

### Phase 3 — แก้ตามที่ eval บอก (ไม่ใช่ตามที่เจอ)
- จัดลำดับด้วย (ผลต่อราคา × ความถี่): Summit scan, groove, hatch legend, ฯลฯ
- Similar-job lookup, shadow mode กับ RFQ จริง

### Phase 4 — Process planning agent
เฉพาะหมวดงานที่ eval พิสูจน์แล้วว่า feature-count model ไม่พอ

### งานค้าง 3 ข้อจากไฟล์สถานะ
| งานค้าง | ทำอย่างไรตอนนี้ |
|---|---|
| เช็ค path prompt ที่ Claude Code ใช้ | หมดไปเอง: prompt อ่านจาก `prompts/` ที่เดียว + sha อยู่ใน manifest |
| รัน no3/no4 ซ้ำด้วย v3 | รันผ่าน `pipeline.run` → เป็น regression baseline ตัวแรก |
| ทดสอบ Summit ครั้งแรก | smoke test 1 แบบแบบ timebox (ไม่ tune prompt) เพื่อวัดขนาดช่องว่าง แล้วเข้าคิว Phase 3; ระหว่างนี้ quote Summit ด้วยโหมดกรอกเอง |

---

## 4. ของที่สร้างแล้วใน repo นี้

```
pipeline/schemas.py      QuoteSpec + Evidence + Flag
pipeline/prompts.py      อ่าน prompt จาก prompts/ เท่านั้น + sha (normalize CRLF)
pipeline/llm.py          เรียก API ตรง, retry JSON, cache, refusal/fallback, meta
pipeline/s1_ingest.py    classify (VECTOR/SCAN/MIXED), render, tiles, เดา template ด้วยโค้ด
pipeline/s2_vector.py    parse_vector.py + เก็บชื่อ tag ต่อกลุ่ม
pipeline/s2_vision.py    รัน prompt ของคุณ (ข้ามตัวที่ยังไม่มี)
pipeline/s3_assemble.py  นับ op, join_by_tag, merge (text layer ชนะ, ขัดกัน = conflict), เสนอ setup
pipeline/s4_validate.py  block/warn/info + risk premium ตาม shop_profile (เกินเพดาน = ห้าม auto-quote)
pipeline/s6_price.py     estimate.py แบบ import ได้ — test บังคับให้ตรงต้นฉบับทุกบาท
pipeline/run.py          CLI: บันทึกทุกขั้นลง runs/<file>-<time>/
app.py                   Streamlit: ภาพแบบ | field + หลักฐาน + ยืนยัน | ธง | ราคา | บันทึก corrections
eval/run_eval.py         คะแนนต่อเคส, --diff สองรัน, --promote run → truth
config/                  shop_profile, tap_drill, customers, feature_map
tests/                   29 tests ไม่ต้องใช้ API key / แบบจริง
```

### วิธีใช้
```bash
pip install -r requirements.txt
cp .env.example .env                                      # ใส่ key + ชื่อโมเดล
python -m pipeline.run samples/no3.pdf --vector-only      # ไม่เรียก AI
python -m pipeline.run samples/no3.pdf                    # vector + vision (ใช้ prompts/)
streamlit run app.py                                      # ตรวจ ยืนยัน บันทึก
python eval/run_eval.py --promote runs/<run> no3          # ทำ truth
python eval/run_eval.py                                   # คะแนน
pytest                                                    # test ทั้งหมด
```

### หลักที่ต้องยึดต่อจากนี้
- AI ทำเฉพาะงานตีความ; อะไรที่เขียนเป็น if/else ได้ ให้อยู่ในโค้ด
- **ห้ามเอาสคริปต์มาแทนการเรียกโมเดลในขั้น vision** — แต่ขั้นที่เป็นกฎตายตัว (join, นับ op) ต้องเป็นโค้ดตั้งแต่แรก
- แก้ prompt = commit + `python eval/run_eval.py` ก่อนลองเคสใหม่
- feature ที่ไม่รู้จัก → `leftovers` → block ราคา; ห้ามทิ้งเงียบ
- ตัวเลขที่ไม่ได้มาจาก text layer และยังไม่มีคนยืนยัน → ไม่ถึงราคา

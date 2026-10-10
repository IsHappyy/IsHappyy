# prompts/

ที่เดียวที่ pipeline อ่าน prompt — ไม่มี path อื่น (`pipeline/prompts.py`)

วางไฟล์ v3 จาก `D:\AI\MD file\` ที่นี่ แล้ว commit:

| ไฟล์ | ใช้ที่ | ถ้าไม่มี |
|---|---|---|
| `title_reader.md` | `s2_vision` | ข้าม (vector PDF ใช้ title block จาก text layer แทน) |
| `feature_reader.md` | `s2_vision` | ข้าม |
| `table_reader.md` | `s2_vision` | ข้าม (vector PDF ใช้ hole table จาก text layer แทน) |
| `reconciler.md` | `s2_vision` | ข้าม; ใช้ผล feature_reader ตรง ๆ |

กติกา:
- ทุกการรันบันทึก `prompt_sha` (12 ตัวแรกของ sha256) ลง `runs/<run>/manifest.json` — ตอบได้เสมอว่าผลไหนมาจาก prompt เวอร์ชันไหน
- แก้ prompt = commit ใหม่ + รัน regression (`python eval/run_eval.py`) ก่อนลองเคสใหม่
- คลังสัญลักษณ์ที่ใช้ร่วมกันหลาย prompt: ถ้าจะแยกเป็นไฟล์กลาง ให้ทำใน PR เดียวกันทุก prompt ที่อ้างถึง
- `config/feature_map.json` ต้องมีทุกค่าใน enum `feature_type` ของ `reconciler.md` — ค่าที่ไม่มีจะไปอยู่ `leftovers` และ block ราคา
- ถ้า output schema ของ reconciler ต่างจากที่ `pipeline/s3_assemble.py::hole_from_feature` คาดไว้ ให้แก้ฟังก์ชันนั้นที่เดียว

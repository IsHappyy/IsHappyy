# eval/golden — คำตอบที่ถูกต้อง (truth)

หนึ่งโฟลเดอร์ต่อหนึ่งแบบ: `eval/golden/<case>/truth.json`

```json
{
  "file": "no3.pdf",
  "quotespec": { "material": "STEEL_MILD", "t": 12, "L": 200, "W": 150, "qty": 2, "setups": 2,
                 "tolerance": "h7", "finish": "black_oxide",
                 "ops": { "drill": 8, "counterbore": 4, "tap_small": 2, "ream": 2 } },
  "quoted_price": 4500,
  "won": true,
  "actual_minutes": { "machine": 55, "hand": 20, "prep": 60 }
}
```

- `file` ต้องตรงกับชื่อไฟล์ที่รันด้วย `python -m pipeline.run` (ใช้จับคู่กับผลรันล่าสุด)
- `quotespec` = ค่าที่คนยืนยันแล้ว (schema เดียวกับ `pipeline/schemas.py::QuoteSpec`)
- `quoted_price` / `won` / `actual_minutes` ไม่บังคับ — ใส่เมื่อหาเจอ เพราะราคาเก่ากระจัดกระจาย
  - `quoted_price` ใช้วัด "โมเดลราคาคลาดเท่าไร" แยกจาก "อ่านแบบผิดเท่าไร"
  - `actual_minutes` ใช้ปรับ `shop_calibration_K` (ดู references/time_model.md ใน skill)

วิธีสร้างเร็วที่สุด: รัน pipeline → ยืนยันใน `streamlit run app.py` → 

```bash
python eval/run_eval.py --promote runs/<run-dir> no3
```

แบบลูกค้าเป็นความลับ — เก็บ PDF ไว้ใน `samples/` (ไม่เข้า git) ส่วน truth.json เป็นตัวเลขอย่างเดียว

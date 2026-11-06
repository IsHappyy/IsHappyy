// เซิร์ฟเวอร์บอร์ดงาน Jig สำหรับวงแลนในโรงงาน
// ใช้แค่ของที่มากับ Node 24 (http, sqlite, crypto) ไม่ต้อง npm install
//
//   node server.mjs                      เปิดเซิร์ฟเวอร์ (พอร์ต 8080 หรือตาม PORT)
//   node server.mjs import <โฟลเดอร์>      นำเข้าเอกสารจากโฟลเดอร์ jigs/ parts/ orders/ logs/
//   node server.mjs user <ชื่อผู้ใช้> <role> [ชื่อที่แสดง]   สร้างหรือรีเซ็ตผู้ใช้ รหัสใหม่เขียนลง data/
//   node server.mjs backup               สำรองฐานข้อมูลทันที
import http from "node:http";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { DatabaseSync } from "node:sqlite";
import { randomBytes, scryptSync, timingSafeEqual } from "node:crypto";

const ROOT = path.dirname(fileURLToPath(import.meta.url));
const PUBLIC = path.join(ROOT, "public");
const DATA = path.join(ROOT, "data");
const BACKUPS = path.join(DATA, "backups");
const PORT = Number(process.env.PORT || 8080);
const KEEP_BACKUPS = 30;
const SESSION_DAYS = 30;
const MAX_BODY = 256 * 1024;

const COLS = new Set(["jigs", "parts", "orders", "logs"]);
const ID_RE = /^[A-Za-z0-9_\-.~:@+]{1,200}$/;
const USER_RE = /^[a-z0-9._-]{2,40}$/;
const ROLES = ["viewer", "contributor", "editor", "admin"];
const rank = (role) => ROLES.indexOf(role);

fs.mkdirSync(BACKUPS, { recursive: true });
const db = new DatabaseSync(path.join(DATA, "jigboard.db"));
db.exec(`
  PRAGMA journal_mode = WAL;
  CREATE TABLE IF NOT EXISTS docs (
    col TEXT NOT NULL, id TEXT NOT NULL, body TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 1, updated_at TEXT NOT NULL, updated_by TEXT,
    PRIMARY KEY (col, id)
  );
  -- ทุกการเขียนถูกเก็บไว้ที่นี่ ใช้ตรวจย้อนหลังหรือกู้เอกสารที่แก้ผิด
  CREATE TABLE IF NOT EXISTS history (
    seq INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT NOT NULL, username TEXT,
    col TEXT NOT NULL, id TEXT NOT NULL, op TEXT NOT NULL, body TEXT
  );
  CREATE TABLE IF NOT EXISTS users (
    username TEXT PRIMARY KEY, name TEXT NOT NULL, role TEXT NOT NULL,
    pw TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL
  );
  CREATE TABLE IF NOT EXISTS sessions (
    token TEXT PRIMARY KEY, username TEXT NOT NULL, expires TEXT NOT NULL
  );
`);

const now = () => new Date().toISOString();
const q = {
  allDocs: db.prepare("SELECT col, id, body FROM docs"),
  countDocs: db.prepare("SELECT COUNT(*) n FROM docs"),
  upsert: db.prepare(`INSERT INTO docs (col, id, body, updated_at, updated_by) VALUES (?, ?, ?, ?, ?)
    ON CONFLICT (col, id) DO UPDATE SET body = excluded.body, version = version + 1,
      updated_at = excluded.updated_at, updated_by = excluded.updated_by`),
  del: db.prepare("DELETE FROM docs WHERE col = ? AND id = ?"),
  hist: db.prepare("INSERT INTO history (at, username, col, id, op, body) VALUES (?, ?, ?, ?, ?, ?)"),
  user: db.prepare("SELECT * FROM users WHERE username = ?"),
  users: db.prepare("SELECT username, name, role, active, created_at FROM users ORDER BY created_at"),
  countUsers: db.prepare("SELECT COUNT(*) n FROM users"),
  countAdmins: db.prepare("SELECT COUNT(*) n FROM users WHERE role = 'admin' AND active = 1"),
  insertUser: db.prepare("INSERT INTO users (username, name, role, pw, active, created_at) VALUES (?, ?, ?, ?, 1, ?)"),
  updateUser: db.prepare("UPDATE users SET name = ?, role = ?, active = ? WHERE username = ?"),
  setPw: db.prepare("UPDATE users SET pw = ? WHERE username = ?"),
  session: db.prepare("SELECT s.token, s.expires, u.* FROM sessions s JOIN users u ON u.username = s.username WHERE s.token = ?"),
  addSession: db.prepare("INSERT INTO sessions (token, username, expires) VALUES (?, ?, ?)"),
  dropSession: db.prepare("DELETE FROM sessions WHERE token = ?"),
  dropUserSessions: db.prepare("DELETE FROM sessions WHERE username = ?"),
  purgeSessions: db.prepare("DELETE FROM sessions WHERE expires < ?"),
};

/* ---------- รหัสผ่าน ---------- */
function hashPw(pw) {
  const salt = randomBytes(16);
  return `scrypt$${salt.toString("hex")}$${scryptSync(pw, salt, 64).toString("hex")}`;
}
function checkPw(pw, stored) {
  const [, salt, hash] = String(stored).split("$");
  if (!salt || !hash) return false;
  const a = scryptSync(pw, Buffer.from(salt, "hex"), 64), b = Buffer.from(hash, "hex");
  return a.length === b.length && timingSafeEqual(a, b);
}
const newPassword = () => randomBytes(9).toString("base64url");

// ตั้งผู้ใช้หรือรีเซ็ตรหัส แล้วเขียนรหัสลงไฟล์ใน data/ ให้ผู้ดูแลเปิดอ่านเอง ไม่พิมพ์ออกหน้าจอ
function setUserWithNewPassword(username, role, name) {
  const pw = newPassword();
  if (q.user.get(username)) {
    const u = q.user.get(username);
    q.updateUser.run(name || u.name, role || u.role, 1, username);
    q.setPw.run(hashPw(pw), username);
    q.dropUserSessions.run(username);
  } else q.insertUser.run(username, name || username, role, hashPw(pw), now());
  const file = path.join(DATA, `password-${username}.txt`);
  fs.writeFileSync(file, `ผู้ใช้: ${username}\nรหัสผ่านชั่วคราว: ${pw}\n\nเข้าระบบแล้วเปลี่ยนรหัสที่เมนูชื่อผู้ใช้ จากนั้นลบไฟล์นี้ทิ้ง\n`, "utf8");
  return file;
}

/* ---------- สำรองข้อมูล ---------- */
function backup(tag = "") {
  const d = new Date();
  const stamp = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
  const file = path.join(BACKUPS, `jigboard-${stamp}${tag}.db`);
  if (fs.existsSync(file)) fs.rmSync(file);
  db.exec(`VACUUM INTO '${file.replace(/'/g, "''")}'`);
  const old = fs.readdirSync(BACKUPS).filter((f) => /^jigboard-\d{4}-\d{2}-\d{2}.*\.db$/.test(f)).sort();
  for (const f of old.slice(0, Math.max(0, old.length - KEEP_BACKUPS))) fs.rmSync(path.join(BACKUPS, f));
  return file;
}

/* ---------- นำเข้า ---------- */
function importDir(dir) {
  let n = 0;
  db.exec("BEGIN");
  try {
    for (const col of COLS) {
      const cdir = path.join(dir, col);
      if (!fs.existsSync(cdir)) continue;
      for (const f of fs.readdirSync(cdir).filter((x) => x.endsWith(".json"))) {
        const id = f.slice(0, -5).replace(/@/g, "~"); // ArtifactData เขียน ~ เป็น @ ในชื่อไฟล์
        if (!ID_RE.test(id)) continue;
        const body = JSON.parse(fs.readFileSync(path.join(cdir, f), "utf8"));
        q.upsert.run(col, id, JSON.stringify(body), now(), "import");
        q.hist.run(now(), "import", col, id, "set", JSON.stringify(body));
        n++;
      }
    }
    db.exec("COMMIT");
  } catch (e) { db.exec("ROLLBACK"); throw e; }
  return n;
}

/* ---------- คำสั่งบรรทัดคำสั่ง ---------- */
const [cmd, ...args] = process.argv.slice(2);
if (cmd === "import") {
  const dir = path.resolve(args[0] || path.join(ROOT, "import"));
  if (q.countDocs.get().n && !args.includes("--force")) {
    console.log("ฐานข้อมูลมีข้อมูลอยู่แล้ว ถ้าต้องการนำเข้าทับให้เพิ่ม --force (ระบบจะสำรองไว้ก่อน)");
    process.exit(1);
  }
  if (q.countDocs.get().n) console.log("สำรองก่อนนำเข้า:", backup("-before-import"));
  console.log(`นำเข้าแล้ว ${importDir(dir)} เอกสาร จาก ${dir}`);
  process.exit(0);
}
if (cmd === "user") {
  const [username, role, ...name] = args;
  if (!USER_RE.test(username || "") || !ROLES.includes(role)) {
    console.log(`ใช้: node server.mjs user <ชื่อผู้ใช้ a-z0-9._-> <${ROLES.join("|")}> [ชื่อที่แสดง]`);
    process.exit(1);
  }
  console.log("เขียนรหัสผ่านชั่วคราวไว้ที่:", setUserWithNewPassword(username, role, name.join(" ")));
  process.exit(0);
}
if (cmd === "backup") { console.log("สำรองแล้ว:", backup("-manual")); process.exit(0); }

if (!q.countUsers.get().n) {
  const file = setUserWithNewPassword("admin", "admin", "ผู้ดูแลระบบ");
  console.log(`สร้างผู้ใช้ admin แล้ว รหัสผ่านชั่วคราวอยู่ในไฟล์ ${file}`);
}

/* ---------- HTTP ---------- */
const MIME = { ".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8",
  ".svg": "image/svg+xml", ".png": "image/png", ".webmanifest": "application/manifest+json", ".json": "application/json" };
const send = (res, status, body, headers = {}) => {
  const data = typeof body === "string" || Buffer.isBuffer(body) ? body : JSON.stringify(body);
  res.writeHead(status, { "content-type": typeof body === "object" && !Buffer.isBuffer(body) ? "application/json; charset=utf-8" : "text/plain; charset=utf-8",
    "cache-control": "no-store", ...headers });
  res.end(data);
};
const fail = (res, status, code, message) => send(res, status, { code, message });
function readJson(req) {
  return new Promise((resolve, reject) => {
    let size = 0; const chunks = [];
    req.on("data", (c) => { size += c.length; if (size > MAX_BODY) { reject(Object.assign(new Error("too_large"), { status: 413 })); req.destroy(); } else chunks.push(c); });
    req.on("end", () => { try { resolve(chunks.length ? JSON.parse(Buffer.concat(chunks).toString("utf8")) : {}); } catch { reject(Object.assign(new Error("bad_json"), { status: 400 })); } });
    req.on("error", reject);
  });
}
function cookie(req, name) {
  for (const part of String(req.headers.cookie || "").split(";")) {
    const [k, ...v] = part.trim().split("=");
    if (k === name) return decodeURIComponent(v.join("="));
  }
  return null;
}
function auth(req) {
  const t = cookie(req, "jb_session");
  if (!t) return null;
  const s = q.session.get(t);
  if (!s || !s.active || s.expires < now()) return null;
  return { token: t, username: s.username, name: s.name, role: s.role };
}
const meOf = (u) => ({ username: u.username, name: u.name, role: u.role,
  canWrite: rank(u.role) >= rank("contributor"), canEdit: rank(u.role) >= rank("editor"), isAdmin: u.role === "admin" });

// คนที่เปิดหน้าอยู่ (Server-Sent Events) รับการเปลี่ยนแปลงทันที
const streams = new Set();
function broadcast(event, data) {
  const msg = `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`;
  for (const res of streams) res.write(msg);
}
setInterval(() => { for (const res of streams) res.write(": ping\n\n"); }, 25000).unref();

function snapshot() {
  const out = { jigs: {}, parts: {}, orders: {}, logs: {} };
  for (const r of q.allDocs.all()) if (out[r.col]) out[r.col][r.id] = JSON.parse(r.body);
  return out;
}
function lanUrls() {
  const urls = [];
  for (const list of Object.values(os.networkInterfaces())) for (const a of list || [])
    if (a.family === "IPv4" && !a.internal && !a.address.startsWith("169.254")) urls.push(`http://${a.address}:${PORT}`);
  return urls;
}

const failedLogins = new Map();
async function handleApi(req, res, url) {
  const p = url.pathname;
  if (p === "/api/login" && req.method === "POST") {
    const { username = "", password = "" } = await readJson(req);
    const key = req.socket.remoteAddress + "|" + username;
    const f = failedLogins.get(key) || { n: 0, until: 0 };
    if (f.until > Date.now()) return fail(res, 429, "too_many", "ลองผิดหลายครั้ง รอสักครู่แล้วลองใหม่");
    const u = q.user.get(String(username).trim().toLowerCase());
    if (!u || !u.active || !checkPw(String(password), u.pw)) {
      f.n++; if (f.n >= 5) { f.until = Date.now() + 60_000; f.n = 0; }
      failedLogins.set(key, f);
      await new Promise((r) => setTimeout(r, 400));
      return fail(res, 401, "bad_login", "ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง");
    }
    failedLogins.delete(key);
    const token = randomBytes(32).toString("base64url");
    q.addSession.run(token, u.username, new Date(Date.now() + SESSION_DAYS * 864e5).toISOString());
    return send(res, 200, meOf(u), { "set-cookie": `jb_session=${token}; HttpOnly; SameSite=Lax; Path=/; Max-Age=${SESSION_DAYS * 86400}` });
  }
  const me = auth(req);
  if (!me) return fail(res, 401, "not_signed_in", "กรุณาเข้าสู่ระบบ");

  if (p === "/api/logout" && req.method === "POST") {
    q.dropSession.run(me.token);
    return send(res, 200, { ok: true }, { "set-cookie": "jb_session=; HttpOnly; SameSite=Lax; Path=/; Max-Age=0" });
  }
  if (p === "/api/me") return send(res, 200, { ...meOf(me), urls: lanUrls() });
  if (p === "/api/me/password" && req.method === "POST") {
    const { current = "", next = "" } = await readJson(req);
    const u = q.user.get(me.username);
    if (!checkPw(String(current), u.pw)) return fail(res, 400, "bad_password", "รหัสผ่านเดิมไม่ถูกต้อง");
    if (String(next).length < 8) return fail(res, 400, "weak_password", "รหัสผ่านใหม่ต้องยาวอย่างน้อย 8 ตัวอักษร");
    q.setPw.run(hashPw(String(next)), me.username);
    return send(res, 200, { ok: true });
  }
  if (p === "/api/stream") {
    res.writeHead(200, { "content-type": "text/event-stream; charset=utf-8", "cache-control": "no-store", connection: "keep-alive", "x-accel-buffering": "no" });
    res.write(`retry: 3000\nevent: snapshot\ndata: ${JSON.stringify(snapshot())}\n\n`);
    streams.add(res);
    req.on("close", () => streams.delete(res));
    return;
  }
  const m = p.match(/^\/api\/docs\/([^/]+)\/([^/]+)$/);
  if (m) {
    const col = decodeURIComponent(m[1]), id = decodeURIComponent(m[2]);
    if (!COLS.has(col) || !ID_RE.test(id)) return fail(res, 400, "invalid_argument", "ที่อยู่เอกสารไม่ถูกต้อง");
    if (req.method === "PUT") {
      if (rank(me.role) < rank("contributor")) return fail(res, 403, "invalid_argument", "บัญชีนี้มีสิทธิ์ดูอย่างเดียว");
      const body = await readJson(req);
      if (!body || typeof body !== "object" || Array.isArray(body)) return fail(res, 400, "invalid_argument", "ข้อมูลต้องเป็นออบเจกต์");
      const text = JSON.stringify(body);
      q.upsert.run(col, id, text, now(), me.username);
      q.hist.run(now(), me.username, col, id, "set", text);
      broadcast("change", { col, id, body });
      return send(res, 200, { ok: true });
    }
    if (req.method === "DELETE") {
      // ลบเอกสารเกิดตอนกู้ข้อมูลจากไฟล์เท่านั้น จึงจำกัดไว้ที่ Editor ขึ้นไป
      if (rank(me.role) < rank("editor")) return fail(res, 403, "invalid_argument", "ลบข้อมูลได้เฉพาะ Editor ขึ้นไป");
      q.del.run(col, id);
      q.hist.run(now(), me.username, col, id, "delete", null);
      broadcast("change", { col, id, body: null });
      return send(res, 200, { ok: true });
    }
  }
  if (p === "/api/users") {
    if (me.role !== "admin") return fail(res, 403, "forbidden", "เฉพาะผู้ดูแลระบบ");
    if (req.method === "GET") return send(res, 200, q.users.all());
    if (req.method === "POST") {
      const { username = "", name = "", role = "contributor", active = true, resetPassword = false } = await readJson(req);
      const un = String(username).trim().toLowerCase();
      if (!USER_RE.test(un)) return fail(res, 400, "bad_username", "ชื่อผู้ใช้ใช้ได้แค่ a-z 0-9 . _ - ยาว 2–40 ตัว");
      if (!ROLES.includes(role)) return fail(res, 400, "bad_role", "ระดับสิทธิ์ไม่ถูกต้อง");
      const existing = q.user.get(un);
      if (existing && existing.role === "admin" && (role !== "admin" || !active) && q.countAdmins.get().n <= 1)
        return fail(res, 400, "last_admin", "ต้องเหลือผู้ดูแลระบบอย่างน้อย 1 คน");
      let password = null;
      if (!existing) { password = newPassword(); q.insertUser.run(un, String(name).trim() || un, role, hashPw(password), now()); }
      else {
        q.updateUser.run(String(name).trim() || existing.name, role, active ? 1 : 0, un);
        if (!active) q.dropUserSessions.run(un);
        if (resetPassword) { password = newPassword(); q.setPw.run(hashPw(password), un); q.dropUserSessions.run(un); }
      }
      // รหัสชั่วคราวส่งกลับให้ผู้ดูแลเห็นครั้งเดียวบนหน้าจอ เพื่อนำไปบอกพนักงาน
      return send(res, 200, { ok: true, password });
    }
  }
  return fail(res, 404, "not_found", "ไม่พบ");
}

function serveStatic(req, res, url) {
  let rel = decodeURIComponent(url.pathname);
  if (rel === "/") rel = "/index.html";
  const file = path.normalize(path.join(PUBLIC, rel));
  if (!file.startsWith(PUBLIC + path.sep) || !fs.existsSync(file) || !fs.statSync(file).isFile()) return fail(res, 404, "not_found", "ไม่พบ");
  const type = MIME[path.extname(file)] || "application/octet-stream";
  res.writeHead(200, { "content-type": type, "cache-control": rel === "/index.html" ? "no-cache" : "max-age=3600" });
  fs.createReadStream(file).pipe(res);
}

const server = http.createServer(async (req, res) => {
  const url = new URL(req.url, "http://localhost");
  try {
    if (url.pathname.startsWith("/api/")) await handleApi(req, res, url);
    else serveStatic(req, res, url);
  } catch (e) {
    if (!res.headersSent) fail(res, e.status || 500, e.status === 413 ? "invalid_argument" : "server_error", e.status ? e.message : "เซิร์ฟเวอร์ผิดพลาด");
    if (!e.status) console.error(e);
  }
});

backup();
setInterval(() => { try { backup(); q.purgeSessions.run(now()); } catch (e) { console.error("สำรองไม่สำเร็จ", e); } }, 6 * 3600 * 1000).unref();

server.listen(PORT, "0.0.0.0", () => {
  console.log(`บอร์ดงาน Jig พร้อมใช้งาน`);
  console.log(`  เครื่องนี้:   http://localhost:${PORT}`);
  for (const u of lanUrls()) console.log(`  มือถือ/เครื่องอื่นในวง Wi-Fi เดียวกัน: ${u}`);
  console.log(`  ฐานข้อมูล:   ${path.join(DATA, "jigboard.db")}  (สำรองอัตโนมัติที่ ${BACKUPS})`);
});

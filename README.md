# ระบบจัดการค่าใช้จ่ายและการชำระเงินของกลุ่ม (Group Expense Manager)

FastAPI + PostgreSQL + Jinja2. รองรับ 2 สิทธิ์ผู้ใช้ (Admin / Member) แบ่งค่าใช้จ่ายรายเดือน
พร้อมยอดค้าง/เครดิตยกเดือน และระบบอนุมัติสลิปโอนเงิน

## โครงสร้างโปรเจกต์

```
project/
├── app/
│   ├── main.py            # FastAPI entrypoint, startup (สร้าง admin เริ่มต้น), health check
│   ├── models.py           # SQLAlchemy models
│   ├── schemas.py          # Pydantic schemas
│   ├── database.py         # engine/session
│   ├── auth.py              # password hashing (bcrypt), JWT cookie session, role guards
│   ├── config.py            # settings จาก environment variables
│   ├── services/
│   │   ├── calculation.py   # หัวใจของระบบ: หารเงิน, ปัดเศษ, ยอดค้าง/เครดิตยกเดือน
│   │   └── storage.py       # storage layer (local disk, พร้อมขยายเป็น S3)
│   ├── routers/              # API endpoints (auth, members, expenses, payments, slips, history, dashboard)
│   ├── templates/            # หน้าเว็บ Jinja2 (server-rendered)
│   └── static/                # CSS/JS
├── uploads/                   # ที่เก็บรูปสลิป (local)
├── migrations/001_init.sql     # schema อ้างอิง (ตารางถูกสร้างอัตโนมัติตอน startup อยู่แล้ว)
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── .env.example
└── README.md
```

## หลักการคำนวณสำคัญ

- **จำนวนผู้ร่วมจ่าย = Admin 1 คน + สมาชิกที่ Active ทั้งหมด** ในขณะที่สร้างค่าใช้จ่ายนั้น
- แต่ละค่าใช้จ่ายจะ **บันทึกสแนปช็อต** ของจำนวนผู้ร่วมจ่ายและยอดต่อคนไว้ถาวร — การเพิ่ม/ลบสมาชิกภายหลังจะไม่กระทบยอดของเดือนก่อนหน้า
- เงินทั้งหมดใช้ `Decimal` / PostgreSQL `NUMERIC(12,2)` ไม่ใช้ float
- กรณีหารไม่ลงตัว ส่วนที่เหลือ (เศษสตางค์) จะถูกกระจายทีละ 1 สตางค์ให้ผู้ร่วมจ่ายตามลำดับ username จนครบ ทำให้ผลรวมของทุกคนเท่ากับยอดรวมเป๊ะเสมอ (ตรวจสอบได้)
- เครดิตที่เกิดจากการโอนเกินจะถูก "ยกไปเดือนถัดไป" ครั้งเดียวตอนที่ระบบสร้างยอดของเดือนถัดไปเป็นครั้งแรก (เพื่อไม่ให้มีการคำนวณย้อนหลังที่ไม่สิ้นสุด)

## Run Local (Docker)

1. คัดลอกไฟล์ environment:
   ```bash
   cp .env.example .env
   ```
2. รันระบบ:
   ```bash
   docker compose up -d --build
   ```
3. เปิดเว็บที่ [http://localhost:8000](http://localhost:8000)
4. Login ด้วยบัญชี Admin เริ่มต้น (สร้างอัตโนมัติตอน startup):
   - Username: `dada`
   - Password: `123456`

   > แนะนำให้เปลี่ยนรหัสผ่านทันทีที่หน้า Profile หลัง Login ครั้งแรก

5. ตรวจสอบว่าระบบพร้อมใช้งาน:
   ```bash
   curl http://localhost:8000/health
   # {"status":"ok"}
   ```

### ทดสอบ workflow ทั้งหมด

1. Login ด้วย `dada` / `123456`
2. ไปที่ **Members** → เพิ่มสมาชิก (เช่น user01, user02)
3. ไปที่ **Expenses** → เพิ่มค่าใช้จ่าย (เช่น เดือนปัจจุบัน, "ค่า Internet", 3000 บาท) → ระบบคำนวณยอดต่อคนอัตโนมัติ
4. Logout แล้ว Login ด้วยบัญชีสมาชิกที่สร้างไว้
5. ไปที่ **Upload Slip** → อัปโหลดรูปสลิปพร้อมจำนวนเงิน
6. Login กลับมาด้วย `dada` → ไปที่ **Payment Slips** → กด **อนุมัติ**
7. ระบบจะคำนวณยอดค้าง/เครดิตอัตโนมัติ และแสดงผลในหน้า Dashboard และ History ของสมาชิกคนนั้น

## Deploy บน Render — ทีละขั้นตอน

### 1. เตรียม Repository

Push โค้ดทั้งหมด (ยกเว้นไฟล์ที่อยู่ใน `.gitignore`) ขึ้น GitHub/GitLab

### 2. สร้าง PostgreSQL Database บน Render

1. Render Dashboard → **New** → **PostgreSQL**
2. ตั้งชื่อ เช่น `expense-db` เลือก Region ให้ตรงกับ Web Service
3. สร้างเสร็จแล้ว คัดลอกค่า **Internal Database URL** (ใช้เชื่อมจาก Web Service ใน Region เดียวกัน — เร็วกว่าและไม่มีค่าใช้จ่ายด้าน bandwidth)

### 3. สร้าง Web Service

1. Render Dashboard → **New** → **Web Service** → เชื่อม Repository นี้
2. **Runtime**: Docker (Render จะตรวจพบ `Dockerfile` อัตโนมัติ)
3. **Region**: เดียวกับ Database
4. **Instance Type**: เลือกตามความเหมาะสม (Free/Starter สำหรับทดสอบ)

### 4. ตั้งค่า Environment Variables บน Render

ไปที่ Web Service → **Environment** แล้วเพิ่ม:

| Key | Value |
|---|---|
| `DATABASE_URL` | (วาง Internal Database URL จากขั้นตอนที่ 2) |
| `SECRET_KEY` | สุ่มค่ายาวๆ (เช่นจาก `openssl rand -hex 32`) |
| `APP_ENV` | `production` |
| `STORAGE_TYPE` | `local` |
| `UPLOAD_DIR` | `/app/uploads` |
| `DEFAULT_ADMIN_USERNAME` | `dada` |
| `DEFAULT_ADMIN_PASSWORD` | (**เปลี่ยนจาก 123456 เป็นรหัสผ่านที่ปลอดภัยก่อน deploy จริง**) |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `1440` |

**ห้ามใส่ Password ฐานข้อมูลจริงหรือ Secret ลง Git** — ตั้งค่าผ่านหน้า Environment ของ Render เท่านั้น

### 5. เพิ่ม Persistent Disk (สำหรับรูปสลิป)

Container บน Render เป็นแบบ ephemeral — ไฟล์ที่เขียนใน container จะหายเมื่อ deploy ใหม่หรือ restart
ดังนั้นต้องเพิ่ม **Persistent Disk**:

1. Web Service → **Disks** → **Add Disk**
2. Mount Path: `/app/uploads`
3. ขนาดตามความเหมาะสม (เริ่มที่ 1GB ก็เพียงพอสำหรับการทดสอบ)

> หากต้องการความทนทานสูงขึ้นในอนาคต ให้เปลี่ยนไปใช้ Object Storage (เช่น S3-compatible) โดย implement class ใหม่ใน `app/services/storage.py` ตาม interface `BaseStorage` — ระบบถูกออกแบบให้เปลี่ยน Storage ได้โดยไม่ต้องแก้ business logic

### 6. Health Check

ตั้งค่า **Health Check Path** เป็น `/health` (Render จะใช้ endpoint นี้ตรวจสอบว่า service พร้อมใช้งาน)

### 7. Deploy

กด **Create Web Service** — Render จะ build image จาก `Dockerfile` และรัน `uvicorn app.main:app` อัตโนมัติ
ตอน startup ระบบจะสร้างตารางฐานข้อมูล (ถ้ายังไม่มี) และสร้างบัญชี Admin เริ่มต้นให้อัตโนมัติ

### 8. ตรวจสอบหลัง Deploy

- เปิด URL ที่ Render ให้มา → ควรเจอหน้า Login
- `https://<your-app>.onrender.com/health` ควรตอบ `{"status":"ok"}`
- Login ด้วยบัญชี Admin ที่ตั้งไว้ใน Environment Variables แล้วเปลี่ยนรหัสผ่านทันทีที่หน้า Profile

## Security Checklist

- [x] Password hash ด้วย bcrypt ไม่เก็บ plain text
- [x] Session ผ่าน JWT ใน httponly cookie (`secure` เปิดอัตโนมัติเมื่อ `APP_ENV=production`)
- [x] แยกสิทธิ์ Admin/Member ทุก endpoint ที่จำเป็น
- [x] Member เข้าถึงได้เฉพาะข้อมูล/สลิปของตัวเอง (ตรวจสอบ ownership ทุกครั้งที่เข้าถึงไฟล์สลิป)
- [x] จำกัดชนิดไฟล์ (JPG/JPEG/PNG/WEBP) และขนาดไฟล์ (`MAX_UPLOAD_SIZE_MB`)
- [x] ป้องกัน path traversal ตอนเสิร์ฟไฟล์สลิป
- [x] ใช้ SQLAlchemy ORM (parameterized queries) ป้องกัน SQL Injection
- [x] Secret/Database URL อ่านจาก Environment Variables เท่านั้น
- [x] Global exception handlers คืน error message ที่เข้าใจง่าย ไม่ทำให้ระบบล่ม

## หมายเหตุ/ข้อจำกัดที่ทราบ (Known limitations)

- เครดิตจากเดือนก่อนหน้าจะถูก "ล็อก" เข้าสู่เดือนถัดไปในครั้งแรกที่ระบบคำนวณยอดของเดือนถัดไป
  (เช่น ตอนสร้างค่าใช้จ่ายแรกของเดือนนั้น) หากมีการอนุมัติสลิปเพิ่มเติมของเดือนก่อนหน้า
  **หลังจาก** เดือนถัดไปถูกคำนวณไปแล้ว เครดิตส่วนเพิ่มจะไม่ไหลย้อนไปเดือนถัดไปโดยอัตโนมัติ
  — Admin สามารถใช้ endpoint "แก้ไขยอดเงิน" (`POST /api/payments`) เพื่อปรับยอดด้วยตนเองในกรณีนี้
- ระบบอนุมัติสลิปแบบ manual โดย Admin เท่านั้น (ไม่มี auto-matching ยอดโอนกับ slip)
# YTPAYMENT

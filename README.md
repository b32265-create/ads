# 🐲 SHADOW ADS BOT (@ALL_SHADOWS_BOT)

Modern, High-Speed Telegram Auto-Ads, Account Hosting, Force Join & Marketing Bot built with **aiogram 3.x**, **Telethon**, and **SQLite (Async WAL Mode)**.

---

## 🚀 Features

1. **Dashboard Interface**:
   - Exact replica of the reference design with real-time statistics (Hosted Accounts, Ad status, Cycle Interval, Delay, Target, Cycles, Status, AI Reply).
2. **Account Hosting**:
   - Add Telegram accounts via **Phone Number + OTP (with 2FA support)** or **StringSession**.
   - Manage/view/remove hosted accounts at any time.
3. **Automated Ad Campaigns**:
   - Set custom Ad Message (supports formatted text, links, captions).
   - Set cycle intervals (1m, 5m, 10m, 30m, 1h, custom seconds).
   - Set message delay between posts (2s, 5s, 10s, 15s, custom seconds) to avoid FloodWait.
   - Switch targets between **Groups**, **Channels**, or **All**.
   - Exclude specific groups or channels.
   - Unlimited or custom cycle limits.
4. **Auto Join Public Groups**:
   - Automatically join batches of public groups across all hosted accounts with anti-flood delay.
5. **Multi-Channel Force Join (Admin Manageable)**:
   - Restrict bot access until users subscribe to mandatory channels.
   - Manage channels directly inside Telegram via `/admin`.
6. **Admin Panel (`/admin`)**:
   - Live system statistics (Total users, accounts, channels).
   - Mass Broadcast system with live progress tracker (text, photo, video, forwards).
   - Add/Remove force join channels.
7. **Lifetime Free & Fast Database**:
   - Asynchronous SQLite (`aiosqlite`) with **WAL mode** for ultra-high speed, zero maintenance, and unlimited queries without paying for cloud database tiers.

---

## 🛠️ Configuration (`.env`)

```ini
BOT_TOKEN=8802315206:AAHfAR2xU9ABMkgouoTrwDX_Z6tY_NKBpps
ADMIN_IDS=6799525497,8803073338
API_ID=37994485
API_HASH=d6ba6dceeeb984b0fe6d6a633ca1673e
DB_PATH=shadow_ads.db
```

---

## ▶️ Running the Bot

Double click `start.bat` or run:
```bash
.\venv\Scripts\python.exe main.py
```

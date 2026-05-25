# Notify Server

שרת WebSocket עם אימות מבוסס-session. המשתמש מתחבר בחיבור קבוע ושולח התראות
(`notifications`) בזמן אמת; השרת מאזין תמיד, שומר אותן ומחזיר `ack`.

## ארכיטקטורה

המערכת מפרידה בין שתי אחריות:

| שכבה | פרוטוקול | תפקיד |
|------|----------|-------|
| אימות | `PUT /auth/session` (REST) | בקשה חד-פעמית: username + password ← token |
| התראות | `WS /ws?token=...` (WebSocket) | חיבור קבוע: המשתמש דוחף notifications לשרת |

ה-`session` הוא הגשר: ה-`PUT` מנפיק `token`, וה-`token` פותח את ה-WebSocket.

```
client ──PUT /auth/session (user, pass)──▶ server
client ◀──────── { session_id, token } ──── server
client ──WS connect ?token=...──────────▶ server   (חיבור נשאר פתוח)
client ──{ type, message, data }────────▶ server
client ◀──────────────── { ack, ... } ──── server
```

## מבנה תיקיות

```
notify-server/
├── app/
│   ├── main.py                # FastAPI entrypoint + /health
│   ├── config.py              # הגדרות מבוססות-env
│   ├── schemas.py             # Pydantic models (auth + notifications)
│   ├── security.py            # bcrypt hashing + token generation
│   ├── store.py               # interfaces + מימוש in-memory (swappable)
│   ├── connection_manager.py  # ניהול חיבורי WebSocket חיים
│   └── routes.py              # endpoint של PUT + WebSocket
├── client/
│   └── test_client.py         # לקוח בדיקה ל-CLI
├── requirements.txt
└── .env.example
```

## הרצה

```bash
# 1. התקנה
pip install -r requirements.txt

# 2. הרצת השרת
uvicorn app.main:app --reload --port 8000

# 3. בטרמינל שני — לקוח הבדיקה
python client/test_client.py
```

משתמש דמו: `avi` / `secret123` (מוגדר ב-`store.py`).

## נקודות ל-production (השלבים הבאים)

- **Storage**: כרגע in-memory — נתונים נמחקים בכל restart. המימושים יושבים מאחורי
  `SessionStore` / `NotificationStore`, אז מחליפים ל-Redis (sessions) ו-Firestore
  (notifications) בלי לגעת בלוגיקה.
- **Push דו-כיווני**: `ConnectionManager.send_to_user()` כבר מוכן — כשתרצה שהשרת
  ידחוף התראות *למשתמש*, זה החיבור.
- **Scale**: מספר תהליכי uvicorn ידרשו Redis Pub/Sub כדי לסנכרן חיבורי WS בין worker-ים.
- **אבטחה**: rate-limit על ה-`PUT`, `wss://` (TLS) בפרוד, רענון token.

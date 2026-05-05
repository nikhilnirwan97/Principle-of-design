"""
db.py — Supabase client + graceful SQLite fallback
──────────────────────────────────────────────────
If SUPABASE_URL / SUPABASE_KEY are set in .env  → uses Supabase cloud.
Otherwise                                        → falls back to local SQLite.
"""
import os, sqlite3
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL    = os.getenv('SUPABASE_URL', '')
SUPABASE_KEY    = os.getenv('SUPABASE_KEY', '')
SUPABASE_BUCKET = os.getenv('SUPABASE_BUCKET', 'yamuna-reports')
USE_SUPABASE    = bool(SUPABASE_URL and SUPABASE_KEY and 'xxxxxxxxxxx' not in SUPABASE_URL)

_supabase = None

def get_supabase():
    global _supabase
    if _supabase is None:
        from supabase import create_client
        _supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    return _supabase


# ── STORAGE ──────────────────────────────────────────────────────────────────

def upload_photo(file_bytes: bytes, filename: str, content_type: str = 'image/jpeg') -> str:
    """Upload image to Supabase Storage; return public URL. Falls back to local save."""
    if USE_SUPABASE:
        sb = get_supabase()
        path = f"reports/{filename}"
        try:
            sb.storage.from_(SUPABASE_BUCKET).upload(
                path, file_bytes,
                {"content-type": content_type, "upsert": "true"}
            )
            return sb.storage.from_(SUPABASE_BUCKET).get_public_url(path)
        except Exception as e:
            print(f"[Storage] Upload failed: {e}")
            return ''
    else:
        # Local fallback
        from flask import current_app
        import time
        local_path = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
        with open(local_path, 'wb') as f:
            f.write(file_bytes)
        return f"/static/uploads/{filename}"


# ── DATABASE ──────────────────────────────────────────────────────────────────
# All functions return plain dicts for consistency.

class SupabaseDB:
    def __init__(self):
        self.sb = get_supabase()

    def _safe(self, query):
        """Execute a Supabase query and return data list, or raise with clean message."""
        try:
            res = query.execute()
            return res.data
        except Exception as e:
            msg = str(e)
            if 'does not exist' in msg or '42P01' in msg:
                raise RuntimeError(
                    'Supabase tables not found. Please run supabase_schema.sql '
                    'in your Supabase SQL Editor first.'
                ) from e
            raise

    # ── Users ────────────────────────────────────────────────────────────────
    def create_user(self, name, email, pw_hash, role='citizen'):
        try:
            data = self._safe(
                self.sb.table('users').insert(
                    {'name': name, 'email': email, 'password': pw_hash, 'role': role}
                )
            )
            return data[0] if data else None
        except Exception as e:
            if 'duplicate' in str(e).lower() or '23505' in str(e):
                raise sqlite3.IntegrityError('Email already registered')
            raise

    def get_user_by_email(self, email):
        """Returns user dict or None — uses maybe_single() to avoid 404 on no match."""
        try:
            res = self.sb.table('users').select('*').eq('email', email)\
                         .maybe_single().execute()
            return res.data  # None if not found
        except Exception as e:
            msg = str(e)
            if 'does not exist' in msg or '42P01' in msg:
                raise RuntimeError(
                    'Supabase tables missing. Run supabase_schema.sql in your project SQL Editor.'
                ) from e
            raise

    def get_user_by_id(self, uid):
        try:
            res = self.sb.table('users').select('*').eq('id', uid)\
                         .maybe_single().execute()
            return res.data
        except Exception:
            return None

    # ── Reports ───────────────────────────────────────────────────────────────
    def insert_report(self, data: dict):
        rows = self._safe(self.sb.table('reports').insert(data))
        return rows[0] if rows else None

    def get_reports(self, status=None, user_id=None):
        try:
            q = self.sb.table('reports').select('*, users(name)').order('id', desc=True)
            if status and status != 'ALL':
                q = q.eq('status', status)
            if user_id:
                q = q.eq('user_id', user_id)
            return q.execute().data or []
        except Exception:
            return []

    def update_report_status(self, rid, status):
        self.sb.table('reports').update({'status': status}).eq('id', rid).execute()

    # ── Readings ──────────────────────────────────────────────────────────────
    def insert_reading(self, data: dict):
        try:
            self.sb.table('readings').insert(data).execute()
        except Exception as e:
            print(f'[Readings] {e}')

    def get_readings(self, station_id, limit=15):
        try:
            res = self.sb.table('readings').select('*')\
                    .eq('station_id', station_id)\
                    .order('id', desc=True).limit(limit).execute()
            return list(reversed(res.data or []))
        except Exception:
            return []

    # ── Alerts ────────────────────────────────────────────────────────────────
    def get_alerts(self):
        try:
            return self.sb.table('alerts').select('*')\
                       .order('id', desc=True).execute().data or []
        except Exception:
            return []

    def insert_alert(self, data: dict):
        self.sb.table('alerts').insert(data).execute()

    # ── Profile stats ─────────────────────────────────────────────────────────
    def profile_stats(self, user_id):
        rows    = self.get_reports(user_id=user_id)
        total    = len(rows)
        pending  = sum(1 for r in rows if r.get('status') == 'PENDING')
        resolved = sum(1 for r in rows if r.get('status') == 'RESOLVED')
        return {'total': total, 'pending': pending, 'resolved': resolved,
                'impact': total * 35 + resolved * 50}


class SQLiteDB:
    """Local fallback — matches SupabaseDB interface."""
    def __init__(self, db_path):
        self.db_path = db_path
        self._init()

    def _conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init(self):
        conn = self._conn()
        c = conn.cursor()
        c.executescript('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL, email TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL, role TEXT DEFAULT "citizen",
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER, type TEXT NOT NULL, station TEXT NOT NULL,
                location TEXT NOT NULL, description TEXT,
                severity TEXT DEFAULT "MEDIUM", photo_url TEXT DEFAULT "",
                status TEXT DEFAULT "PENDING", lat REAL, lng REAL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT, station TEXT, parameter TEXT,
                value TEXT, threshold TEXT, level TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS readings (
                id INTEGER PRIMARY KEY AUTOINCREMENT, station_id INTEGER,
                bod REAL, do_level REAL, ph REAL, turbidity REAL,
                nitrates REAL, phosphates REAL, score INTEGER,
                recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        ''')
        # Seed alerts
        c.execute('SELECT COUNT(*) FROM alerts')
        if c.fetchone()[0] == 0:
            c.executemany('INSERT INTO alerts (station,parameter,value,threshold,level) VALUES (?,?,?,?,?)', [
                ('Nizamuddin','BOD','98 mg/L','>30 mg/L','CRITICAL'),
                ('Wazirabad','Dissolved O₂','1.2 mg/L','<4 mg/L','CRITICAL'),
                ('Okhla','Turbidity','165 NTU','>100 NTU','HIGH'),
                ('Palla','pH','6.3','>6.5','MODERATE'),
            ])
        conn.commit()
        conn.close()

    def _row(self, r): return dict(r) if r else None
    def _rows(self, rs): return [dict(r) for r in rs]

    def create_user(self, name, email, pw_hash, role='citizen'):
        conn = self._conn()
        try:
            cur = conn.cursor()
            cur.execute('INSERT INTO users (name,email,password,role) VALUES (?,?,?,?)', (name,email,pw_hash,role))
            conn.commit()
            uid = cur.lastrowid
            conn.close()
            return {'id': uid, 'name': name, 'email': email, 'role': role}
        except sqlite3.IntegrityError:
            conn.close()
            raise

    def get_user_by_email(self, email):
        conn = self._conn()
        r = conn.execute('SELECT * FROM users WHERE email=?', (email,)).fetchone()
        conn.close()
        return self._row(r)

    def get_user_by_id(self, uid):
        conn = self._conn()
        r = conn.execute('SELECT * FROM users WHERE id=?', (uid,)).fetchone()
        conn.close()
        return self._row(r)

    def insert_report(self, data):
        conn = self._conn()
        cur = conn.cursor()
        cur.execute('''INSERT INTO reports (user_id,type,station,location,description,severity,photo_url,lat,lng)
                       VALUES (:user_id,:type,:station,:location,:description,:severity,:photo_url,:lat,:lng)''', data)
        conn.commit()
        rid = cur.lastrowid
        conn.close()
        return {**data, 'id': rid}

    def get_reports(self, status=None, user_id=None):
        conn = self._conn()
        if user_id:
            rs = conn.execute('SELECT r.*,u.name as reporter FROM reports r LEFT JOIN users u ON r.user_id=u.id WHERE r.user_id=? ORDER BY r.id DESC', (user_id,)).fetchall()
        elif status and status != 'ALL':
            rs = conn.execute('SELECT r.*,u.name as reporter FROM reports r LEFT JOIN users u ON r.user_id=u.id WHERE r.status=? ORDER BY r.id DESC', (status,)).fetchall()
        else:
            rs = conn.execute('SELECT r.*,u.name as reporter FROM reports r LEFT JOIN users u ON r.user_id=u.id ORDER BY r.id DESC').fetchall()
        conn.close()
        return self._rows(rs)

    def update_report_status(self, rid, status):
        conn = self._conn()
        conn.execute('UPDATE reports SET status=? WHERE id=?', (status, rid))
        conn.commit()
        conn.close()

    def insert_reading(self, data):
        conn = self._conn()
        conn.execute('''INSERT INTO readings (station_id,bod,do_level,ph,turbidity,nitrates,phosphates,score)
                        VALUES (:station_id,:bod,:do_level,:ph,:turbidity,:nitrates,:phosphates,:score)''', data)
        conn.commit()
        conn.close()

    def get_readings(self, station_id, limit=15):
        conn = self._conn()
        rs = conn.execute('SELECT * FROM readings WHERE station_id=? ORDER BY id DESC LIMIT ?', (station_id, limit)).fetchall()
        conn.close()
        return list(reversed(self._rows(rs)))

    def get_alerts(self):
        conn = self._conn()
        rs = conn.execute('SELECT * FROM alerts ORDER BY id DESC').fetchall()
        conn.close()
        return self._rows(rs)

    def insert_alert(self, data):
        conn = self._conn()
        conn.execute('INSERT INTO alerts (station,parameter,value,threshold,level) VALUES (:station,:parameter,:value,:threshold,:level)', data)
        conn.commit()
        conn.close()

    def profile_stats(self, user_id):
        rows = self.get_reports(user_id=user_id)
        total = len(rows)
        pending  = sum(1 for r in rows if r['status'] == 'PENDING')
        resolved = sum(1 for r in rows if r['status'] == 'RESOLVED')
        return {'total': total, 'pending': pending, 'resolved': resolved,
                'impact': total * 35 + resolved * 50}


def get_db():
    """Return the active DB instance (Supabase or SQLite)."""
    if USE_SUPABASE:
        return SupabaseDB()
    else:
        BASE_DIR = os.path.dirname(os.path.abspath(__file__))
        return SQLiteDB(os.path.join(BASE_DIR, 'yamuna.db'))

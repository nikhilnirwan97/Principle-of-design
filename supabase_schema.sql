-- ══════════════════════════════════════════════════════════════════════
--  YamunaWatch — Supabase SQL Schema
--  Run this in: Supabase Dashboard → SQL Editor
-- ══════════════════════════════════════════════════════════════════════

-- 1. USERS
CREATE TABLE IF NOT EXISTS users (
    id         BIGSERIAL PRIMARY KEY,
    name       TEXT NOT NULL,
    email      TEXT UNIQUE NOT NULL,
    password   TEXT NOT NULL,
    role       TEXT DEFAULT 'citizen',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 2. REPORTS
CREATE TABLE IF NOT EXISTS reports (
    id          BIGSERIAL PRIMARY KEY,
    user_id     BIGINT REFERENCES users(id) ON DELETE SET NULL,
    type        TEXT NOT NULL,
    station     TEXT NOT NULL,
    location    TEXT NOT NULL,
    description TEXT,
    severity    TEXT DEFAULT 'MEDIUM',
    photo_url   TEXT DEFAULT '',
    status      TEXT DEFAULT 'PENDING',
    lat         DOUBLE PRECISION,
    lng         DOUBLE PRECISION,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- 3. ALERTS
CREATE TABLE IF NOT EXISTS alerts (
    id          BIGSERIAL PRIMARY KEY,
    station     TEXT,
    parameter   TEXT,
    value       TEXT,
    threshold   TEXT,
    level       TEXT,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- 4. WATER QUALITY READINGS (sensor history)
CREATE TABLE IF NOT EXISTS readings (
    id          BIGSERIAL PRIMARY KEY,
    station_id  INTEGER NOT NULL,
    bod         DOUBLE PRECISION,
    do_level    DOUBLE PRECISION,
    ph          DOUBLE PRECISION,
    turbidity   DOUBLE PRECISION,
    nitrates    DOUBLE PRECISION,
    phosphates  DOUBLE PRECISION,
    score       INTEGER,
    recorded_at TIMESTAMPTZ DEFAULT NOW()
);

-- 5. SEED: Demo admin user (password = admin123, bcrypt-hashed)
-- Re-generate this hash in Python: from werkzeug.security import generate_password_hash; print(generate_password_hash('admin123'))
-- Insert via the app's /auth/register endpoint instead if preferred.

-- 6. SEED: Alerts
INSERT INTO alerts (station, parameter, value, threshold, level) VALUES
  ('Nizamuddin', 'BOD',           '98 mg/L',  '>30 mg/L',  'CRITICAL'),
  ('Wazirabad',  'Dissolved O₂', '1.2 mg/L', '<4 mg/L',   'CRITICAL'),
  ('Okhla',      'Turbidity',    '165 NTU',  '>100 NTU',  'HIGH'),
  ('Palla',      'pH',           '6.3',      '>6.5',      'MODERATE')
ON CONFLICT DO NOTHING;

-- 7. Row Level Security (optional — enable if you want per-user isolation)
-- ALTER TABLE reports ENABLE ROW LEVEL SECURITY;
-- CREATE POLICY "Users see own reports" ON reports USING (user_id = auth.uid());

-- 8. Supabase Storage
--   Manually create a bucket named "yamuna-reports" in:
--   Supabase Dashboard → Storage → New Bucket
--   Set it to PUBLIC so photo URLs are accessible without auth.

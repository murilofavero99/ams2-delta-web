-- ═════════════════════════════════════════════════════════════════════════
-- AMS2 Delta — Schema do Postgres no Supabase
-- ═════════════════════════════════════════════════════════════════════════
-- Como aplicar:
-- 1. No Supabase Dashboard, vá em "SQL Editor"
-- 2. Cole este arquivo e clique em "Run"
-- 3. No menu "Storage", crie um bucket chamado "telemetry" (público OK por enquanto)
-- ═════════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS sessions (
    session_id       TEXT PRIMARY KEY,
    started_at       TEXT NOT NULL,
    track_location   TEXT DEFAULT 'unknown',
    track_variation  TEXT DEFAULT '',
    track_length_m   REAL DEFAULT 0,
    num_samples      INTEGER DEFAULT 0,
    num_laps         INTEGER DEFAULT 0,
    car_name         TEXT DEFAULT '',
    car_class_name   TEXT DEFAULT '',
    car_class_id     INTEGER DEFAULT 0,
    telemetry_path   TEXT,                       -- caminho do .parquet no Storage
    created_at       TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_sessions_started_at ON sessions(started_at DESC);
CREATE INDEX IF NOT EXISTS idx_sessions_track       ON sessions(track_location);
CREATE INDEX IF NOT EXISTS idx_sessions_car         ON sessions(car_name);

CREATE TABLE IF NOT EXISTS laps (
    session_id   TEXT NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
    lap_number   INTEGER NOT NULL,
    lap_time_s   REAL,
    sector1_s    REAL,
    sector2_s    REAL,
    sector3_s    REAL,
    invalidated  INTEGER DEFAULT 0,
    PRIMARY KEY (session_id, lap_number)
);

CREATE INDEX IF NOT EXISTS idx_laps_session ON laps(session_id);

-- ═════════════════════════════════════════════════════════════════════════
-- RLS (Row Level Security) — desabilitado pra simplicidade.
-- Se quiser limitar acesso, ative depois e crie policies.
-- ═════════════════════════════════════════════════════════════════════════
ALTER TABLE sessions DISABLE ROW LEVEL SECURITY;
ALTER TABLE laps     DISABLE ROW LEVEL SECURITY;

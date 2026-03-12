
PRAGMA foreign_keys = ON;

/* =========================
   1) Core dimensions
   ========================= */

-- Master list of people/players to normalize names & external IDs.
-- bdl_player_id -> BallDontLie player id (if known)
-- pfr_id -> Pro-Football-Reference id coming from nflverse combine feed (if known)
CREATE TABLE IF NOT EXISTS players (
  player_id        INTEGER PRIMARY KEY,
  bdl_player_id    INTEGER UNIQUE,         -- nullable; not all combine rows resolve to BDL
  pfr_id           TEXT UNIQUE,            -- nullable; not all BDL rows resolve to PFR
  first_name       TEXT,
  last_name        TEXT,
  full_name        TEXT,
  norm_name        TEXT NOT NULL,          -- lowercased, punctuation-stripped, space-collapsed
  primary_position TEXT,                   -- e.g., 'RB' for this project
  college          TEXT,
  created_at       TEXT DEFAULT (datetime('now'))
);

-- Fast lookups by external identifiers or normalized name
CREATE INDEX IF NOT EXISTS idx_players_bdl_id    ON players(bdl_player_id);
CREATE INDEX IF NOT EXISTS idx_players_pfr_id    ON players(pfr_id);
CREATE INDEX IF NOT EXISTS idx_players_norm_name ON players(norm_name);


/* =========================
   2) Fact tables
   ========================= */

-- Rookie-season running back totals (one row per player/season/scoring).
-- ppr_points is computed by your script:
--   yards: 0.1 per rush/rec yard; TD: 6; receptions: 1.0 (PPR) / 0.5 (HALF_PPR) / 0.0 (STD); fumbles_lost: -2
CREATE TABLE IF NOT EXISTS rookie_rb_stats (
  player_id       INTEGER NOT NULL REFERENCES players(player_id) ON UPDATE CASCADE ON DELETE CASCADE,
  season          INTEGER NOT NULL,
  games_played    INTEGER,
  rushing_att     REAL,
  rushing_yds     REAL,
  rushing_td      REAL,
  receptions      REAL,
  receiving_yds   REAL,
  receiving_td    REAL,
  fumbles_lost    REAL,
  scoring         TEXT NOT NULL DEFAULT 'PPR',   -- 'PPR' | 'HALF_PPR' | 'STD'
  ppr_points      REAL NOT NULL,                 -- computed by ETL per scoring
  PRIMARY KEY (player_id, season, scoring)
);

-- Analytic indexes for rookie queries:
--   - top/bottom by season
--   - season slices used in rolling 10y windows
CREATE INDEX IF NOT EXISTS idx_rookie_season           ON rookie_rb_stats(season);
CREATE INDEX IF NOT EXISTS idx_rookie_season_scoring   ON rookie_rb_stats(season, scoring);
CREATE INDEX IF NOT EXISTS idx_rookie_player           ON rookie_rb_stats(player_id);
CREATE INDEX IF NOT EXISTS idx_rookie_season_ppr       ON rookie_rb_stats(season, ppr_points);

-- Combine results for RBs (per season). A row may exist without a resolved player_id yet;
-- keep both a normalized name + raw identifiers to help later reconciliation.
CREATE TABLE IF NOT EXISTS combine_results (
  combine_id   INTEGER PRIMARY KEY,
  player_id    INTEGER REFERENCES players(player_id) ON UPDATE CASCADE ON DELETE SET NULL,
  season       INTEGER NOT NULL,
  pos          TEXT,             -- e.g., 'RB'
  school       TEXT,
  ht_raw       TEXT,             -- e.g., '5-11' (raw from source)
  height_in    REAL,             -- normalized inches, e.g., 71.0
  weight_lb    REAL,
  forty        REAL,
  bench        REAL,
  vertical     REAL,
  broad_jump   REAL,
  cone         REAL,
  shuttle      REAL,
  pfr_id       TEXT,             -- duplicate for matching; also lives in players when resolved
  player_name  TEXT,             -- raw name from feed
  norm_name    TEXT NOT NULL,    -- normalized name (lowercased, etc.)
  -- When player_id is known, (player_id, season) should be unique.
  -- Otherwise, fall back to a natural key to avoid dupes on refreshes:
  -- NOTE: SQLite supports multiple UNIQUE constraints; the first is enforced when player_id exists,
  -- the second helps guard raw duplicates when player_id is NULL.
  UNIQUE(player_id, season),
  UNIQUE(player_name, school, season)
);

-- Analytic indexes for combine filtering & joins:
CREATE INDEX IF NOT EXISTS idx_combine_season           ON combine_results(season);
CREATE INDEX IF NOT EXISTS idx_combine_season_pos       ON combine_results(season, pos);
CREATE INDEX IF NOT EXISTS idx_combine_player_season    ON combine_results(player_id, season);
CREATE INDEX IF NOT EXISTS idx_combine_norm_name_season ON combine_results(norm_name, season);

-- Useful metric-specific indexes for common WHERE/ORDER BY patterns
CREATE INDEX IF NOT EXISTS idx_combine_forty_season     ON combine_results(season, forty);
CREATE INDEX IF NOT EXISTS idx_combine_cone_season      ON combine_results(season, cone);
CREATE INDEX IF NOT EXISTS idx_combine_shuttle_season   ON combine_results(season, shuttle);
CREATE INDEX IF NOT EXISTS idx_combine_jump_season      ON combine_results(season, broad_jump, vertical);


/* =========================
   3) (Optional) Helper views
   ========================= */

-- Easy “analysis ready” view for rookie RB PPR by season with names
CREATE VIEW IF NOT EXISTS v_rookie_rb_ppr AS
SELECT
  r.season,
  p.player_id,
  COALESCE(p.full_name, p.first_name || ' ' || p.last_name) AS player_name,
  p.primary_position,
  p.college,
  r.games_played,
  r.rushing_att, r.rushing_yds, r.rushing_td,
  r.receptions,  r.receiving_yds, r.receiving_td,
  r.fumbles_lost,
  r.scoring,
  r.ppr_points
FROM rookie_rb_stats r
JOIN players p ON p.player_id = r.player_id;

-- Join rookies to their *same-season* combine metrics (typical analysis join)
CREATE VIEW IF NOT EXISTS v_rookie_with_combine AS
SELECT
  r.season,
  p.player_id,
  COALESCE(p.full_name, p.first_name || ' ' || p.last_name) AS player_name,
  r.ppr_points, r.scoring,
  c.forty, c.cone, c.shuttle, c.bench, c.vertical, c.broad_jump,
  c.height_in, c.weight_lb,
  p.college
FROM rookie_rb_stats r
JOIN players p        ON p.player_id = r.player_id
LEFT JOIN combine_results c
       ON c.player_id = p.player_id
      AND c.season    = r.season
WHERE p.primary_position = 'RB';

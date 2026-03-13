PRAGMA foreign_keys = ON;

/* =========================
   1) Players dimension
   ========================= */

CREATE TABLE IF NOT EXISTS players (
  player_id        INTEGER PRIMARY KEY,
  first_name       TEXT,
  last_name        TEXT,
  full_name        TEXT,
  norm_name        TEXT NOT NULL,
  primary_position TEXT,
  college          TEXT,
  created_at       TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_players_norm_name ON players(norm_name);


/* =========================
   2) Rookie RB Stats
   ========================= */

CREATE TABLE IF NOT EXISTS rookie_rb_stats (
  player_id       INTEGER NOT NULL REFERENCES players(player_id)
                     ON UPDATE CASCADE ON DELETE CASCADE,
  season          INTEGER NOT NULL,
  games_played    INTEGER,
  rushing_yds     REAL,
  rushing_td      REAL,
  receptions      REAL,
  receiving_yds   REAL,
  receiving_td    REAL,
  fumbles_lost    REAL,
  position        TEXT,
  scoring         TEXT NOT NULL,
  ppr_points      REAL NOT NULL,
  PRIMARY KEY (player_id, season, scoring)
);

CREATE INDEX IF NOT EXISTS idx_rookie_season           ON rookie_rb_stats(season);
CREATE INDEX IF NOT EXISTS idx_rookie_season_scoring   ON rookie_rb_stats(season, scoring);
CREATE INDEX IF NOT EXISTS idx_rookie_player           ON rookie_rb_stats(player_id);
CREATE INDEX IF NOT EXISTS idx_rookie_season_ppr       ON rookie_rb_stats(season, ppr_points);


/* =========================
   3) Combine Results
   ========================= */

CREATE TABLE IF NOT EXISTS combine_results (
  combine_id   INTEGER PRIMARY KEY,
  player_id    INTEGER REFERENCES players(player_id)
                   ON UPDATE CASCADE ON DELETE SET NULL,
  season       INTEGER NOT NULL,
  player_name  TEXT,
  norm_name    TEXT NOT NULL,
  pos          TEXT,
  school       TEXT,
  ht_raw       TEXT,
  height_in    REAL,
  weight_lb    REAL,
  forty        REAL,
  bench        REAL,
  vertical     REAL,
  broad_jump   REAL,
  cone         REAL,
  shuttle      REAL,
  pfr_id       TEXT,
  UNIQUE(player_id, season),
  UNIQUE(player_name, school, season)
);

CREATE INDEX IF NOT EXISTS idx_combine_season           ON combine_results(season);
CREATE INDEX IF NOT EXISTS idx_combine_norm_name_season ON combine_results(norm_name, season);

DROP VIEW IF EXISTS v_rookie_rb_ppr;
DROP VIEW IF EXISTS v_rookie_with_combine;


/* =========================
   4) Views
   ========================= */

CREATE VIEW IF NOT EXISTS v_rookie_rb_ppr AS
SELECT
  r.season,
  p.player_id,
  p.full_name AS player_name,
  p.primary_position,
  p.college,
  r.games_played,
  r.rushing_yds, r.rushing_td,
  r.receptions, r.receiving_yds, r.receiving_td,
  r.fumbles_lost,
  r.scoring,
  r.ppr_points
FROM rookie_rb_stats r
JOIN players p ON p.player_id = r.player_id;

CREATE VIEW IF NOT EXISTS v_rookie_with_combine AS
SELECT
  r.season,
  p.player_id,
  p.full_name AS player_name,
  r.ppr_points,
  r.scoring,
  c.forty,
  c.cone,
  c.shuttle,
  c.bench,
  c.vertical,
  c.broad_jump,
  c.height_in,
  c.weight_lb,
  p.college
FROM rookie_rb_stats r
JOIN players p
  ON p.player_id = r.player_id
LEFT JOIN combine_results c
  ON c.norm_name = p.norm_name
 AND c.season    = r.season
WHERE p.primary_position = 'RB';

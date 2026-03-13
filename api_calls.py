"""
This script is intended to fetch two datasets and store them in SQLite:
  1) Rookie-season RB stats (past 10 seasons) from BALLDONTLIE NFL API
  2) Combine results for RBs (past 10 combines, incl. 2026) via nflreadpy

Tables:
  - rookie_rb_stats (rookie season rb stats with PPR)
  - combine_rb (rb combine results)

Requirements:
  pip install -r requirements.txt

"""

import os
import pathlib
import time
import math
import sqlite3
import datetime as dt
from typing import Dict, Any, List, Iterable
import pandas as pd
import requests
from dotenv import load_dotenv
from balldontlie import BalldontlieAPI

# api = BalldontlieAPI(api_key="YOUR_API_KEY")


# # ---- External sources ----
# # BALLDONTLIE NFL: Authorization header + cursor pagination.  Docs show base URL and auth pattern.  [1](https://developer.sportradar.com/football/docs/nfl-ig-seasonal-stats)
# BDL_BASE = "https://api.balldontlie.io/nfl/v1"

api = BalldontlieAPI(api_key=os.getenv("BDL_API_KEY"))
# stats = api.nfl.season_stats.list()

# nflreadpy exposes load_combine() for Combine results (PFR-fed via nflverse).  
try:
    import nflreadpy as nfl
except Exception as e:
    raise SystemExit("nflreadpy is required. Run: pip install nflreadpy") from e


# ---------------------------
# Configuration & time window
# ---------------------------
load_dotenv()

BDL_API_KEY = os.getenv("BDL_API_KEY")
HEADERS = {"Authorization": BDL_API_KEY} if BDL_API_KEY else {}
DB_PATH = os.getenv("DB_PATH", "rookie_rb.sqlite")
SCORING = os.getenv("SCORING", "PPR").upper()

TODAY = dt.date.today()
CURRENT_YEAR = TODAY.year

# Rookie seasons: create a range of past 10 completed seasons (exclude current year)
ROOKIE_YEARS = list(range(CURRENT_YEAR - 10, CURRENT_YEAR))      # e.g., 2016..2025
# Combine seasons: create a range of last 10 combines INCLUDING current year (so it includes 2026)
COMBINE_YEARS = list(range(CURRENT_YEAR - 9, CURRENT_YEAR + 1))  # e.g., 2017..2026


# ----------------------
# Small utility functions
# ----------------------
def normalize_name(name: str) -> str:
    """Lowercase, trim, collapse whitespace; keep letters, spaces, dash, apostrophe."""
    import re
    s = re.sub(r"[^A-Za-z' -]", "", (name or "")).lower().strip()
    return re.sub(r"\s+", " ", s)


def height_to_inches(ht: str) -> float:
    """
    Convert height like '5-11' to inches. Returns NaN if not parseable.
    (nflverse combine 'ht' often appears as 'ft-in' string.)
    """
    if isinstance(ht, str) and "-" in ht:
        try:
            ft, inch = ht.split("-")
            return int(ft) * 12 + int(inch)
        except Exception:
            return math.nan
    return math.nan


def ppr_points_from_row(row: pd.Series, scoring: str = "PPR") -> float:
    """
    Compute fantasy points from season totals.
    Scoring:
      - PPR: +1 per reception (this use case)
      - HALF_PPR: +0.5 per reception
      - STD: +0 per reception
      - Always: +0.1 per yard (rush+rec), +6 per TD (rush+rec), -2 per fumble lost
    """
    rush_yds = float(row.get("rushing_yds", 0) or 0)
    rec_yds  = float(row.get("receiving_yds", 0) or 0)
    rush_td  = float(row.get("rushing_td", 0) or 0)
    rec_td   = float(row.get("receiving_td", 0) or 0)
    recs     = float(row.get("receptions", 0) or 0)
    fumbles  = float(row.get("fumbles_lost", 0) or 0)

    rec_bonus = 1.0 if scoring == "PPR" else 0.5 if scoring == "HALF_PPR" else 0.0
    return (0.1 * (rush_yds + rec_yds)
            + 6.0 * (rush_td + rec_td)
            + rec_bonus * recs
            - 2.0 * fumbles)


# --------------------------------------
# BallDontLie NFL API (cursor pagination strategy per docs)
# --------------------------------------
# def bdl_paginate(path: str, params: Dict[str, Any]) -> List[Dict[str, Any]]:

#     # API_KEY = os.getenv("BDL_API_KEY")
#     # print("KEY:", API_KEY)

#     # headers = {"Authorization": f"Bearer {API_KEY}"}

#     # r = requests.get("https://api.balldontlie.io/v2/nba/teams", headers=headers)
#     # print(r.status_code, r.text)
#     # print("URL:", f"{BDL_BASE}{path}")
#     # """Minimal client for BALLDONTLIE NFL with cursor-based pagination."""
#     items: List[Dict[str, Any]] = []
#     cursor = None
#     while True:
#         query = dict(params)
#         if cursor is not None:
#             query["cursor"] = cursor

#         r = api.nfl.season_stats.list(headers=HEADERS, params=query, timeout=30) #f"{BDL_BASE}{path}", headers=HEADERS, params=query, timeout=30)
#         if r.status_code == 401:
#             raise SystemExit("401 Unauthorized from BallDontLie. Check BDL_API_KEY / tier.")
#         if r.status_code == 429:
#             time.sleep(1.0)
#             continue
#         r.raise_for_status()

#         payload = r.json() or {}
#         items.extend(payload.get("data", []))
#         meta = payload.get("meta") or {}
#         cursor = meta.get("next_cursor")
#         if not cursor:
#             break

#         time.sleep(0.15)  # gentle pacing
#     return items

def bdl_paginate(endpoint, *, season=None):
    items = []
    cursor = None

    while True:
        query = {}
        if season is not None:
            query["season"] = season
        if cursor is not None:
            query["cursor"] = cursor

        r = endpoint.list(**query)

        if r.status_code == 401:
            raise SystemExit("401 Unauthorized from BallDontLie. Check BDL_API_KEY / tier.")
        if r.status_code == 429:
            time.sleep(1.0)
            continue

        r.raise_for_status()

        payload = r.json() or {}
        items.extend(payload.get("data", []))

        cursor = (payload.get("meta") or {}).get("next_cursor")
        if not cursor:
            break

        time.sleep(0.15)

    return items


# def load_bdl_rb_season_totals(season: int) -> pd.DataFrame:
#     """
#     Load RB season totals for 'season' from BallDontLie NFL.
#     Flattens nested 'player' object; filters to RB by player.position_abbreviation.
#     (Auth header + cursor pagination per docs.)  [1](https://developer.sportradar.com/football/docs/nfl-ig-seasonal-stats)
#     """
#     raw = bdl_paginate("/stats", {"per_page": 100, "seasons": season})
#     df = pd.DataFrame(raw)
#     if df.empty:
#         return df

#     if "player" in df.columns:
#         p = pd.json_normalize(df["player"]).add_prefix("player.")
#         df = pd.concat([df.drop(columns=["player"]), p], axis=1)

#     pos_col = "player.position_abbreviation"
#     if pos_col in df.columns:
#         df = df[df[pos_col] == "RB"].copy()

#     # Standardize columns
#     colmap = {
#         "player.id": "bdl_player_id",
#         "games_played": "games_played",
#         "rushing.attempts": "rushing_att",
#         "rushing.yards": "rushing_yds",
#         "rushing.touchdowns": "rushing_td",
#         "receiving.receptions": "receptions",
#         "receiving.yards": "receiving_yds",
#         "receiving.touchdowns": "receiving_td",
#         "turnovers.fumbles_lost": "fumbles_lost",
#         "player.first_name": "first_name",
#         "player.last_name": "last_name",
#     }
#     for src, dst in colmap.items():
#         if src in df.columns:
#             df.rename(columns={src: dst}, inplace=True)
#         elif dst not in df.columns:
#             df[dst] = 0

#     df["season"] = season
#     df["norm_name"] = (df["first_name"].fillna("") + " " + df["last_name"].fillna("")).apply(
#         normalize_name
#     )
#     # keep only relevant fields
#     keep = [
#         "bdl_player_id",
#         "first_name",
#         "last_name",
#         "norm_name",
#         "season",
#         "games_played",
#         "rushing_att",
#         "rushing_yds",
#         "rushing_td",
#         "receptions",
#         "receiving_yds",
#         "receiving_td",
#         "fumbles_lost",
#     ]
#     if "games_played" in df.columns:
#         df = df[df["games_played"].fillna(0) > 0]
#     return df[[c for c in keep if c in df.columns]]

def load_bdl_rb_season_totals(season: int) -> pd.DataFrame:
    """
    Load RB season totals for 'season' from BallDontLie NFL.
    Flattens nested 'player' object; filters to RB by player.position_abbreviation.
    """

    # Correct call: pass endpoint + season keyword
    raw = bdl_paginate(api.nfl.season_stats, season=season)
    df = pd.DataFrame(raw)

    if df.empty:
        return df

    # Flatten nested player object
    if "player" in df.columns:
        p = pd.json_normalize(df["player"]).add_prefix("player.")
        df = pd.concat([df.drop(columns=["player"]), p], axis=1)

    # Filter to RBs
    pos_col = "player.position_abbreviation"
    if pos_col in df.columns:
        df = df[df[pos_col] == "RB"].copy()

    # Standardize columns
    colmap = {
        "player.id": "bdl_player_id",
        "games_played": "games_played",
        "rushing.attempts": "rushing_att",
        "rushing.yards": "rushing_yds",
        "rushing.touchdowns": "rushing_td",
        "receiving.receptions": "receptions",
        "receiving.yards": "receiving_yds",
        "receiving.touchdowns": "receiving_td",
        "turnovers.fumbles_lost": "fumbles_lost",
        "player.first_name": "first_name",
        "player.last_name": "last_name",
    }

    for src, dst in colmap.items():
        if src in df.columns:
            df.rename(columns={src: dst}, inplace=True)
        elif dst not in df.columns:
            df[dst] = 0

    df["season"] = season
    df["norm_name"] = (
        df["first_name"].fillna("") + " " + df["last_name"].fillna("")
    ).apply(normalize_name)

    # Keep only relevant fields
    keep = [
        "bdl_player_id",
        "first_name",
        "last_name",
        "norm_name",
        "season",
        "games_played",
        "rushing_att",
        "rushing_yds",
        "rushing_td",
        "receptions",
        "receiving_yds",
        "receiving_td",
        "fumbles_lost",
    ]

    if "games_played" in df.columns:
        df = df[df["games_played"].fillna(0) > 0]

    return df[[c for c in keep if c in df.columns]]


def compute_rookie_rb_stats(seasons: Iterable[int], scoring: str) -> pd.DataFrame:
    """
    Assemble rookie-season totals, then compute PPR-based fantasy points (column: ppr_points).
    """
    parts: List[pd.DataFrame] = []
    for y in seasons:
        try:
            print(y)
            df_y = load_bdl_rb_season_totals(y)
            if not df_y.empty:
                parts.append(df_y)
        except Exception as e:
            print(f"WARN: failed loading season {y} stats: {e}")

    if not parts:
        cols = [
            "bdl_player_id","first_name","last_name","norm_name","season",
            "games_played","rushing_att","rushing_yds","rushing_td",
            "receptions","receiving_yds","receiving_td","fumbles_lost","ppr_points"
        ]
        return pd.DataFrame(columns=cols)

    all_stats = pd.concat(parts, ignore_index=True)
    # rookie = earliest season the player appears
    rook_year = (
        all_stats.sort_values(["bdl_player_id", "season"])
        .groupby("bdl_player_id")["season"]
        .first()
        .rename("rookie_season")
    )
    rook = all_stats.merge(rook_year, on="bdl_player_id", how="left")
    rook = rook[rook["season"] == rook["rookie_season"]].copy()
    rook.drop(columns=["rookie_season"], inplace=True)

    # compute PPR/HALF_PPR/STD
    rook["ppr_points"] = rook.apply(lambda r: ppr_points_from_row(r, scoring), axis=1)
    return rook


# --------------------------
# nflreadpy: Combine (RB only)
# --------------------------
def load_combine_rb(seasons: Iterable[int]) -> pd.DataFrame:
    """
    Pull Combine results for RBs using nflreadpy.load_combine().
    nflreadpy docs describe the function; data dictionary via nflverse (PFR source).  
    """
    df = nfl.load_combine(seasons=list(seasons))
    # nflreadpy may return Polars DataFrame; convert to pandas if needed
    # try:
    #     import polars as pl
    #     if isinstance(df, pl.DataFrame):
    #         df = df.to_pandas()
    # except Exception:
    #     pass
    df = df.to_pandas()


    df = df.rename(columns={"player_name": "player_name", "wt": "weight_lb", "ht": "ht_raw"})
    df = df[df["pos"].astype(str).str.upper() == "RB"].copy()
    df["norm_name"] = df["player_name"].apply(normalize_name)
    df["height_in"] = df["ht_raw"].apply(height_to_inches)

    keep = [
        "season","player_name","norm_name","pos","school","ht_raw","height_in","weight_lb",
        "forty","bench","vertical","broad_jump","cone","shuttle","pfr_id",
    ]
    keep = [c for c in keep if c in df.columns]
    return df[keep].drop_duplicates()


# -------------------------
# Main: build & write to DB
# -------------------------
def main() -> None:
    DB_PATH = "rookie_rb.sqlite"
    SCHEMA_PATH = "schema.sql"
    
    print(f"Rookie seasons window: {ROOKIE_YEARS[0]}–{ROOKIE_YEARS[-1]}")
   # print(f"Combine seasons window: {COMBINE_YEARS[0]}–{COMBINE_YEARS[-1]}")
    print(f"Scoring mode: {SCORING}")

    # 1) Rookie RB stats with PPR
    rook_df = compute_rookie_rb_stats(ROOKIE_YEARS, scoring=SCORING)

    # 2) Combine RB results
    combine_df = load_combine_rb(COMBINE_YEARS)

    # 3) Write to SQLite
    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)

    with sqlite3.connect(DB_PATH) as conn:
        conn.executescript(pathlib.Path(SCHEMA_PATH).read_text(encoding="utf-8"))
        if not rook_df.empty:
            rook_df.to_sql("rookie_rb_stats", conn, if_exists="replace", index=False)
        if not combine_df.empty:
            combine_df.to_sql("combine_rb", conn, if_exists="replace", index=False)

    print(f"Done. SQLite: {DB_PATH}")
    #print(f"  rookie_rb_stats rows: {len(rook_df)}")
    #print(f"  combine_rb rows:      {len(combine_df)}")


if __name__ == "__main__":
    main()

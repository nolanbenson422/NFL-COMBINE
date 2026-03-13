"""
This script is intended to fetch two datasets and store them in SQLite:
  1) Rookie-season RB stats (past 10 seasons) from BALLDONTLIE NFL API
  2) Combine results for RBs (past 10 combines, incl. 2026) via nflreadpy

Tables:
  - offensive_stats (rookie season rb stats with PPR)
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

# # ---- External sources ----

# nflreadpy exposes load_combine() for Combine results (PFR-fed via nflverse).  
try:
    import nflreadpy as nfl
except Exception as e:
    raise SystemExit("nflreadpy is required. Run: pip install nflreadpy") from e


# ---------------------------
# Configuration & time window
# ---------------------------
load_dotenv()

DB_PATH = os.getenv("DB_PATH", "rookie_rb.sqlite")
SCORING = os.getenv("SCORING", "PPR").upper()

TODAY = dt.date.today()
CURRENT_YEAR = TODAY.year

# Rookie seasons: create a range of past 10 completed seasons (exclude current year)
ROOKIE_YEARS = list(range(CURRENT_YEAR - 25, CURRENT_YEAR))      # e.g., 2016..2025
# Combine seasons: create a range of last 10 combines INCLUDING current year (so it includes 2026)
COMBINE_YEARS = list(range(CURRENT_YEAR - 24, CURRENT_YEAR + 1))  # e.g., 2017..2026


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

def load_nflverse_rb_season_totals(season: int) -> pd.DataFrame:
    df = nfl.load_player_stats(seasons=[season]).to_pandas()

    if "position" not in df.columns:
        return pd.DataFrame()

    # df = df[df["position"].astype(str).str.upper() == "RB"].copy()
    df = df[df["position"].astype(str).str.upper().isin(["RB", "WR", "TE"])].copy()
    if df.empty:
        return df

    df["full_name"] = df["player_display_name"].astype(str)
    df["first_name"] = df["full_name"].str.split(" ").str[0]
    df["last_name"] = df["full_name"].str.split(" ").str[1:].str.join(" ")
    df["norm_name"] = df["full_name"].apply(normalize_name)

    colmap = {
        "rushing_yards": "rushing_yds",
        "rushing_tds": "rushing_td",
        "receptions": "receptions",
        "receiving_yards": "receiving_yds",
        "receiving_tds": "receiving_td",
        "fumbles_lost": "fumbles_lost",
        "games": "games_played",
    }

    for src, dst in colmap.items():
        if src in df.columns:
            df.rename(columns={src: dst}, inplace=True)
        else:
            df[dst] = 0

    df["season"] = season

    keep = [
        "player_id", "first_name", "last_name", "full_name", "norm_name",
        "season", "games_played", "rushing_yds", "rushing_td",
        "receptions", "receiving_yds", "receiving_td", "fumbles_lost",
        "position"
    ]

    return df[keep]


# def compute_rookie_rb_stats(seasons, scoring):
#     parts = []
#     for y in seasons:
#         try:
#             df_y = load_nflverse_rb_season_totals(y)
#             if not df_y.empty:
#                 parts.append(df_y)
#         except Exception as e:
#             print(f"WARN: failed loading season {y}: {e}")

#     if not parts:
#         return pd.DataFrame()

#     all_stats = pd.concat(parts, ignore_index=True)

#     rook_year = (
#         all_stats.sort_values(["player_id", "season"])
#         .groupby("player_id")["season"]
#         .first()
#         .rename("rookie_season")
#     )

#     rook = all_stats.merge(rook_year, on="player_id")
#     rook = rook[rook["season"] == rook["rookie_season"]].copy()
#     rook.drop(columns=["rookie_season"], inplace=True)

#     rook["scoring"] = scoring
#     rook["ppr_points"] = rook.apply(lambda r: ppr_points_from_row(r, scoring), axis=1)

#     return rook

def compute_rb_stats_all_seasons(seasons, scoring):
    parts = []
    for y in seasons:
        try:
            df_y = load_nflverse_rb_season_totals(y)
            if not df_y.empty:
                parts.append(df_y)
        except Exception as e:
            print(f"WARN: failed loading season {y}: {e}")

    if not parts:
        return pd.DataFrame()

    # ALL seasons for ALL RBs
    all_stats = pd.concat(parts, ignore_index=True)

    # Add scoring + fantasy points
    all_stats["scoring"] = scoring
    all_stats["ppr_points"] = all_stats.apply(
        lambda r: ppr_points_from_row(r, scoring), axis=1
    )

    return all_stats

# --------------------------
# nflreadpy: Combine (RB only)
# --------------------------
def load_combine_rb(seasons):
    df = nfl.load_combine(seasons=list(seasons)).to_pandas()

    df = df[df["pos"].astype(str).str.upper() == "RB"].copy()

    df["norm_name"] = df["player_name"].apply(normalize_name)
    df["height_in"] = df["ht"].apply(height_to_inches)
    df.rename(columns={"ht": "ht_raw", "wt": "weight_lb"}, inplace=True)

    keep = [
        "season", "player_name", "norm_name", "pos", "school",
        "ht_raw", "height_in", "weight_lb", "forty", "bench",
        "vertical", "broad_jump", "cone", "shuttle", "pfr_id"
    ]

    return df[keep]

# -------------------------
# Main: build & write to DB
# -------------------------
def main() -> None:
    DB_PATH = "rookie_rb.sqlite"
    SCHEMA_PATH = "schema.sql"

    print(f"Rookie seasons window: {ROOKIE_YEARS[0]}–{ROOKIE_YEARS[-1]}")
    print(f"Combine seasons window: {COMBINE_YEARS[0]}–{COMBINE_YEARS[-1]}")
    print(f"Scoring mode: {SCORING}")

    # 1) Load rookie RB stats
    # rook_df = compute_rookie_rb_stats(ROOKIE_YEARS, scoring=SCORING)
    rook_df = compute_rb_stats_all_seasons(ROOKIE_YEARS, scoring=SCORING)

    # 2) Load combine RB results
    combine_df = load_combine_rb(COMBINE_YEARS)

    # ---------------------------------------------------------
    # 3) BUILD PLAYERS TABLE (this is where players_df goes)
    # ---------------------------------------------------------

    rook_players = rook_df[[
        "player_id", "first_name", "last_name", "full_name",
        "norm_name", "position"
    ]].copy()
    rook_players.rename(columns={"position": "primary_position"}, inplace=True)
    rook_players["college"] = None

    combine_players = combine_df[[
        "player_name", "norm_name", "pos", "school"
    ]].copy()
    combine_players.rename(columns={
        "player_name": "full_name",
        "pos": "primary_position",
        "school": "college"
    }, inplace=True)

    combine_players["first_name"] = combine_players["full_name"].str.split(" ").str[0]
    combine_players["last_name"] = combine_players["full_name"].str.split(" ").str[1:].str.join(" ")
    combine_players["player_id"] = None  # combine does not include player_id

    players_df = pd.concat([rook_players, combine_players], ignore_index=True)
    players_df = players_df.drop_duplicates(subset=["full_name", "norm_name"])

    players_df = players_df.merge(
    combine_df[["norm_name", "school"]],
    on="norm_name",
    how="left"
    )

    players_df["college"] = players_df["college"].fillna(players_df["school"])
    players_df.drop(columns=["school"], inplace=True)


    # ---------------------------------------------------------
    # 4) WRITE ALL TABLES TO SQLITE
    # ---------------------------------------------------------

    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)

    with sqlite3.connect(DB_PATH) as conn:
        conn.executescript(pathlib.Path(SCHEMA_PATH).read_text(encoding="utf-8"))

        players_df.to_sql("players", conn, if_exists="replace", index=False)
        rook_df.to_sql("offensive_stats", conn, if_exists="replace", index=False)
        combine_df.to_sql("combine_results", conn, if_exists="replace", index=False)

    print(f"Done. SQLite: {DB_PATH}")
    print(f"  players rows:        {len(players_df)}")
    print(f"  offensive_stats rows:{len(rook_df)}")
    print(f"  combine_results rows:{len(combine_df)}")

if __name__ == "__main__":
    main()

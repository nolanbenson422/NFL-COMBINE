# Rookie RB Analytics Pipeline

A complete ETL + analytics workflow for evaluating NFL rookie running backs using historical performance, combine metrics, and predictive scoring models. This project builds a reproducible SQLite database, loads rookie RB season statistics and NFL Combine results, and provides analytical tools to explore trends, correlations, and predictive indicators for future rookie classes.

---

## 📘 Overview

This repository contains:

- A full **ETL pipeline** that:
  - Loads rookie RB season statistics using `nflreadpy`
  - Loads NFL Combine results using `nflreadpy`
  - Normalizes player names
  - Builds a unified `players` dimension table
  - Ensures relational integrity across tables
  - Writes everything into a SQLite database (`rookie_rb.sqlite`)

- A set of **analysis functions** that:
  - Identify top-performing rookie RBs by season
  - Analyze correlations between combine metrics and rookie production
  - Evaluate which colleges produce elite rookie RBs
  - Compute average combine profiles for top performers
  - Predict top RB prospects from the 2026 combine class

---

## 🧠 Data Sources

### Rookie RB Stats  
Rookie RB season stats  are loaded using the `nflreadpy` library, which provides standardized metrics including: 

- Rushing Yards
- Receiving yards  
- Receptions
- Rushing Touchdowns
- Receiving Touchdowns
- Fumbles 


**API Documentation:**  
https://nflreadpy.nflverse.com/


### NFL Combine Data  
Combine results are loaded using the `nflreadpy` library, which provides standardized combine metrics including:

- 40-yard dash  
- 3-cone  
- Shuttle  
- Bench press  
- Vertical jump  
- Broad jump  
- Height / weight  

**API Documentation:**  
https://nflreadpy.nflverse.com/

---

## 📦 Requirements

Install dependencies:

```bash
pip install pandas numpy matplotlib python-dotenv nflreadpy matplotlib requests python-dotenv pyarrow sqlite3
```

## 🗂 Database Schema

The ETL builds three core tables inside `rookie_rb.sqlite`:

### `players`
Stores player identity and metadata.

| Column            | Description |
|------------------|-------------|
| player_id        | Unique player identifier |
| first_name       | Player first name |
| last_name        | Player last name |
| full_name        | Combined full name |
| norm_name        | Normalized name used for joining |
| primary_position | Player position (RB, WR, etc.) |
| college          | College (merged from combine data when available) |

---

### `rookie_rb_stats`
Stores rookie-season performance metrics.

| Column       | Description |
|--------------|-------------|
| player_id    | Foreign key to `players` |
| season       | NFL season |
| ppr_points   | Rookie PPR fantasy points |
| games_played | Number of games played |
| attempts     | Rushing attempts |
| targets      | Passing targets |
| receptions   | Receptions |
| yards        | Total yards |
| touchdowns   | Total touchdowns |

---

### `combine_results`
Stores NFL Combine metrics.

| Column       | Description |
|--------------|-------------|
| player_name  | Raw name from combine data |
| norm_name    | Normalized name |
| season       | Combine year |
| pos          | Position |
| forty        | 40-yard dash |
| cone         | 3-cone drill |
| shuttle      | Shuttle run |
| bench        | Bench press reps |
| vertical     | Vertical jump |
| broad_jump   | Broad jump |
| height_in    | Height (inches) |
| weight_lb    | Weight (pounds) |
| school       | College |

---

### Database Views

Two views are created for convenience:

- `v_rookie_rb_ppr` — rookie RB stats with PPR scoring  
- `v_rookie_with_combine` — rookies joined with combine metrics  

---

## ⚙️ Running the ETL

Run the ETL script:

```bash
python etl.py
```

The ETL performs:

- Fetch rookie RB stats from the `nflreadpy` 
- Fetch combine results using `nflreadpy`  
- Normalize player names  
- Build the `players` table  
- Merge combine `school` → `players.college`  
- Write all tables to `rookie_rb.sqlite`  
- Rebuild SQL views  

After running, verify the schema:

```python
import sqlite3
import pandas as pd

conn = sqlite3.connect("rookie_rb.sqlite")
pd.read_sql_query("PRAGMA table_info(players);", conn) 
```

## 📊 Analysis Functions

All analysis is modularized into reusable Python functions. Each function accepts a SQLite connection (`conn`) and returns a pandas DataFrame.

---

### **1. Top 10 Rookie RBs by Weight**

Returns the top 10 rookie RBs per season, joined with combine weight.

```python
df = get_top10_rb_weight(conn)
```

### **2. Top 10 Rookie RBs by Agility (3-Cone)**

Returns the top 10 rookie RBs per season, joined with 3-cone drill times.
df = get_top10_rb_cone(conn)

```python
df = get_top10_rb_cone(conn)
```

### **3. Colleges Producing Top Rookie RBs**

Counts how many times each college appears among top‑10 rookie RBs.


```python
df = get_top10_rb_colleges(conn)
```

### **4. Average Combine Metrics for Top Performers**

Computes average combine metrics (40, cone, shuttle, bench, vertical, broad jump) for top‑10 rookie RBs.


```python
df = get_top10_rb_combine_averages(conn)
```

### **5. Predict Top 2026 RB Prospects**

Uses combine metrics + college pedigree to score and rank 2026 RB prospects.


```python
df = predict_2026_rb_prospects(conn)
```

## 📓 Viewing the Analysis

Openand run script: `analysis.py`


Inside, you’ll find:

- Scatterplots (weight vs PPR, cone vs PPR)  
- Combine metric averages  
- College frequency tables  
- 2026 RB prospect rankings  

Run script to produce all results

---

## 🧪 Example Visualization

Example: Weight vs Rookie PPR Points

```python
df = get_top10_rb_weight(conn)

plt.scatter(df["weight_lb"], df["ppr_points"], alpha=0.7)
plt.xlabel("Weight (lb)")
plt.ylabel("Rookie PPR Points")
plt.title("Weight vs Rookie RB PPR (Top 10 per Class)")
plt.show()
```

## 🔮 Predictive Model

The 2026 rookie RB prospect model evaluates incoming players using a weighted scoring formula based on historical correlations between combine metrics and rookie-year fantasy production. The model incorporates:

- **Speed** — 40-yard dash  
- **Agility** — 3-cone drill  
- **Short-area quickness** — shuttle  
- **Strength** — bench press  
- **Explosiveness** — vertical and broad jump  
- **Ideal weight range** — bonus for 205–225 lbs  
- **College pedigree** — bonus for historically productive RB programs  
  (Georgia, Alabama, Ohio State, LSU, Wisconsin, Oklahoma)

These factors are combined into a single score that ranks the top 20 RB prospects from the 2026 combine class.

Example usage:

```python
df = predict_2026_rb_prospects(conn)
print(df)
```

This returns a DataFrame sorted by descending score, including:
- player_name
- school
- forty
- cone
- bench
- weight_lb
- score


## 🏁 Summary

This project provides:

- A clean, reproducible ETL pipeline  
- A relational database of rookie RBs + combine metrics  
- Analytical tools for exploring performance trends  
- A predictive model for future rookie classes  

It is designed for extensibility — you can easily add:

- Machine learning models  
- Additional combine metrics  
- College production pipelines  
- Fantasy scoring variations  
- Web dashboards or API endpoints  

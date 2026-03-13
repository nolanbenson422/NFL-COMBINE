import sqlite3
import pandas as pd
import matplotlib.pyplot as plt

def get_top10_rb_weight(conn):
    """
    Returns a DataFrame of the top 10 rookie RBs per season
    with their PPR points and weight, using the rookie view.
    """
    query = """
    WITH ranked AS (
        SELECT
            season,
            player_name,
            ppr_points,
            weight_lb,
            ROW_NUMBER() OVER (
                PARTITION BY season
                ORDER BY ppr_points DESC
            ) AS rn
        FROM v_rookie_with_combine
        WHERE weight_lb IS NOT NULL
    )
    SELECT *
    FROM ranked
    WHERE rn <= 10;
    """

    return pd.read_sql_query(query, conn)

def get_top10_rb_cone(conn):
    """
    Returns a DataFrame of the top 10 rookie RBs per season
    ranked by PPR points, including their 3-cone time.
    """
    query = """
    WITH ranked AS (
        SELECT
            season,
            player_name,
            ppr_points,
            cone,
            ROW_NUMBER() OVER (
                PARTITION BY season
                ORDER BY ppr_points DESC
            ) AS rn
        FROM v_rookie_with_combine
        WHERE cone IS NOT NULL
    )
    SELECT *
    FROM ranked
    WHERE rn <= 10;
    """

    return pd.read_sql_query(query, conn)


def get_top10_rb_colleges(conn):
    """
    Returns a DataFrame of the colleges that produced the most
    top-10 rookie RBs per season (ranked by PPR points).
    """
    query = """
    WITH ranked AS (
        SELECT
            season,
            player_name,
            college,
            ppr_points,
            ROW_NUMBER() OVER (
                PARTITION BY season
                ORDER BY ppr_points DESC
            ) AS rn
        FROM v_rookie_rb_ppr
        WHERE college IS NOT NULL
          AND college <> ''
    )
    SELECT college, COUNT(*) AS top10_count
    FROM ranked
    WHERE rn <= 10
    GROUP BY college
    ORDER BY top10_count DESC
    LIMIT 10;
    """

    return pd.read_sql_query(query, conn)

def get_top10_rb_combine_averages(conn):
    """
    Returns average combine metrics for the top 10 rookie RBs per season,
    ranked by PPR points, using the rookie+combine view.
    """
    query = """
    WITH ranked AS (
        SELECT
            season,
            player_name,
            forty,
            cone,
            shuttle,
            bench,
            vertical,
            broad_jump,
            ROW_NUMBER() OVER (
                PARTITION BY season
                ORDER BY ppr_points DESC
            ) AS rn
        FROM v_rookie_with_combine
    )
    SELECT
        AVG(forty)       AS avg_40,
        AVG(cone)        AS avg_cone,
        AVG(shuttle)     AS avg_shuttle,
        AVG(bench)       AS avg_bench,
        AVG(vertical)    AS avg_vertical,
        AVG(broad_jump)  AS avg_broad_jump
    FROM ranked
    WHERE rn <= 10;
    """

    return pd.read_sql_query(query, conn)


def predict_2026_rb_prospects(conn):
    query = """
    SELECT *
    FROM combine_results
    WHERE season = 2026 AND pos = 'RB';
    """
    df = pd.read_sql_query(query, conn)

    df["score"] = (
        (4.50 - df["forty"]) * 40 +
        (7.10 - df["cone"]) * 25 +
        (df["bench"] - 15) * 5 +
        df["weight_lb"].between(205, 225) * 20 +
        df["school"].isin([
            'Georgia','Alabama','Ohio State','LSU','Wisconsin','Oklahoma'
        ]) * 15
    )

    return df.sort_values("score", ascending=False).head(20)



def main() -> None:
    conn = sqlite3.connect("rookie_rb.sqlite")

    top10_df = get_top10_rb_weight(conn)
    plt.scatter(top10_df["weight_lb"], top10_df["ppr_points"], alpha=0.7)
    plt.xlabel("Weight (lb)")
    plt.ylabel("Rookie PPR Points")
    plt.title("Weight vs Rookie RB PPR (Top 10 per Class)")
    plt.show()

    top10_cone_df = get_top10_rb_cone(conn)
    plt.scatter(top10_cone_df["cone"], top10_cone_df["ppr_points"], alpha=0.7)
    plt.gca().invert_xaxis()  # faster cone = left
    plt.xlabel("3-Cone Time (seconds)")
    plt.ylabel("Rookie PPR Points")
    plt.title("Agility vs Rookie RB PPR (Top 10 per Class)")
    plt.show()

    top10_colleges_df = get_top10_rb_colleges(conn)
    print(top10_colleges_df)

    top10_combine_averages_df = get_top10_rb_combine_averages(conn)
    print(top10_combine_averages_df)

    top20_prospects_df = predict_2026_rb_prospects(conn)
    df_top20 = top20_prospects_df.sort_values("score", ascending=False).head(20)
    df_top20[["player_name", "school", "forty", "cone", "bench", "weight_lb", "score"]]
    print("Top 20 2026 RB Prospects: ")
    print(df_top20[["player_name"]])

if __name__ == "__main__":
    main()

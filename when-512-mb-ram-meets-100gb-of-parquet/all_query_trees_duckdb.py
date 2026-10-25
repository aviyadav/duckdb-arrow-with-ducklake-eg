"""Run every TPC-H query against tpch_temp.db and write one DuckDB
``query_tree`` profile per query into ``tpc-profile-out/qNN_profile.txt``.

The files in ``tpc-h-sqls/`` are raw TPC-H templates (qgen style): their
parameters are still placeholders such as ``:1``, ``':2'`` and ``'%:3'``, so
they are not executable as-is.  They are filled in with the standard TPC-H
substitution values below, and two template artefacts are cleaned up:

* ``:o``          - qgen "print output" directive on its own line (Q15)
* ``revenue:s``   - parameterised view name (Q15)
* ``day (3)``     - SQL interval precision, which DuckDB rejects (Q1)

Q15 is also the only multi-statement query (create view / select / drop view);
only its SELECT is profiled, so the profile file describes the real query
rather than the DDL around it.

Usage:
    python all_query_trees_duckdb.py            # all queries
    python all_query_trees_duckdb.py 01 06 15   # only these
"""

import re
import sys
import time
from pathlib import Path

import duckdb

DB_FILE = "tpch_temp.db"
SQL_DIR = Path("tpc-h-sqls")
OUT_DIR = Path("tpc-profile-out")

# Standard TPC-H substitution values (the qgen defaults).  Values are inserted
# verbatim: the templates already carry quotes around string parameters
# (':1', '%:2') and leave numeric ones bare (p_size = :1).
SUBSTITUTIONS = {
    "01": {1: "90"},
    "02": {1: "15", 2: "BRASS", 3: "EUROPE"},
    "03": {1: "BUILDING", 2: "1995-03-15"},
    "04": {1: "1993-07-01"},
    "05": {1: "ASIA", 2: "1994-01-01"},
    "06": {1: "1994-01-01", 2: "0.06", 3: "24"},
    "07": {1: "FRANCE", 2: "GERMANY"},
    "08": {1: "BRAZIL", 2: "AMERICA", 3: "ECONOMY ANODIZED STEEL"},
    "09": {1: "green"},
    "10": {1: "1993-10-01"},
    "11": {1: "GERMANY", 2: "0.0001"},
    "12": {1: "MAIL", 2: "SHIP", 3: "1994-01-01"},
    "13": {1: "special", 2: "requests"},
    "14": {1: "1995-09-01"},
    "15": {1: "1996-01-01"},
    "16": {
        1: "Brand#45",
        2: "MEDIUM POLISHED",
        3: "49",
        4: "14",
        5: "23",
        6: "45",
        7: "19",
        8: "3",
        9: "36",
        10: "9",
    },
    "17": {1: "Brand#23", 2: "MED BOX"},
    "18": {1: "300"},
    "19": {
        1: "Brand#12",
        2: "Brand#23",
        3: "Brand#34",
        4: "1",
        5: "10",
        6: "20",
    },
    "20": {1: "forest", 2: "1994-01-01", 3: "CANADA"},
    "21": {1: "SAUDI ARABIA"},
    "22": {1: "13", 2: "31", 3: "23", 4: "29", 5: "30", 6: "18", 7: "17"},
}


def prepare_sql(qnum, text):
    """Turn a TPC-H template into executable DuckDB SQL statements."""
    # qgen's output directive sits on its own line and is not SQL.
    text = re.sub(r"^\s*:o\s*$", "", text, flags=re.MULTILINE)

    # Q15's parameterised view name: revenue:s -> revenue0
    text = text.replace(":s", "0")

    # Substitute :1, :2, ... (:10 must not be shadowed by :1, hence \d+).
    values = SUBSTITUTIONS.get(qnum, {})
    text = re.sub(
        r":(\d+)\b",
        lambda m: values.get(int(m.group(1)), m.group(0)),
        text,
    )

    # DuckDB has no interval precision: INTERVAL '90' DAY (3) -> DAY
    text = re.sub(
        r"\b(day|month|year)\s*\(\s*\d+\s*\)", r"\1", text, flags=re.IGNORECASE
    )

    return [s.strip() for s in text.split(";") if s.strip()]


def run_query(con, qnum, statements, out_path):
    """Execute one query's statements, profiling only its main SELECT."""
    # The main query is the last SELECT; anything before it is setup (Q15's
    # CREATE VIEW) and anything after is teardown (Q15's DROP VIEW).
    select_idx = next(
        (
            i
            for i in range(len(statements) - 1, -1, -1)
            if statements[i].lower().lstrip().startswith("select")
        ),
        None,
    )
    if select_idx is None:
        raise ValueError("no SELECT statement found")

    con.execute("PRAGMA disable_profiling;")
    for stmt in statements[:select_idx]:
        con.execute(stmt)

    con.execute(f"PRAGMA profiling_output = '{out_path.as_posix()}';")
    con.execute("PRAGMA enable_profiling = 'query_tree';")
    try:
        con.execute(statements[select_idx]).fetchall()
    finally:
        con.execute("PRAGMA disable_profiling;")

    for stmt in statements[select_idx + 1 :]:
        con.execute(stmt)


def main():
    wanted = sys.argv[1:] or None

    sql_files = sorted(SQL_DIR.glob("*.sql"))
    if wanted:
        sql_files = [p for p in sql_files if p.stem in wanted]
    if not sql_files:
        print(f"No .sql files found in {SQL_DIR}/")
        return 1

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    con = duckdb.connect(DB_FILE)
    ok, failed = [], []

    for path in sql_files:
        qnum = path.stem
        out_path = OUT_DIR / f"q{qnum}_profile.txt"
        print(f"[q{qnum}] running ...", end=" ", flush=True)
        start = time.time()
        try:
            statements = prepare_sql(qnum, path.read_text())
            run_query(con, qnum, statements, out_path)
        except Exception as exc:  # keep going: one bad query must not stop the batch
            elapsed = time.time() - start
            failed.append((qnum, str(exc).splitlines()[0]))
            print(f"FAILED in {elapsed:.2f}s\n         {exc}".rstrip())
            continue

        elapsed = time.time() - start
        if out_path.exists():
            size = out_path.stat().st_size
            ok.append((qnum, elapsed))
            print(f"profiled in {elapsed:.2f}s -> {out_path} ({size} bytes)")
        else:
            failed.append((qnum, "profile file was not written"))
            print(f"ran in {elapsed:.2f}s but no profile file was written")

    con.close()

    print(f"\n=== Summary: {len(ok)} profiled, {len(failed)} failed ===")
    for qnum, elapsed in ok:
        print(f"  q{qnum}: {elapsed:.2f}s")
    for qnum, err in failed:
        print(f"  q{qnum}: FAILED - {err}")

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

from __future__ import annotations

from datetime import date, datetime


def parse_date(value: str) -> date:
    """
    Parse a date supplied as either:
      - YYYY-MM-DD
      - YYYYMMDD
    """
    value = value.strip()

    for fmt in ("%Y-%m-%d", "%Y%m%d"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            pass

    raise ValueError(
        f"Unsupported date format: {value!r}. "
        "Expected YYYY-MM-DD or YYYYMMDD."
    )


def sql_quote(value: str) -> str:
    """
    Safely quote a string for inclusion in a DuckDB SQL statement.
    """
    return "'" + str(value).replace("'", "''") + "'"
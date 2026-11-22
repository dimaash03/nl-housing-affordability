"""The harmonised-price SQL in docs/harmonisation.md must equal the Python reference (QA H-4).

The SQL block is read from the doc itself, so the documented pattern cannot drift from the
tested one. Runs offline on a tiny synthetic DuckDB with the real staging column names.
"""

from __future__ import annotations

import re
from pathlib import Path

import duckdb
import pandas as pd
import pytest

from nl_housing import config
from nl_housing import weight_sensitivity as ws

DOC = config.REPO_ROOT / "docs" / "harmonisation.md"

# Historical codes -> 2026 codes. GM0001 merges into GM0003; GM0020 splits 60/40; GM0010 is renamed to GM0011
# mid-2015 and both have a 2015 price (the De Fryske Marren pattern, D-022); GM0998 is a pseudo code.
MAPPING = pd.DataFrame(
    [
        ("GM0001", "GM0003", 1.0, "merge"),
        ("GM0003", "GM0003", 1.0, "unchanged"),
        ("GM0010", "GM0011", 1.0, "rename"),
        ("GM0011", "GM0011", 1.0, "unchanged"),
        ("GM0020", "GM0003", 0.6, "split"),
        ("GM0020", "GM0021", 0.4, "split"),
        ("GM0021", "GM0021", 1.0, "unchanged"),
    ],
    columns=["old_code", "new_code_2026", "weight", "change_type"],
)
PRICES = pd.DataFrame(
    [
        ("GM0001", 2014, 200_000.0),
        ("GM0003", 2014, 300_000.0),
        ("GM0020", 2014, 250_000.0),
        ("GM0021", 2014, 400_000.0),
        ("GM0010", 2014, 180_000.0),
        ("GM0010", 2015, 190_000.0),  # first half of 2015
        ("GM0011", 2015, 210_000.0),  # second half of 2015, same territory
        ("GM0011", 2016, 220_000.0),
        ("GM0003", 2016, 310_000.0),
        ("GM0021", 2016, 410_000.0),
    ],
    columns=["code", "year", "price"],
)
OWNER_STOCK = pd.DataFrame(
    [
        ("GM0001", 2014, 1_000.0),
        ("GM0003", 2014, 5_000.0),
        ("GM0020", 2014, 2_000.0),
        ("GM0021", 2014, 3_000.0),
        ("GM0010", 2014, 4_000.0),
        ("GM0010", 2015, 4_100.0),  # 1 January figures: only the old code exists in 2015
        ("GM0011", 2016, 4_200.0),
        ("GM0003", 2016, 5_100.0),
        ("GM0021", 2016, 3_100.0),
    ],
    columns=["code", "year", "owner_stock"],
)


def doc_sql() -> str:
    match = re.search(r"harmonised-price-sql.*?```sql\n(.*?)```", DOC.read_text(encoding="utf-8"), re.S)
    assert match, "harmonised-price-sql block not found in docs/harmonisation.md"
    return match.group(1)


@pytest.fixture
def db(tmp_path: Path) -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(str(tmp_path / "t.duckdb"))
    con.execute("create schema staging")
    con.execute("create schema reference")
    prices = PRICES.rename(columns={"code": "region_code", "price": "avg_sale_price_eur"}).assign(region_type="GM")
    prices = pd.concat(
        [
            prices,
            pd.DataFrame([{"region_code": "GM0998", "year": 2014, "avg_sale_price_eur": 1.0, "region_type": "GM"}]),
        ]
    )
    key = OWNER_STOCK.rename(columns={"code": "region_code", "owner_stock": "owner_occupied_stock"})
    con.register("prices_df", prices)
    con.register("key_df", key.assign(region_type="GM"))
    con.register("mapping_df", MAPPING)
    con.execute("create table staging.stg_cbs__house_prices as select * from prices_df")
    con.execute("create table staging.stg_cbs__regional_key_figures as select * from key_df")
    con.execute("create table reference.municipality_mapping_2026 as select * from mapping_df")
    return con


def test_doc_sql_equals_python_reference(db):
    got = db.execute(doc_sql()).df()
    ref = ws.harmonised_prices(PRICES, OWNER_STOCK, MAPPING)
    merged = got.merge(ref, on=["new_code_2026", "year"], how="outer", suffixes=("_sql", "_py"), indicator=True)
    assert (merged["_merge"] == "both").all(), merged
    assert (merged["avg_sale_price_eur_sql"] - merged["avg_sale_price_eur_py"]).abs().max() < 1e-6
    assert (merged["n_source_codes_sql"] == merged["n_source_codes_py"]).all()


def test_mid_year_rename_is_one_equal_weight_unit(db):
    got = db.execute(doc_sql()).df().set_index(["new_code_2026", "year"])
    # Both 2015 prices count with equal weight, although only GM0010 has a 2015 weight.
    assert got.loc[("GM0011", 2015), "avg_sale_price_eur"] == pytest.approx((190_000 + 210_000) / 2)
    # Split + merge: GM0003 2014 = (200k*1000 + 300k*5000 + 250k*2000*0.6) / (1000 + 5000 + 1200)
    expected = (200_000 * 1_000 + 300_000 * 5_000 + 250_000 * 1_200) / 7_200
    assert got.loc[("GM0003", 2014), "avg_sale_price_eur"] == pytest.approx(expected)

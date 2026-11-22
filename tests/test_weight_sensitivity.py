"""Offline tests for the harmonised-price weighting (nl_housing.weight_sensitivity)."""

from __future__ import annotations

import pandas as pd
import pytest

from nl_housing import harmonise as h
from nl_housing import weight_sensitivity as ws

MAPPING = pd.DataFrame([
    # A + B merge into A; C splits 25/75 over A and D; R renamed mid-year to S
    ("GM0001", "GM0001", 1.0, "unchanged"),
    ("GM0002", "GM0001", 1.0, "merge"),
    ("GM0003", "GM0001", 0.25, "split"),
    ("GM0003", "GM0004", 0.75, "split"),
    ("GM0004", "GM0004", 1.0, "unchanged"),
    ("GM0005", "GM0006", 1.0, "rename"),
    ("GM0006", "GM0006", 1.0, "unchanged"),
], columns=["old_code", "new_code_2026", "weight", "change_type"]).assign(new_name_2026="x")


def frames(rows_prices, rows_weights):
    prices = pd.DataFrame(rows_prices, columns=["code", "year", "price"])
    weights = pd.DataFrame(rows_weights, columns=["code", "year", "owner_stock", "dwellings", "households"])
    return prices, weights


def test_weighted_mean_with_split_weights():
    prices, weights = frames(
        [("GM0001", 2015, 300.0), ("GM0002", 2015, 100.0), ("GM0003", 2015, 200.0), ("GM0004", 2015, 400.0)],
        [("GM0001", 2015, 60, 100, 100), ("GM0002", 2015, 20, 10, 10),
         ("GM0003", 2015, 80, 50, 50), ("GM0004", 2015, 10, 10, 10)])
    out = ws.harmonised_prices(prices, weights, MAPPING, "owner_stock").set_index("new_code_2026")
    # A: (300*60 + 100*20 + 200*80*0.25) / (60 + 20 + 20) = 240
    assert out.loc["GM0001", "avg_sale_price_eur"] == pytest.approx(240.0)
    assert out.loc["GM0001", "n_source_codes"] == 3
    # D: (400*10 + 200*80*0.75) / (10 + 60) = 16000/70
    assert out.loc["GM0004", "avg_sale_price_eur"] == pytest.approx(16000 / 70)


def test_mid_year_rename_is_one_equal_weight_unit():
    # Like GM1921/GM1940 in 2015: both priced, only the old code has 1-January figures.
    prices, weights = frames([("GM0005", 2015, 100.0), ("GM0006", 2015, 200.0)],
                             [("GM0005", 2015, 50, 80, 80), ("GM0006", 2015, None, None, None)])
    out = ws.harmonised_prices(prices, weights, MAPPING, "owner_stock")
    assert out[["new_code_2026", "avg_sale_price_eur", "n_source_codes"]].values.tolist() == [["GM0006", 150.0, 1]]


def test_missing_weight_raises():
    prices, weights = frames([("GM0001", 2015, 300.0), ("GM0002", 2015, 100.0)],
                             [("GM0001", 2015, 60, 100, 100), ("GM0002", 2015, None, 10, 10)])
    with pytest.raises(h.HarmonisationError, match="Missing owner_stock"):
        ws.harmonised_prices(prices, weights, MAPPING, "owner_stock")


def test_sensitivity_and_summary():
    prices, weights = frames([("GM0001", 2015, 300.0), ("GM0002", 2015, 100.0), ("GM0004", 2015, 400.0)],
                             [("GM0001", 2015, 50, 100, 150), ("GM0002", 2015, 50, 100, 50),
                              ("GM0004", 2015, 10, 10, 10)])
    wide = ws.sensitivity(prices, weights, MAPPING).set_index("new_code_2026")
    assert wide.loc["GM0001", "owner_stock"] == pytest.approx(200.0)
    assert wide.loc["GM0001", "households"] == pytest.approx(250.0)
    assert wide.loc["GM0001", "households_vs_owner_stock_pct"] == pytest.approx(25.0)
    assert wide.loc["GM0004", "dwellings_vs_owner_stock_pct"] == pytest.approx(0.0)
    stats = ws.summarise(wide.reset_index())
    assert stats["municipality_years_harmonised"] == 1  # only GM0001 has more than one source code
    assert stats["households"]["max_abs_pct"] == pytest.approx(25.0)
    assert stats["households"]["max_at"] == "GM0001 2015"

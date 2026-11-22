"""Sensitivity of the harmonised average price to the weight choice (decision D-007).

When several historical codes are combined into one 2026 municipality, the
harmonised average sale price is a weighted mean of the historical averages::

    price_2026 = sum(price_old * w_old * mapping_weight) / sum(w_old * mapping_weight)

CBS publishes no transaction counts per municipality, so ``w_old`` is a proxy.
D-007 chose the owner-occupied dwelling stock (``Woningvoorraad_59 *
Koopwoningen_64 / 100``, ``70072ned``, same year as the price). This module
recomputes the harmonised prices with two alternatives (total dwellings,
private households) and reports how much they differ. It is also the Python
reference implementation that the staging/marts SQL can be tested against.

Mid-year rename (only case: GM1921 De Friese Meren -> GM1940 De Fryske Marren,
01-07-2015): both codes have a 2015 price for the *same territory* (two halves
of the year), and ``70072ned`` (reference date 1 January) has 2015 figures only
for GM1921. The two prices are combined with equal weight into one territorial
unit first (DATA_DICTIONARY 4.7), before weighting against other units.

Usage::

    python -m nl_housing.weight_sensitivity              # Markdown summary on stdout
    python -m nl_housing.weight_sensitivity --details out.csv
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import pandas as pd

from nl_housing import config, harmonise

logger = logging.getLogger(__name__)

KEY_FIGURES_TABLE = "70072ned"

#: weight option -> description (column names of the frame built by load_weights)
WEIGHT_OPTIONS: dict[str, str] = {
    "owner_stock": "owner-occupied dwellings (Woningvoorraad_59 * Koopwoningen_64 / 100) — D-007 choice",
    "dwellings": "total dwelling stock (Woningvoorraad_59)",
    "households": "private households (TotaalParticuliereHuishoudens_51)",
}
BASELINE = "owner_stock"

#: Research prototype values for Amsterdam incl. Weesp, owner-stock weight
#: (docs/cbs_tables_research.md section 5), reproduced here as a regression check.
RESEARCH_AMSTERDAM = {2019: 481_422, 2020: 507_388, 2021: 564_658, 2022: 617_736}


# --- Inputs ------------------------------------------------------------------


def load_prices(start_year: int, end_year: int, root: Path = config.REPO_ROOT) -> pd.DataFrame:
    """``[code, year, price]`` for GM codes with a price in ``83625NED``."""
    df = pd.read_parquet(harmonise._table_dir(harmonise.PRICE_TABLE, root) / "typed_dataset.parquet",
                         columns=["RegioS", "Perioden", "GemiddeldeVerkoopprijs_1"])
    df = df.assign(code=df["RegioS"].str.strip(), year=df["Perioden"].str[:4].astype(int))
    df = df[df["code"].str.startswith("GM") & df["year"].between(start_year, end_year)]
    df = df.dropna(subset=["GemiddeldeVerkoopprijs_1"])
    return df.rename(columns={"GemiddeldeVerkoopprijs_1": "price"})[["code", "year", "price"]].reset_index(drop=True)


def load_weights(start_year: int, end_year: int, root: Path = config.REPO_ROOT) -> pd.DataFrame:
    """``[code, year, owner_stock, dwellings, households]`` from ``70072ned``."""
    cols = ["RegioS", "Perioden", "Woningvoorraad_59", "Koopwoningen_64", "TotaalParticuliereHuishoudens_51"]
    df = pd.read_parquet(harmonise._table_dir(KEY_FIGURES_TABLE, root) / "typed_dataset.parquet", columns=cols)
    df = df.assign(code=df["RegioS"].str.strip(), year=df["Perioden"].str[:4].astype(int))
    df = df[df["code"].str.startswith("GM") & df["year"].between(start_year, end_year)]
    return pd.DataFrame({
        "code": df["code"],
        "year": df["year"],
        "owner_stock": df["Woningvoorraad_59"] * df["Koopwoningen_64"] / 100,
        "dwellings": df["Woningvoorraad_59"],
        "households": df["TotaalParticuliereHuishoudens_51"],
    }).reset_index(drop=True)


# --- Core --------------------------------------------------------------------


def _territorial_units(observations: pd.DataFrame, mapping: pd.DataFrame) -> pd.DataFrame:
    """Merge a renamed code and its successor that both have a price in the same year.

    They describe the same territory (two parts of the year), so their prices are
    averaged with equal weight and the unit keeps the weights that are available
    (mean of the non-missing values). The unit is identified by the successor code.
    """
    renames = mapping.loc[mapping["change_type"] == harmonise.CHANGE_RENAME, ["old_code", "new_code_2026"]]
    rename_to = dict(zip(renames["old_code"], renames["new_code_2026"]))
    obs = observations.copy()
    present = set(zip(obs["code"], obs["year"]))
    successor = obs["code"].map(rename_to)
    both = successor.notna() & pd.Series([(s, y) in present for s, y in zip(successor, obs["year"])], index=obs.index)
    if not both.any():
        return obs
    for code, year in obs.loc[both, ["code", "year"]].itertuples(index=False):
        logger.info("Mid-year rename: %s and %s both priced in %d -> equal-weight unit", code, rename_to[code], year)
    obs.loc[both, "code"] = successor[both]
    value_cols = [c for c in obs.columns if c not in ("code", "year")]
    return obs.groupby(["code", "year"], as_index=False)[value_cols].mean()


def harmonised_prices(prices: pd.DataFrame, weights: pd.DataFrame, mapping: pd.DataFrame,
                      weight_col: str = BASELINE) -> pd.DataFrame:
    """Average sale price per 2026 municipality and year, weighted by ``weight_col``.

    Returns ``[new_code_2026, year, avg_sale_price_eur, n_source_codes]``.
    Raises if a contributing observation has no weight (would silently bias the mean).
    """
    obs = prices.merge(weights[["code", "year", weight_col]], on=["code", "year"], how="left")
    obs = _territorial_units(obs, mapping)
    if obs[weight_col].isna().any():
        missing = obs.loc[obs[weight_col].isna(), ["code", "year"]].values.tolist()
        raise harmonise.HarmonisationError(f"Missing {weight_col} for priced observations: {missing}")

    m = mapping[["old_code", "new_code_2026", "weight"]]
    joined = obs.merge(m, left_on="code", right_on="old_code", how="left", validate="many_to_many")
    if joined["new_code_2026"].isna().any():
        raise harmonise.HarmonisationError(f"Codes not in mapping: {sorted(joined.loc[joined['new_code_2026'].isna(), 'code'].unique())}")
    joined["w"] = joined[weight_col] * joined["weight"]
    joined["pw"] = joined["price"] * joined["w"]
    out = joined.groupby(["new_code_2026", "year"], as_index=False).agg(
        pw=("pw", "sum"), w=("w", "sum"), n_source_codes=("code", "nunique"))
    out["avg_sale_price_eur"] = out["pw"] / out["w"]
    return out[["new_code_2026", "year", "avg_sale_price_eur", "n_source_codes"]]


def sensitivity(prices: pd.DataFrame, weights: pd.DataFrame, mapping: pd.DataFrame) -> pd.DataFrame:
    """Harmonised prices for every weight option, side by side, with % differences vs the baseline."""
    frames = []
    for option in WEIGHT_OPTIONS:
        hp = harmonised_prices(prices, weights, mapping, option).rename(columns={"avg_sale_price_eur": option})
        frames.append(hp.set_index(["new_code_2026", "year"]))
    wide = pd.concat([frames[0]] + [f.drop(columns="n_source_codes") for f in frames[1:]], axis=1).reset_index()
    for option in WEIGHT_OPTIONS:
        if option != BASELINE:
            wide[f"{option}_vs_{BASELINE}_pct"] = (wide[option] / wide[BASELINE] - 1) * 100
    return wide


def summarise(wide: pd.DataFrame) -> dict:
    """Statistics over the *harmonised* municipality-years (more than one source code)."""
    harmonised = wide[wide["n_source_codes"] > 1]
    result: dict = {
        "municipality_years_total": int(len(wide)),
        "municipality_years_harmonised": int(len(harmonised)),
        "municipalities_harmonised": int(harmonised["new_code_2026"].nunique()),
    }
    for option in WEIGHT_OPTIONS:
        if option == BASELINE:
            continue
        diff = harmonised[f"{option}_vs_{BASELINE}_pct"]
        worst = harmonised.loc[diff.abs().idxmax()]
        result[option] = {
            "max_abs_pct": float(diff.abs().max()),
            "median_abs_pct": float(diff.abs().median()),
            "p95_abs_pct": float(diff.abs().quantile(0.95)),
            "share_within_0_5_pct": float((diff.abs() <= 0.5).mean()),
            "max_at": f"{worst['new_code_2026']} {int(worst['year'])}",
        }
    return result


def to_markdown(wide: pd.DataFrame, stats: dict, mapping: pd.DataFrame) -> str:
    """Human-readable summary (pasted into docs/harmonisation.md)."""
    names = dict(zip(mapping["new_code_2026"], mapping["new_name_2026"]))
    lines = [
        f"Harmonised municipality-years (more than one source code): {stats['municipality_years_harmonised']} "
        f"of {stats['municipality_years_total']} ({stats['municipalities_harmonised']} municipalities).",
        "",
        "| Alternative weight vs owner stock | max abs diff | median abs diff | p95 abs diff | share within 0.5 % | max at |",
        "|---|---:|---:|---:|---:|---|",
    ]
    for option in WEIGHT_OPTIONS:
        if option == BASELINE:
            continue
        s = stats[option]
        code, year = s["max_at"].split()
        lines.append(f"| {option} | {s['max_abs_pct']:.2f} % | {s['median_abs_pct']:.2f} % | {s['p95_abs_pct']:.2f} % "
                     f"| {s['share_within_0_5_pct']:.0%} | {names.get(code, code)} ({code}) {year} |")

    ams = wide[(wide["new_code_2026"] == "GM0363") & wide["year"].isin(RESEARCH_AMSTERDAM)].sort_values("year")
    lines += ["", "Amsterdam incl. Weesp (GM0363), euro:", "",
              "| year | owner stock | dwellings | households | research prototype (owner stock) |",
              "|---|---:|---:|---:|---:|"]
    for row in ams.itertuples(index=False):
        lines.append(f"| {row.year} | {row.owner_stock:,.0f} | {row.dwellings:,.0f} | {row.households:,.0f} "
                     f"| {RESEARCH_AMSTERDAM[row.year]:,} |".replace(",", " "))
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Weight sensitivity of the harmonised average price (D-007).")
    parser.add_argument("--start-year", type=int, default=harmonise.DEFAULT_START_YEAR)
    parser.add_argument("--end-year", type=int, default=harmonise.DEFAULT_END_YEAR)
    parser.add_argument("--details", type=Path, help="optional CSV with all municipality-years (do not commit)")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    mapping = pd.read_csv(harmonise.mapping_path(), dtype={"weight": float}, keep_default_na=False)
    prices = load_prices(args.start_year, args.end_year)
    weights = load_weights(args.start_year, args.end_year)
    wide = sensitivity(prices, weights, mapping)
    stats = summarise(wide)
    if args.details:
        wide.to_csv(args.details, index=False)
        logger.info("Wrote %d rows to %s", len(wide), args.details)
    sys.stdout.write(to_markdown(wide, stats, mapping))
    return 0


if __name__ == "__main__":
    sys.exit(main())

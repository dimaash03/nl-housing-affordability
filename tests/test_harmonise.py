"""Offline tests for the herindeling mapping (nl_housing.harmonise).

Fixtures are verbatim ``70739ned/RegioS`` descriptions (``tests/fixtures/``),
so the parser is tested against the real CBS text, including ``\\r\\n`` line
endings, the lone "." separator and history blocks before 2011.
"""

from __future__ import annotations

import json
import logging
import random
from datetime import date
from pathlib import Path

import duckdb
import pandas as pd
import pytest

from nl_housing import harmonise as h

FIXTURE = Path(__file__).parent / "fixtures" / "regios_70739ned_sample.json"

#: 2026 codes among the fixture municipalities (all verified in 86247NED).
TARGETS = ["GM0074", "GM0080", "GM0363", "GM0757", "GM0824", "GM0855", "GM0865",
           "GM1900", "GM1904", "GM1940", "GM1942", "GM1945", "GM1978"]


@pytest.fixture(scope="module")
def regions() -> pd.DataFrame:
    return pd.DataFrame(json.loads(FIXTURE.read_text(encoding="utf-8"))["regions"])


@pytest.fixture(scope="module")
def events(regions: pd.DataFrame) -> dict[str, h.SuccessionEvent]:
    return h.build_events(regions)


@pytest.fixture(scope="module")
def names(regions: pd.DataFrame) -> dict[str, str]:
    return dict(zip(regions["Key"], regions["Title"]))


@pytest.fixture(scope="module")
def targets(names: dict[str, str]) -> dict[str, str]:
    return {code: names[code] for code in TARGETS}


@pytest.fixture(scope="module")
def mapping(events, targets, names) -> pd.DataFrame:
    codes = ["GM0457", "GM0363", "GM0788", "GM1921", "GM1940", "GM0241", "GM0265",
             "GM0424", "GM0055", "GM0571", "GM1927", "GM0311"]
    return h.build_mapping(codes, events, targets, names)


def rows(mapping: pd.DataFrame, code: str) -> pd.DataFrame:
    return mapping[mapping["old_code"] == code].set_index("new_code_2026")


# --- Parsing -----------------------------------------------------------------


@pytest.mark.parametrize(("text", "expected"), [
    ("535 hectare met 918 woningen en 2149 inwoners", (535.0, 918, 2149)),
    ("22 hectare met 1 woning en 1 inwoner", (22.0, 1, 1)),
    ("0,17 hectare met 0 woningen en 0 inwoners", (0.17, 0, 0)),
    ("84 hectare 12 woningen en 30 inwoners", (84.0, 12, 30)),       # "met" missing
    ("1767 hectare met 3159 inwoners", (1767.0, None, 3159)),        # pre-1990 records
    ("48 inwoners", (None, None, 48)),
    ("16540 hectare met 458.397 woningen en 882.633 inwoners", (16540.0, 458397, 882633)),  # defensive
])
def test_parse_detail_line(text, expected):
    assert h.parse_detail_line(text) == expected


def test_parse_weesp_abolition(events):
    e = events["GM0457"]
    assert e.kind == h.KIND_ABOLITION
    assert e.effective_date == date(2022, 3, 24)
    assert e.receivers == (h.Receiver("GM0363", "Amsterdam", 2272.0, 9526, 20766),)


def test_parse_only_terminating_events(events):
    # Amsterdam's description has a "Gemeentelijke herindeling ... ontvangen van" block
    # (the receiving side) and many Grenswijzigingen: none of them ends the code.
    assert "GM0363" not in events
    # GM1940 has "Naamswijziging ... oude naam: ..." only: not a successor.
    assert "GM1940" not in events


def test_parse_haaren_split_ignores_older_history(events):
    e = events["GM0788"]
    assert e.effective_date == date(2021, 1, 1)
    assert [(r.code, r.inhabitants) for r in e.receivers] == [
        ("GM0757", 2149), ("GM0824", 5827), ("GM0855", 1442), ("GM0865", 4900)]


def test_parse_code_changing_renames(events):
    fm = events["GM1921"]
    assert (fm.kind, fm.effective_date, fm.receivers[0].code) == (h.KIND_RENAME, date(2015, 7, 1), "GM1940")
    assert fm.receivers[0].name == "De Fryske Marren"
    groesbeek = events["GM0241"]
    assert (groesbeek.kind, groesbeek.effective_date, groesbeek.receivers[0].code) == (
        h.KIND_RENAME, date(2016, 1, 1), "GM1945")


def test_lone_dot_separator_ends_block(events, caplog):
    # GM0311 Breukelen uses "\r\n.\r\n" instead of a blank line after the abolition block.
    assert [r.code for r in events["GM0311"].receivers] == ["GM1904"]
    with caplog.at_level(logging.WARNING, logger="nl_housing.harmonise"):
        h.parse_description("GM0311", "Breukelen", "Opgeheven per 01-01-2011, overgegaan naar:\r\n"
                            "- Stichtse Vecht (GM1904),\r\n... 1 hectare met 1 woning en 1 inwoner\r\n.\r\n")
    assert not caplog.records


def test_pre_1930_abolition_without_receivers(events):
    e = events["GM1001"]  # "Opgeheven per 01-01-1923" with no successor listed
    assert e.receivers == () and e.effective_date == date(1923, 1, 1)


def test_rename_to_same_code_is_ignored():
    desc = "Naamswijziging per 01-01-2020,\r\nnieuwe naam: Nieuwe Naam (GM9999)\r\n"
    assert h.parse_description("GM9999", "Oude Naam", desc) == []


def test_multiple_terminating_events_raise():
    desc = ("Opgeheven per 01-01-2019, overgegaan naar:\r\n- A (GM0001),\r\n... 1 hectare met 1 woning en 1 inwoner\r\n\r\n"
            "Naamswijziging per 01-01-2018,\r\nnieuwe naam: B (GM0002)\r\n")
    regions = pd.DataFrame([{"Key": "GM9999  ", "Title": "X", "Description": desc}])
    with pytest.raises(h.HarmonisationError, match="more than one"):
        h.build_events(regions)


# --- Mapping -----------------------------------------------------------------


def test_weesp_merges_into_amsterdam(mapping):
    r = rows(mapping, "GM0457")
    assert list(r.index) == ["GM0363"]
    assert r.loc["GM0363", "weight"] == 1.0
    assert r.loc["GM0363", "change_type"] == h.CHANGE_MERGE
    assert r.loc["GM0363", "effective_date"] == "2022-03-24"
    amsterdam = rows(mapping, "GM0363")
    assert amsterdam.loc["GM0363", "change_type"] == h.CHANGE_UNCHANGED  # identity row for one join


def test_haaren_split_weights_are_inhabitant_shares(mapping):
    r = rows(mapping, "GM0788")
    total = 2149 + 5827 + 1442 + 4900
    assert set(r["change_type"]) == {h.CHANGE_SPLIT}
    for code, inhabitants in [("GM0757", 2149), ("GM0824", 5827), ("GM0855", 1442), ("GM0865", 4900)]:
        assert r.loc[code, "weight"] == pytest.approx(inhabitants / total, abs=1e-6)
    assert r["weight"].sum() == pytest.approx(1.0, abs=1e-12)


def test_de_fryske_marren_both_codes_map_to_gm1940(mapping):
    # 83625NED has 2015 prices for both GM1921 (old name, until 01-07-2015) and GM1940.
    old, new = rows(mapping, "GM1921"), rows(mapping, "GM1940")
    assert list(old.index) == list(new.index) == ["GM1940"]
    assert old.loc["GM1940", "weight"] == new.loc["GM1940", "weight"] == 1.0
    assert old.loc["GM1940", "change_type"] == h.CHANGE_RENAME
    assert old.loc["GM1940", "effective_date"] == "2015-07-01"


def test_groesbeek_rename_and_chain(mapping):
    assert rows(mapping, "GM0241").loc["GM1945", "change_type"] == h.CHANGE_RENAME
    millingen = rows(mapping, "GM0265")  # merged into Groesbeek 2015, renamed Berg en Dal 2016
    assert list(millingen.index) == ["GM1945"]
    assert millingen.loc["GM1945", "change_type"] == h.CHANGE_MERGE
    assert millingen.loc["GM1945", "resolution_path"] == "GM0265>GM0241[2015-01-01]>GM1945[2016-01-01]"


def test_muiden_zero_inhabitant_part_is_dropped(events, mapping):
    assert [r.code for r in events["GM0424"].receivers] == ["GM1942", "GM0457"]
    r = rows(mapping, "GM0424")
    # without dropping, the Weesp part would resolve to Amsterdam with weight 0
    assert list(r.index) == ["GM1942"]
    assert r.loc["GM1942", "weight"] == 1.0
    assert r.loc["GM1942", "change_type"] == h.CHANGE_MERGE


def test_chain_resolution(mapping):
    r = rows(mapping, "GM0571")  # Nieuw-Lekkerland -> Molenwaard (2013) -> Molenlanden (2019)
    assert list(r.index) == ["GM1978"]
    assert r.loc["GM1978", "resolution_path"] == "GM0571>GM1927[2013-01-01]>GM1978[2019-01-01]"
    assert r.loc["GM1978", "effective_date"] == "2013-01-01"  # date the old code ended


def test_split_through_chain(events, mapping):
    # Boarnsterhim (2014) split over 4 municipalities, one of them De Friese Meren -> renamed GM1940
    shares, basis = h.allocation_shares(events["GM0055"])
    assert basis == "inhabitants"
    r = rows(mapping, "GM0055")
    assert set(r.index) == {"GM0074", "GM0080", "GM1900", "GM1940"}
    assert r.loc["GM1940", "weight"] == pytest.approx(shares["GM1921"], abs=1e-6)
    assert r.loc["GM1940", "resolution_path"] == "GM0055>GM1921[2014-01-01]>GM1940[2015-07-01]"


def test_weights_sum_to_one_and_targets_valid(mapping, targets):
    h.validate_mapping(mapping, set(mapping["old_code"]), set(targets))
    assert set(mapping["new_code_2026"]) <= set(targets)
    assert (mapping.groupby("old_code")["weight"].sum() == 1.0).all()  # exact after rounding


def test_rounded_weights_sum_exactly_to_one():
    weights = {"a": 1 / 3, "b": 1 / 3, "c": 1 / 3}
    assert sum(h._round_weights(weights).values()) == 1.0


def test_unresolvable_codes_raise(events, targets, names):
    with pytest.raises(h.HarmonisationError, match="GM1001"):  # abolished 1923 without receivers
        h.build_mapping(["GM1001"], events, targets, names)
    with pytest.raises(h.HarmonisationError, match="no successor"):
        h.resolve("GM0000", events, set(targets))


def test_cycle_raises():
    a = h.SuccessionEvent("GM0001", "A", h.KIND_RENAME, date(2020, 1, 1), (h.Receiver("GM0002", "B"),))
    b = h.SuccessionEvent("GM0002", "B", h.KIND_RENAME, date(2021, 1, 1), (h.Receiver("GM0001", "A"),))
    with pytest.raises(h.HarmonisationError, match="Cycle"):
        h.resolve("GM0001", {"GM0001": a, "GM0002": b}, {"GM0003"})


def test_target_with_terminating_event_raises(events):
    with pytest.raises(h.HarmonisationError, match="also has a terminating event"):
        h.resolve("GM0457", events, {"GM0457", "GM0363"})


def test_weight_fallback_to_dwellings_when_no_inhabitants():
    e = h.SuccessionEvent("GM0001", "A", h.KIND_ABOLITION, date(2020, 1, 1), (
        h.Receiver("GM0002", "B", 1.0, 3, 0), h.Receiver("GM0003", "C", 1.0, 1, 0)))
    shares, basis = h.allocation_shares(e)
    assert basis == "dwellings" and shares == {"GM0002": 0.75, "GM0003": 0.25}


def test_end_date_cross_check(events):
    ends = {"GM0457": date(2022, 3, 24), "GM0363": None, "GM0788": date(2020, 1, 1)}
    problems = h.check_end_dates({k: events[k] for k in ("GM0457", "GM0788")}, ends)
    assert problems == ["GM0788: description says 2021-01-01, Einddatum 2020-01-01"]


# --- Output ------------------------------------------------------------------


def test_output_is_deterministic(events, targets, names, mapping, tmp_path):
    codes = list(mapping["old_code"].unique())
    random.Random(1).shuffle(codes)
    again = h.build_mapping(codes, events, targets, names)
    a, b = tmp_path / "a.csv", tmp_path / "b.csv"
    h.write_mapping(mapping, a)
    h.write_mapping(again, b)
    assert a.read_bytes() == b.read_bytes()
    assert list(pd.read_csv(a).columns) == h.MAPPING_COLUMNS
    assert b"\r\n" not in a.read_bytes()


def test_load_mapping_to_duckdb(mapping, tmp_path):
    csv = h.write_mapping(mapping, tmp_path / "m.csv")
    db = tmp_path / "t.duckdb"
    assert h.load_mapping_to_duckdb(db_path=db, csv_path=csv) == len(mapping)
    assert h.load_mapping_to_duckdb(db_path=db, csv_path=csv) == len(mapping)  # idempotent
    with duckdb.connect(str(db), read_only=True) as con:
        nulls, total = con.execute(
            "SELECT count(*) FILTER (effective_date IS NULL), sum(weight) "
            "FROM reference.municipality_mapping_2026").fetchone()
    assert nulls == (mapping["change_type"] == h.CHANGE_UNCHANGED).sum()
    assert total == pytest.approx(mapping["old_code"].nunique())


# --- Committed reference file ------------------------------------------------


@pytest.mark.skipif(not h.mapping_path().exists(), reason="mapping CSV not generated")
def test_committed_mapping_invariants():
    m = pd.read_csv(h.mapping_path(), dtype=str, keep_default_na=False)
    m["weight"] = m["weight"].astype(float)
    assert list(m.columns) == h.MAPPING_COLUMNS
    assert (m.groupby("old_code")["weight"].sum() - 1.0).abs().max() < 1e-9
    identity = set(m.loc[m["change_type"] == h.CHANGE_UNCHANGED, "old_code"])
    assert set(m["new_code_2026"]) == identity  # every target is a 2026 code with its own identity row
    assert len(identity) == 342                 # 86247NED: 342 municipalities on 1 January 2026
    assert m[["old_code", "new_code_2026"]].apply(tuple, axis=1).is_monotonic_increasing
    assert set(m["change_type"]) <= {h.CHANGE_UNCHANGED, h.CHANGE_RENAME, h.CHANGE_MERGE, h.CHANGE_SPLIT}


def test_boundary_corrections_since_2011(regions):
    bc = h.boundary_corrections(regions, since=date(2011, 1, 1))
    weesp = bc[bc["from_code"] == "GM0457"]
    # "Grenswijziging per 01-01-2016, overgegaan naar: - Gooise Meren (GM1942), ... 4 hectare met 0 woningen en 0 inwoners"
    assert weesp[["to_code", "effective_date", "hectares", "inhabitants"]].values.tolist() == [
        ["GM1942", date(2016, 1, 1), 4.0, 0]]
    assert (bc["effective_date"] >= date(2011, 1, 1)).all()  # Weesp's 2009 correction is excluded


# --- Pseudo-municipalities (GM0998 Buitenland, GM0999 Niet-gemeentelijk ingedeeld) ---------


def test_pseudo_codes_are_excluded(regions, events, targets, names):
    assert {"GM0998", "GM0999"} <= set(regions["Key"])
    # GM0999 has "Opgeheven per 01-01-1996" in its description, but is not a municipality
    assert not set(h.PSEUDO_CODES) & set(events)
    with pytest.raises(h.HarmonisationError, match="Pseudo-municipality"):
        h.build_mapping(["GM0998"], events, targets, names)


def test_pseudo_codes_not_in_boundary_corrections(regions):
    # Eijsden-Margraten (GM1903) <-> Buitenland (GM0998), Grenswijziging 01-01-2018
    bc = h.boundary_corrections(regions, since=date(2011, 1, 1))
    assert not set(bc["from_code"]) & set(h.PSEUDO_CODES)
    assert not set(bc["to_code"]) & set(h.PSEUDO_CODES)


def test_active_codes_exclude_buitenland():
    ends = {"GM0363": None, "GM0998": None, "GM0457": date(2022, 3, 24), "GM0999": date(1996, 1, 1)}
    assert h.active_codes(ends) == {"GM0363"}
    assert h.check_end_dates({}, {"GM0999": date(1996, 1, 1)}) == []

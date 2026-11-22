"""Map historical municipality codes to the municipal division of 1 January 2026.

CBS publishes house prices (``83625NED``) and key figures (``70072ned``) in the
boundaries of each reporting year, while income (``86380NED``) is already in the
2026 division. This module builds the bridge: one row per (historical code,
2026 code) with an allocation weight, so that every historical observation can
be re-allocated with a single join (decision D-007).

Source of the reorganisation history: the free-text ``Description`` field of the
``RegioS`` dimension of ``70739ned`` ("Gebieden; overzicht vanaf 1830"). Two
patterns define a successor (``\\r\\n`` line endings in the raw text)::

    Opgeheven per 01-01-2021, overgegaan naar:
    - Boxtel (GM0757),
    ... 535 hectare met 918 woningen en 2149 inwoners
    - Oisterwijk (GM0824),
    ... 1627 hectare met 2412 woningen en 5827 inwoners

    Naamswijziging per 01-07-2015,
    nieuwe naam: De Fryske Marren (GM1940)

Other blocks (``Grenswijziging``, ``Wijziging``, ``Gemeentelijke herindeling ...
ontvangen van``, ``Ontstaan``) describe boundary corrections or the receiving
side of a merger and do not end a code; they are not used for the mapping
(boundary corrections are a documented limitation, see ``docs/harmonisation.md``).

Allocation weights: when a code is split over several receivers, each receiver
gets the share of *inhabitants* transferred (fallbacks: dwellings, hectares,
equal shares — logged). Parts with weight 0 are dropped. Chains (abolished into
a municipality that was itself abolished or renamed later) are resolved
recursively and the weights multiplied, so the weights of every historical code
sum to 1.

Usage::

    python -m nl_housing.harmonise                 # writes data/reference/municipality_mapping_2026.csv
    python -m nl_housing.harmonise --load-duckdb   # ... and loads it as reference.municipality_mapping_2026
"""

from __future__ import annotations

import argparse
import logging
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

import pandas as pd

from nl_housing import config

logger = logging.getLogger(__name__)

# --- Constants ---------------------------------------------------------------

REORG_TABLE = "70739ned"   # Gebieden; overzicht vanaf 1830 (RegioS descriptions)
TARGET_TABLE = "86247NED"  # Gebieden in Nederland 2026 (342 municipalities)
PRICE_TABLE = "83625NED"   # average sale prices (defines which codes must be covered)

DEFAULT_START_YEAR = 2011
DEFAULT_END_YEAR = 2025

#: GM codes in 70739ned that are not municipalities. GM0998 "Buitenland" (abroad)
#: has no end date, so 70739ned lists 343 active GM codes vs 342 in 86247NED;
#: GM0999 "Niet-gemeentelijk ingedeeld" (unallocated territory) ended 1996.
#: Both are excluded everywhere (events, coverage, boundary corrections).
PSEUDO_CODES: dict[str, str] = {"GM0998": "Buitenland", "GM0999": "Niet-gemeentelijk ingedeeld"}

MAPPING_FILE_NAME = "municipality_mapping_2026.csv"
DUCKDB_SCHEMA = "reference"
DUCKDB_TABLE = "municipality_mapping_2026"

#: Column order of the committed CSV.
MAPPING_COLUMNS = [
    "old_code",
    "old_name",
    "new_code_2026",
    "new_name_2026",
    "weight",
    "change_type",
    "effective_date",
    "source",
    "resolution_path",
]

#: Weights are written with this many decimals (the largest part absorbs rounding).
WEIGHT_DECIMALS = 6

CHANGE_UNCHANGED = "unchanged"
CHANGE_RENAME = "rename"
CHANGE_MERGE = "merge"
CHANGE_SPLIT = "split"

KIND_ABOLITION = "abolition"
KIND_RENAME = "rename"

_DATE = r"(?P<date>\d{2}-\d{2}-\d{4})"
_GM_CODE = r"GM\d{4}"

#: Start of any event block ("Opgeheven per ...", "Grenswijziging per ...", ...).
_BLOCK_HEADER_RE = re.compile(r"^[A-Z][A-Za-z ]* per \d{2}-\d{2}-\d{4}")
_ABOLITION_HEADER_RE = re.compile(rf"^Opgeheven per {_DATE}(?P<rest>.*)$")
_RENAME_RE = re.compile(rf"Naamswijziging per {_DATE},\s*nieuwe naam:\s*(?P<name>.+?)\s*\((?P<code>{_GM_CODE})\)")
_RECEIVER_RE = re.compile(rf"^- (?P<name>.+?) \((?P<code>{_GM_CODE})\),?\s*$")
_DETAIL_RE = re.compile(r"^\.\.\.\s*(?P<text>.*)$")
# Numbers: no thousand separators in the current data, but '.' is accepted and
# stripped defensively; hectares can use a decimal comma ("0,17 hectare").
_HECTARES_RE = re.compile(r"(?P<n>\d+(?:,\d+)?)\s+hectare")
_DWELLINGS_RE = re.compile(r"(?P<n>\d[\d.]*)\s+woning(?:en)?\b")
_INHABITANTS_RE = re.compile(r"(?P<n>\d[\d.]*)\s+inwoners?\b")


class HarmonisationError(ValueError):
    """Raised when the reorganisation history is inconsistent or incomplete."""


# --- Parsing -----------------------------------------------------------------


@dataclass(frozen=True)
class Receiver:
    """One municipality that received (part of) an abolished municipality."""

    code: str
    name: str
    hectares: float | None = None
    dwellings: int | None = None
    inhabitants: int | None = None


@dataclass(frozen=True)
class SuccessionEvent:
    """The event that ended a municipality code (abolition or code-changing rename)."""

    old_code: str
    old_name: str
    kind: str  # KIND_ABOLITION or KIND_RENAME
    effective_date: date
    receivers: tuple[Receiver, ...] = field(default_factory=tuple)


def _parse_date(text: str) -> date:
    return datetime.strptime(text, "%d-%m-%Y").date()


def _parse_int(text: str) -> int:
    return int(text.replace(".", ""))


def parse_detail_line(text: str) -> tuple[float | None, int | None, int | None]:
    """Parse ``"535 hectare met 918 woningen en 2149 inwoners"`` -> ``(535.0, 918, 2149)``.

    Every part is optional (old records have only inhabitants; a few lines lack
    "met"; singular forms "1 woning", "1 inwoner" occur).
    """
    ha = _HECTARES_RE.search(text)
    dw = _DWELLINGS_RE.search(text)
    inh = _INHABITANTS_RE.search(text)
    return (
        float(ha.group("n").replace(",", ".")) if ha else None,
        _parse_int(dw.group("n")) if dw else None,
        _parse_int(inh.group("n")) if inh else None,
    )


def _normalise_lines(description: str) -> list[str]:
    return [line.strip() for line in description.replace("\r\n", "\n").replace("\r", "\n").split("\n")]


def _parse_abolition(lines: list[str], start: int) -> tuple[date, list[Receiver]]:
    """Parse the receivers that follow the ``Opgeheven per ...`` header at ``lines[start]``."""
    header = _ABOLITION_HEADER_RE.match(lines[start])
    assert header is not None
    return _parse_date(header.group("date")), _parse_receivers(lines, start)


def _parse_receivers(lines: list[str], start: int) -> list[Receiver]:
    """Parse the ``- <name> (GMxxxx),`` / ``... <numbers>`` pairs after the header at ``lines[start]``."""
    receivers: list[dict] = []
    for line in lines[start + 1:]:
        # A block ends at a blank line, a lone "." (used as separator in 5 records,
        # e.g. GM0311 Breukelen), the next event header or the start-date line.
        if line in ("", ".") or _BLOCK_HEADER_RE.match(line) or line.startswith("Begindatum"):
            break
        if m := _RECEIVER_RE.match(line):
            receivers.append({"code": m.group("code"), "name": m.group("name")})
        elif (m := _DETAIL_RE.match(line)) and receivers:
            ha, dw, inh = parse_detail_line(m.group("text"))
            receivers[-1].update(hectares=ha, dwellings=dw, inhabitants=inh)
        else:
            logger.warning("Unrecognised line in event block: %r", line)
    return [Receiver(**r) for r in receivers]


_BOUNDARY_OUT_RE = re.compile(rf"^(?:Grenswijziging|Wijziging) per {_DATE}, overgegaan naar:$")


def boundary_corrections(regions: pd.DataFrame, since: date) -> pd.DataFrame:
    """Boundary corrections (``Grenswijziging``) between municipalities that keep their code.

    These are NOT modelled in the mapping (a code maps to its successor as a
    whole). This function only quantifies the limitation: one row per transfer
    on or after ``since``, read from the sending municipality's description.
    """
    rows = []
    for key, title, desc in regions[["Key", "Title", "Description"]].itertuples(index=False):
        code = str(key).strip()
        if not code.startswith("GM") or code in PSEUDO_CODES or pd.isna(desc):
            continue
        lines = _normalise_lines(str(desc))
        for i, line in enumerate(lines):
            m = _BOUNDARY_OUT_RE.match(line)
            if not m or (eff := _parse_date(m.group("date"))) < since:
                continue
            for r in _parse_receivers(lines, i):
                if r.code in PSEUDO_CODES:  # e.g. Eijsden-Margraten <-> abroad (2018, 0 inhabitants)
                    continue
                rows.append({"from_code": code, "from_name": str(title).strip(), "to_code": r.code,
                             "to_name": r.name, "effective_date": eff, "hectares": r.hectares,
                             "dwellings": r.dwellings, "inhabitants": r.inhabitants})
    cols = ["from_code", "from_name", "to_code", "to_name", "effective_date", "hectares", "dwellings", "inhabitants"]
    return pd.DataFrame(rows, columns=cols).sort_values(["effective_date", "from_code", "to_code"], ignore_index=True)


def parse_description(code: str, name: str, description: str | None) -> list[SuccessionEvent]:
    """Extract the events that ended ``code`` from its ``70739ned/RegioS`` description.

    Returns an empty list for codes that still exist (or whose history only
    contains boundary corrections). A well-formed history yields at most one
    event; :func:`build_events` raises if there are more.
    """
    if not description:
        return []
    events: list[SuccessionEvent] = []
    lines = _normalise_lines(description)
    for i, line in enumerate(lines):
        if _ABOLITION_HEADER_RE.match(line):
            eff, receivers = _parse_abolition(lines, i)
            events.append(SuccessionEvent(code, name, KIND_ABOLITION, eff, tuple(receivers)))

    for m in _RENAME_RE.finditer(description):
        new_code = m.group("code")
        if new_code == code:  # name change without a code change: nothing to map
            continue
        events.append(SuccessionEvent(code, name, KIND_RENAME, _parse_date(m.group("date")),
                                      (Receiver(code=new_code, name=m.group("name")),)))
    return events


def build_events(regions: pd.DataFrame) -> dict[str, SuccessionEvent]:
    """Parse all GM descriptions of ``70739ned/RegioS`` into ``{old_code: event}``.

    ``regions`` needs the columns ``Key``, ``Title`` and ``Description`` (keys may
    be space-padded, as delivered by CBS).
    """
    events: dict[str, SuccessionEvent] = {}
    for key, title, desc in regions[["Key", "Title", "Description"]].itertuples(index=False):
        code = str(key).strip()
        if not code.startswith("GM") or code in PSEUDO_CODES:
            continue
        found = parse_description(code, str(title).strip(), None if pd.isna(desc) else str(desc))
        if len(found) > 1:
            raise HarmonisationError(f"{code}: more than one terminating event: {found}")
        if found:
            events[code] = found[0]
    logger.info("Parsed %d terminating events (%d abolitions, %d code-changing renames)",
                len(events), sum(e.kind == KIND_ABOLITION for e in events.values()),
                sum(e.kind == KIND_RENAME for e in events.values()))
    return events


# --- Allocation weights ------------------------------------------------------


def allocation_shares(event: SuccessionEvent) -> tuple[dict[str, float], str]:
    """Shares of ``event.old_code`` allocated to each direct receiver, and the basis used.

    Basis: inhabitants transferred; if they are missing or all zero, dwellings,
    then hectares, then equal shares. Receivers with share 0 are dropped
    (e.g. GM0424 Muiden -> GM0457 Weesp, "235 hectare met 0 woningen en 0 inwoners").
    """
    if not event.receivers:
        raise HarmonisationError(f"{event.old_code}: abolished without receivers")
    if event.kind == KIND_RENAME:
        return {event.receivers[0].code: 1.0}, "rename"
    if len({r.code for r in event.receivers}) == 1:
        return {event.receivers[0].code: 1.0}, "single"

    for basis in ("inhabitants", "dwellings", "hectares"):
        values = [getattr(r, basis) for r in event.receivers]
        if all(v is not None for v in values) and sum(values) > 0:
            break
    else:
        basis, values = "equal", [1.0] * len(event.receivers)
    if basis != "inhabitants":
        logger.warning("%s: weights based on %s (inhabitants missing or zero)", event.old_code, basis)

    total = float(sum(values))
    shares: dict[str, float] = defaultdict(float)
    for receiver, value in zip(event.receivers, values):
        if value > 0:
            shares[receiver.code] += value / total
        else:
            logger.info("%s -> %s dropped: %s transferred = 0", event.old_code, receiver.code, basis)
    return dict(shares), basis


@dataclass
class _Allocation:
    weight: float = 0.0
    paths: list[str] = field(default_factory=list)
    bases: set[str] = field(default_factory=set)
    kinds: set[str] = field(default_factory=set)


def resolve(code: str, events: dict[str, SuccessionEvent], targets: set[str],
            _stack: tuple[str, ...] = ()) -> dict[str, _Allocation]:
    """Resolve ``code`` to the target list, following chains recursively.

    Returns ``{target_code: allocation}`` with weights that sum to 1. Raises
    :class:`HarmonisationError` for cycles, dead ends (abolished code without a
    successor event) and target codes that also have a terminating event.
    """
    if code in _stack:
        raise HarmonisationError(f"Cycle in reorganisation history: {' -> '.join(_stack + (code,))}")
    if code in targets:
        if code in events:
            raise HarmonisationError(f"{code} is in the target list but also has a terminating event")
        return {code: _Allocation(weight=1.0, paths=[code])}
    if code not in events:
        raise HarmonisationError(f"{code} is not in the target list and has no successor in {REORG_TABLE}")

    event = events[code]
    shares, basis = allocation_shares(event)
    result: dict[str, _Allocation] = defaultdict(_Allocation)
    for receiver_code, share in sorted(shares.items()):
        for target, sub in resolve(receiver_code, events, targets, _stack + (code,)).items():
            alloc = result[target]
            alloc.weight += share * sub.weight
            # sub-paths start with receiver_code; annotate that hop with the event date
            hop = f"{code}>{receiver_code}[{event.effective_date.isoformat()}]"
            alloc.paths += [hop + p[len(receiver_code):] for p in sub.paths]
            alloc.bases |= {basis} | sub.bases
            alloc.kinds |= {event.kind} | sub.kinds
    return dict(result)


def _round_weights(weights: dict[str, float]) -> dict[str, float]:
    """Round to WEIGHT_DECIMALS so that the rounded weights still sum to exactly 1."""
    rounded = {k: round(v, WEIGHT_DECIMALS) for k, v in weights.items()}
    largest = max(rounded, key=lambda k: (weights[k], k))
    rounded[largest] = round(1.0 - sum(v for k, v in rounded.items() if k != largest), WEIGHT_DECIMALS)
    return rounded


# --- Mapping table -----------------------------------------------------------


def build_mapping(codes: list[str] | set[str], events: dict[str, SuccessionEvent],
                  targets: dict[str, str], names: dict[str, str]) -> pd.DataFrame:
    """Build the mapping for ``codes`` (historical GM codes to cover).

    ``targets``: ``{code_2026: name_2026}``; ``names``: ``{code: latest name}``
    from ``70739ned``. Codes that still exist in 2026 get an identity row
    (``change_type = unchanged``), so a single join covers every observation.
    Output is sorted by ``old_code, new_code_2026`` (deterministic diffs).
    """
    target_set = set(targets)
    pseudo = sorted(set(codes) & set(PSEUDO_CODES))
    if pseudo:
        raise HarmonisationError(f"Pseudo-municipality codes cannot be mapped: {pseudo}")
    rows: list[dict] = []
    errors: list[str] = []
    for code in sorted(set(codes)):
        try:
            allocations = resolve(code, events, target_set)
        except HarmonisationError as exc:
            errors.append(str(exc))
            continue
        weights = _round_weights({t: a.weight for t, a in allocations.items()})
        event = events.get(code)
        for target in sorted(allocations):
            alloc = allocations[target]
            if event is None:
                change_type = CHANGE_UNCHANGED
            elif len(allocations) > 1:
                change_type = CHANGE_SPLIT
            elif KIND_ABOLITION in alloc.kinds:
                change_type = CHANGE_MERGE
            else:
                change_type = CHANGE_RENAME
            bases = sorted(alloc.bases - {"rename", "single"})  # only report the basis of real splits
            source = (f"{TARGET_TABLE} (identity)" if event is None
                      else f"{REORG_TABLE} RegioS.Description" + (f" (weight: {'+'.join(bases)})" if bases else ""))
            rows.append({
                "old_code": code,
                "old_name": names.get(code, targets.get(code, "")),
                "new_code_2026": target,
                "new_name_2026": targets[target],
                "weight": weights[target],
                "change_type": change_type,
                "effective_date": event.effective_date.isoformat() if event else "",
                "source": source,
                "resolution_path": "; ".join(sorted(alloc.paths)),
            })
    if errors:
        raise HarmonisationError(f"{len(errors)} code(s) could not be resolved:\n" + "\n".join(errors))
    return pd.DataFrame(rows, columns=MAPPING_COLUMNS)


def validate_mapping(mapping: pd.DataFrame, codes: set[str], targets: set[str]) -> None:
    """Hard checks on the mapping; raises :class:`HarmonisationError` on the first failure."""
    sums = mapping.groupby("old_code")["weight"].sum()
    bad = sums[(sums - 1.0).abs() > 1e-9]
    if not bad.empty:
        raise HarmonisationError(f"Weights do not sum to 1 for: {bad.to_dict()}")
    if (mapping["weight"] <= 0).any():
        raise HarmonisationError("Mapping contains non-positive weights")
    unknown = set(mapping["new_code_2026"]) - targets
    if unknown:
        raise HarmonisationError(f"Target codes not in the 2026 list: {sorted(unknown)}")
    missing = codes - set(mapping["old_code"])
    if missing:
        raise HarmonisationError(f"Codes without a mapping: {sorted(missing)}")
    if mapping.duplicated(["old_code", "new_code_2026"]).any():
        raise HarmonisationError("Duplicate (old_code, new_code_2026) pairs")


def check_end_dates(events: dict[str, SuccessionEvent], end_dates: dict[str, date | None]) -> list[str]:
    """Cross-check parsed event dates with ``Einddatum`` in the ``70739ned`` data columns.

    Returns human-readable mismatches (logged as warnings, not fatal: the data
    columns are an independent second source within the same table).
    """
    problems = []
    for code, event in sorted(events.items()):
        end = end_dates.get(code)
        if end != event.effective_date:
            problems.append(f"{code}: description says {event.effective_date}, Einddatum {end}")
    for code, end in sorted(end_dates.items()):
        if end is not None and code not in events and code not in PSEUDO_CODES:
            problems.append(f"{code}: Einddatum {end} but no terminating event in the description")
    return problems


def active_codes(end_dates: dict[str, date | None]) -> set[str]:
    """GM codes without an end date in ``70739ned``, excluding :data:`PSEUDO_CODES`.

    Must equal the 2026 list (``86247NED``); :func:`run` fails otherwise.
    """
    return {code for code, end in end_dates.items() if end is None and code not in PSEUDO_CODES}


def summarise(mapping: pd.DataFrame, events: dict[str, SuccessionEvent], since: date) -> dict:
    """Figures used to check the research claims (docs/cbs_tables_research.md section 5)."""
    per_target = mapping.groupby("new_code_2026")["old_code"].nunique()
    recent = [e for e in events.values() if e.effective_date >= since]
    abolitions = [e for e in recent if e.kind == KIND_ABOLITION]
    return {
        "codes_covered": int(mapping["old_code"].nunique()),
        "target_codes_reached": int(mapping["new_code_2026"].nunique()),
        "identity_codes": int((mapping["change_type"] == CHANGE_UNCHANGED).sum()),
        "targets_from_one_code": int((per_target == 1).sum()),
        "targets_from_several_codes": int((per_target > 1).sum()),
        "rows": int(len(mapping)),
        "change_type_codes": mapping.drop_duplicates("old_code")["change_type"].value_counts().sort_index().to_dict(),
        "events_total": len(events),
        "abolitions_total": sum(e.kind == KIND_ABOLITION for e in events.values()),
        "abolitions_since": len(abolitions),
        "abolition_receiver_rows_since": sum(len(e.receivers) for e in abolitions),
        "abolitions_by_year": dict(sorted(Counter(e.effective_date.year for e in abolitions).items())),
        "renames_since": sorted(f"{e.old_code}->{e.receivers[0].code}" for e in recent if e.kind == KIND_RENAME),
        "splits_since": {e.old_code: len(e.receivers) for e in sorted(abolitions, key=lambda e: e.old_code)
                         if len(e.receivers) > 1},
    }


# --- I/O ---------------------------------------------------------------------


def _table_dir(table_id: str, root: Path) -> Path:
    """``data/raw/<table_id>`` matched case-insensitively (the config spelling varies)."""
    raw = config.raw_dir(root)
    for candidate in raw.iterdir() if raw.exists() else []:
        if candidate.is_dir() and candidate.name.lower() == table_id.lower():
            return candidate
    raise FileNotFoundError(f"{table_id} not found in {raw}; run `python -m nl_housing.ingest --table {table_id}`")


def mapping_path(root: Path = config.REPO_ROOT) -> Path:
    """Location of the committed mapping: ``data/reference/municipality_mapping_2026.csv``."""
    return root / "data" / "reference" / MAPPING_FILE_NAME


def load_regions(root: Path = config.REPO_ROOT) -> pd.DataFrame:
    """``70739ned`` RegioS dimension (Key, Title, Description)."""
    return pd.read_parquet(_table_dir(REORG_TABLE, root) / "dimensions" / "RegioS.parquet")


def load_end_dates(root: Path = config.REPO_ROOT) -> dict[str, date | None]:
    """``Einddatum`` per GM code from the ``70739ned`` data columns (sort field YYYYMMDD)."""
    df = pd.read_parquet(_table_dir(REORG_TABLE, root) / "typed_dataset.parquet",
                         columns=["RegioS", "EinddatumSorteerveld_7"])
    out: dict[str, date | None] = {}
    for key, end in df.itertuples(index=False):
        code = str(key).strip()
        if code.startswith("GM"):
            end = None if pd.isna(end) else str(end).strip()
            out[code] = datetime.strptime(end, "%Y%m%d").date() if end else None
    return out


def load_targets(root: Path = config.REPO_ROOT) -> dict[str, str]:
    """``{code: name}`` of the 2026 municipalities (``86247NED``; keys are padded)."""
    df = pd.read_parquet(_table_dir(TARGET_TABLE, root) / "typed_dataset.parquet", columns=["Code_1", "Naam_2"])
    return {str(c).strip(): str(n).strip() for c, n in df.itertuples(index=False)}


def load_price_codes(start_year: int, end_year: int, root: Path = config.REPO_ROOT) -> set[str]:
    """GM codes with a non-missing average price in ``83625NED`` for the given years."""
    df = pd.read_parquet(_table_dir(PRICE_TABLE, root) / "typed_dataset.parquet",
                         columns=["RegioS", "Perioden", "GemiddeldeVerkoopprijs_1"])
    df["RegioS"] = df["RegioS"].str.strip()
    year = df["Perioden"].str[:4].astype(int)
    mask = (df["RegioS"].str.startswith("GM") & ~df["RegioS"].isin(PSEUDO_CODES)
            & year.between(start_year, end_year) & df["GemiddeldeVerkoopprijs_1"].notna())
    return set(df.loc[mask, "RegioS"])


def write_mapping(mapping: pd.DataFrame, path: Path) -> Path:
    """Write the mapping as UTF-8 CSV with ``\\n`` line endings and fixed weight precision."""
    path.parent.mkdir(parents=True, exist_ok=True)
    mapping.to_csv(path, index=False, lineterminator="\n", float_format=f"%.{WEIGHT_DECIMALS}f")
    logger.info("Wrote %d rows to %s", len(mapping), path)
    return path


def load_mapping_to_duckdb(db_path: Path | None = None, csv_path: Path | None = None,
                           root: Path = config.REPO_ROOT) -> int:
    """(Re)create ``reference.municipality_mapping_2026`` in DuckDB from the CSV. Returns the row count.

    Standalone on purpose (does not touch the raw loader). Types are explicit so
    that empty ``effective_date`` values load as NULL dates.
    """
    import duckdb

    db_path = db_path or config.duckdb_path(root)
    csv_path = csv_path or mapping_path(root)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with duckdb.connect(str(db_path)) as con:
        con.execute(f"CREATE SCHEMA IF NOT EXISTS {DUCKDB_SCHEMA}")
        con.execute(
            f"""CREATE OR REPLACE TABLE {DUCKDB_SCHEMA}.{DUCKDB_TABLE} AS
                SELECT * FROM read_csv(?, header = true, columns = {{
                    'old_code': 'VARCHAR', 'old_name': 'VARCHAR', 'new_code_2026': 'VARCHAR',
                    'new_name_2026': 'VARCHAR', 'weight': 'DOUBLE', 'change_type': 'VARCHAR',
                    'effective_date': 'DATE', 'source': 'VARCHAR', 'resolution_path': 'VARCHAR'}})""",
            [str(csv_path)],
        )
        n = con.execute(f"SELECT count(*) FROM {DUCKDB_SCHEMA}.{DUCKDB_TABLE}").fetchone()[0]
    logger.info("Loaded %d rows into %s.%s", n, DUCKDB_SCHEMA, DUCKDB_TABLE)
    return int(n)


def run(start_year: int = DEFAULT_START_YEAR, end_year: int = DEFAULT_END_YEAR,
        root: Path = config.REPO_ROOT, output: Path | None = None) -> tuple[pd.DataFrame, dict]:
    """Regenerate the mapping CSV from ``data/raw/``. Returns the mapping and its summary."""
    regions = load_regions(root)
    events = build_events(regions)
    names = {str(k).strip(): str(t).strip() for k, t in regions[["Key", "Title"]].itertuples(index=False)}
    targets = load_targets(root)
    codes = load_price_codes(start_year, end_year, root)
    logger.info("%d target municipalities (%s); %d GM codes with a price in %s %d-%d",
                len(targets), TARGET_TABLE, len(codes), PRICE_TABLE, start_year, end_year)

    end_dates = load_end_dates(root)
    for problem in check_end_dates(events, end_dates):
        logger.warning("End-date check: %s", problem)
    active = active_codes(end_dates)
    if active != set(targets):
        raise HarmonisationError(f"Active codes in {REORG_TABLE} differ from {TARGET_TABLE}: "
                                 f"only in {REORG_TABLE} {sorted(active - set(targets))}, "
                                 f"only in {TARGET_TABLE} {sorted(set(targets) - active)}")

    mapping = build_mapping(codes, events, targets, names)
    validate_mapping(mapping, codes, set(targets))
    write_mapping(mapping, output or mapping_path(root))
    summary = summarise(mapping, events, since=date(start_year, 1, 1))
    corrections = boundary_corrections(regions, since=date(start_year, 1, 1))
    largest = corrections.nlargest(3, "inhabitants")
    summary["boundary_corrections_since"] = {
        "transfers": int(len(corrections)),
        "inhabitants_total": int(corrections["inhabitants"].fillna(0).sum()),
        "dwellings_total": int(corrections["dwellings"].fillna(0).sum()),
        "transfers_with_100_plus_inhabitants": int((corrections["inhabitants"] >= 100).sum()),
        "largest": [f"{r.from_code}->{r.to_code} {r.effective_date} {r.inhabitants} inh."
                    for r in largest.itertuples(index=False)],
    }
    for key, value in summary.items():
        logger.info("%s: %s", key, value)
    return mapping, summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the historical -> 2026 municipality code mapping.")
    parser.add_argument("--start-year", type=int, default=DEFAULT_START_YEAR)
    parser.add_argument("--end-year", type=int, default=DEFAULT_END_YEAR)
    parser.add_argument("--output", type=Path, help=f"CSV path (default data/reference/{MAPPING_FILE_NAME})")
    parser.add_argument("--load-duckdb", action="store_true",
                        help=f"also load the CSV into {DUCKDB_SCHEMA}.{DUCKDB_TABLE} in data/nl_housing.duckdb")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    try:
        run(args.start_year, args.end_year, output=args.output)
    except (HarmonisationError, FileNotFoundError) as exc:
        logger.error("%s", exc)
        return 1
    if args.load_duckdb:
        load_mapping_to_duckdb(csv_path=args.output)
    return 0


if __name__ == "__main__":
    sys.exit(main())

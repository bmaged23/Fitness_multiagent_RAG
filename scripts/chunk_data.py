"""
Chunk both dataset CSVs into JSONL files ready for embed_and_index.py.

Outputs:
    data/processed/program_chunks.jsonl   — one record per program  (~2,598)
    data/processed/exercise_chunks.jsonl  — one record per unique exercise (~3,213)

Usage:
    python scripts/chunk_data.py
"""

import sys
import ast
import json
import uuid
import logging
from pathlib import Path

import pandas as pd
import numpy as np
from tqdm import tqdm

sys.path.insert(0, str(Path(__file__).parent.parent))
from config.settings import (
    EXERCISES_CSV, PROGRAMS_CSV,
    EXERCISE_CHUNK_BATCH_SIZE, SETS_CAP, REPS_TIME_BASED_CAP_SECONDS,
    PROGRAM_CHUNKS_JSONL, EXERCISE_CHUNKS_JSONL,
    P_CHUNK_ID, P_SOURCE_TABLE, P_TEXT, P_TITLE,
    P_GOAL, P_LEVEL, P_EQUIPMENT,
    P_DESCRIPTION, P_PROGRAM_LENGTH_WEEKS, P_TIME_PER_WORKOUT_MIN,
    P_TOTAL_EXERCISES, P_CREATED, P_LAST_EDIT,
    P_EXERCISE_NAME, P_SETS_MEDIAN, P_SETS_MIN, P_SETS_MAX,
    P_REPS_MEDIAN, P_REPS_MIN, P_REPS_MAX,
    P_IS_TIME_BASED, P_INTENSITY_MEDIAN, P_PROGRAMS, P_OCCURRENCE_COUNT,
    SOURCE_PROGRAMS, SOURCE_EXERCISES,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def safe_parse_list(val: str) -> list[str]:
    try:
        result = ast.literal_eval(val)
        return result if isinstance(result, list) else [result]
    except Exception:
        return [val] if pd.notna(val) else []


def make_chunk_id() -> str:
    return str(uuid.uuid4())


def safe_int(val) -> int | None:
    try:
        v = int(val)
        return None if np.isnan(float(val)) else v
    except Exception:
        return None


def write_jsonl(records: list[dict], path: Path) -> None:
    with open(path, "a", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")


# ---------------------------------------------------------------------------
# Program chunks — one record per row in program_summary.csv
# ---------------------------------------------------------------------------

def build_program_text(row: pd.Series) -> str:
    goals  = ", ".join(row["goal_list"])
    levels = ", ".join(row["level_list"])
    dur    = (f"{int(row['program_length'])} weeks"
              if pd.notna(row["program_length"]) else "unknown duration")
    tpw    = (f"{int(row['time_per_workout'])} min/session"
              if pd.notna(row["time_per_workout"]) else "")
    header = (
        f"Title: {row['title']}\n"
        f"Goal: {goals}\n"
        f"Level: {levels}\n"
        f"Equipment: {row['equipment']}\n"
        f"Duration: {dur}" + (f" | {tpw}" if tpw else "") + "\n"
    )
    return header + "\n" + str(row["description"])


def chunk_programs() -> int:
    log.info("Loading %s …", PROGRAMS_CSV.name)
    df = pd.read_csv(PROGRAMS_CSV)
    log.info("  %d rows loaded", len(df))

    # parse list columns
    df["goal_list"]  = df["goal"].apply(safe_parse_list)
    df["level_list"] = df["level"].apply(safe_parse_list)

    # drop rows with no description (can't build meaningful chunk)
    before = len(df)
    df = df[df["description"].notna()].reset_index(drop=True)
    dropped = before - len(df)
    if dropped:
        log.warning("  Dropped %d rows with null description", dropped)

    PROGRAM_CHUNKS_JSONL.parent.mkdir(parents=True, exist_ok=True)
    PROGRAM_CHUNKS_JSONL.unlink(missing_ok=True)

    records = []
    for _, row in tqdm(df.iterrows(), total=len(df), desc="Program chunks"):
        text = build_program_text(row)

        record = {
            P_CHUNK_ID:              make_chunk_id(),
            P_SOURCE_TABLE:          SOURCE_PROGRAMS,
            P_TEXT:                  text,
            P_TITLE:                 str(row["title"]),
            P_DESCRIPTION:           str(row["description"]),
            P_GOAL:                  row["goal_list"],
            P_LEVEL:                 row["level_list"],
            P_EQUIPMENT:             str(row["equipment"]) if pd.notna(row["equipment"]) else None,
            P_PROGRAM_LENGTH_WEEKS:  safe_int(row["program_length"]),
            P_TIME_PER_WORKOUT_MIN:  safe_int(row["time_per_workout"]),
            P_TOTAL_EXERCISES:       safe_int(row["total_exercises"]),
            P_CREATED:               str(row["created"])  if pd.notna(row["created"])   else None,
            P_LAST_EDIT:             str(row["last_edit"]) if pd.notna(row["last_edit"]) else None,
        }
        records.append(record)

        if len(records) >= EXERCISE_CHUNK_BATCH_SIZE:
            write_jsonl(records, PROGRAM_CHUNKS_JSONL)
            records.clear()

    if records:
        write_jsonl(records, PROGRAM_CHUNKS_JSONL)

    count = sum(1 for _ in open(PROGRAM_CHUNKS_JSONL, encoding="utf-8"))
    log.info("  Written %d program chunks → %s", count, PROGRAM_CHUNKS_JSONL)
    return count


# ---------------------------------------------------------------------------
# Exercise chunks — deduplicated by exercise_name
# ---------------------------------------------------------------------------

def union_lists(series: pd.Series) -> list[str]:
    """Union all parsed lists in a Series of already-parsed list values."""
    return sorted(set(v for lst in series for v in lst))


def build_exercise_text(name: str, equipment: list, goals: list, levels: list,
                        sets_med: int, reps_med: int, is_time: bool,
                        intensity_med: int, count: int) -> str:
    equip_str = ", ".join(equipment) if equipment else "any"
    goal_str  = ", ".join(goals)     if goals     else "general"
    level_str = ", ".join(levels)    if levels    else "all levels"
    reps_str  = f"{reps_med} s" if is_time else f"{reps_med} reps"
    return (
        f"Exercise: {name} | "
        f"Equipment: {equip_str} | "
        f"Goals: {goal_str} | "
        f"Levels: {level_str} | "
        f"Prescription: {sets_med} sets x {reps_str} | "
        f"Intensity: {intensity_med}/10 | "
        f"Appears in {count} programs"
    )


def chunk_exercises() -> int:
    log.info("Loading %s …", EXERCISES_CSV.name)
    df = pd.read_csv(EXERCISES_CSV)
    log.info("  %d rows loaded", len(df))

    # parse list columns up front (once, not per-group)
    log.info("  Parsing goal/level list columns …")
    df["goal_list"]  = df["goal"].apply(safe_parse_list)
    df["level_list"] = df["level"].apply(safe_parse_list)

    # clean reps: abs value, cap time-based outliers
    df["reps_abs"] = df["reps"].abs().clip(upper=REPS_TIME_BASED_CAP_SECONDS)
    df["is_time_based_row"] = df["reps"] < 0

    # clean sets
    df["sets_clean"] = df["sets"].clip(upper=SETS_CAP)

    # drop rows with null exercise_name (none expected but guard anyway)
    before = len(df)
    df = df[df["exercise_name"].notna()].reset_index(drop=True)
    if len(df) < before:
        log.warning("  Dropped %d rows with null exercise_name", before - len(df))

    log.info("  Grouping by exercise_name (%d unique) …", df["exercise_name"].nunique())

    EXERCISE_CHUNKS_JSONL.parent.mkdir(parents=True, exist_ok=True)
    EXERCISE_CHUNKS_JSONL.unlink(missing_ok=True)

    records = []

    for name, grp in tqdm(df.groupby("exercise_name", sort=False),
                          desc="Exercise chunks",
                          total=df["exercise_name"].nunique()):

        equipment = sorted(grp["equipment"].dropna().unique().tolist())
        goals     = union_lists(grp["goal_list"])
        levels    = union_lists(grp["level_list"])
        programs  = sorted(grp["title"].dropna().unique().tolist())

        sets_med = int(grp["sets_clean"].median())
        sets_min = int(grp["sets_clean"].min())
        sets_max = int(grp["sets_clean"].max())

        reps_med = int(grp["reps_abs"].median())
        reps_min = int(grp["reps_abs"].min())
        reps_max = int(grp["reps_abs"].max())

        is_time  = bool(grp["is_time_based_row"].sum() > len(grp) / 2)
        intensity_med = int(grp["intensity"].median())
        count = len(grp)

        text = build_exercise_text(
            name, equipment, goals, levels,
            sets_med, reps_med, is_time, intensity_med, count,
        )

        record = {
            P_CHUNK_ID:        make_chunk_id(),
            P_SOURCE_TABLE:    SOURCE_EXERCISES,
            P_TEXT:            text,
            P_EXERCISE_NAME:   str(name),
            P_EQUIPMENT:       equipment,
            P_GOAL:            goals,
            P_LEVEL:           levels,
            P_SETS_MEDIAN:     sets_med,
            P_SETS_MIN:        sets_min,
            P_SETS_MAX:        sets_max,
            P_REPS_MEDIAN:     reps_med,
            P_REPS_MIN:        reps_min,
            P_REPS_MAX:        reps_max,
            P_IS_TIME_BASED:   is_time,
            P_INTENSITY_MEDIAN: intensity_med,
            P_PROGRAMS:        programs,
            P_OCCURRENCE_COUNT: count,
        }
        records.append(record)

        if len(records) >= EXERCISE_CHUNK_BATCH_SIZE:
            write_jsonl(records, EXERCISE_CHUNKS_JSONL)
            records.clear()

    if records:
        write_jsonl(records, EXERCISE_CHUNKS_JSONL)

    count = sum(1 for _ in open(EXERCISE_CHUNKS_JSONL, encoding="utf-8"))
    log.info("  Written %d exercise chunks → %s", count, EXERCISE_CHUNKS_JSONL)
    return count


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    DATA_PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    log.info("=" * 60)
    log.info("Step 1/2 — Program chunks")
    log.info("=" * 60)
    n_programs = chunk_programs()

    log.info("=" * 60)
    log.info("Step 2/2 — Exercise chunks (deduplicated)")
    log.info("=" * 60)
    n_exercises = chunk_exercises()

    log.info("=" * 60)
    log.info("Done.")
    log.info("  Program chunks:  %d  →  %s", n_programs,  PROGRAM_CHUNKS_JSONL)
    log.info("  Exercise chunks: %d  →  %s", n_exercises, EXERCISE_CHUNKS_JSONL)
    log.info("Next step: python scripts/embed_and_index.py")
    log.info("=" * 60)


if __name__ == "__main__":
    main()

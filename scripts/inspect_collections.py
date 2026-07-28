"""
Health check and detailed inspection of the two Qdrant collections.

Prints:
  - Qdrant server info
  - Per-collection: status, counts, vector config, optimizer state,
    payload indexes, payload field distributions, sample points

Exit codes:
  0  — all collections healthy
  1  — connection failure or unhealthy collection

Usage:
    python scripts/inspect_collections.py
"""

import sys
import json
import logging
from pathlib import Path

from qdrant_client import QdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchValue, MatchAny

sys.path.insert(0, str(Path(__file__).parent.parent))
from config.settings import (
    QDRANT_URL, QDRANT_API_KEY,
    QDRANT_PROGRAMS_COLLECTION, QDRANT_EXERCISES_COLLECTION,
    P_GOAL, P_LEVEL, P_EQUIPMENT, P_IS_TIME_BASED,
    P_PROGRAM_LENGTH_WEEKS, P_TIME_PER_WORKOUT_MIN,
    P_EXERCISE_NAME,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

# Known categorical values for distribution checks
KNOWN_GOALS = [
    "Bodybuilding", "Muscle & Sculpting", "Powerbuilding",
    "Athletics", "Powerlifting", "Bodyweight Fitness",
    "Olympic Weightlifting", "At-Home & Calisthenics",
]
KNOWN_LEVELS     = ["Beginner", "Novice", "Intermediate", "Advanced"]
KNOWN_EQUIPMENT  = ["Full Gym", "Garage Gym", "At Home", "Dumbbell Only"]

W = 70  # separator width


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

def sep(char: str = "=") -> None:
    log.info(char * W)


def header(title: str) -> None:
    sep()
    log.info("  %s", title)
    sep()


def section(title: str) -> None:
    sep("-")
    log.info("  %s", title)
    sep("-")


def kv(label: str, value) -> None:
    log.info("  %-32s %s", label, value)


def truncate(val, max_len: int = 100) -> str:
    s = str(val)
    return s if len(s) <= max_len else s[:max_len - 3] + "..."


# ---------------------------------------------------------------------------
# Server info
# ---------------------------------------------------------------------------

def print_server_info(client: QdrantClient) -> None:
    header("QDRANT SERVER")
    try:
        info = client.get_collections()
        existing = [c.name for c in info.collections]
        kv("URL",                 QDRANT_URL)
        kv("Collections found",  len(existing))
        kv("Collection names",   ", ".join(existing) if existing else "(none)")
    except Exception as exc:
        log.error("  Failed to reach Qdrant: %s", exc)
        sys.exit(1)


# ---------------------------------------------------------------------------
# Payload distribution
# ---------------------------------------------------------------------------

def count_filter(client: QdrantClient, collection: str,
                 field: str, value: str) -> int:
    return client.count(
        collection_name=collection,
        count_filter=Filter(
            must=[FieldCondition(key=field, match=MatchValue(value=value))]
        ),
        exact=True,
    ).count


def print_distribution(client: QdrantClient, collection: str,
                        field: str, values: list[str]) -> None:
    log.info("  %s distribution:", field)
    total = client.count(collection_name=collection, exact=True).count
    for val in values:
        n = count_filter(client, collection, field, val)
        if n == 0:
            continue
        bar = "█" * int(n / total * 30)
        log.info("    %-30s %5d  %s", val, n, bar)


def print_bool_distribution(client: QdrantClient, collection: str,
                              field: str) -> None:
    true_count = client.count(
        collection_name=collection,
        count_filter=Filter(
            must=[FieldCondition(key=field, match=MatchValue(value=True))]
        ),
        exact=True,
    ).count
    total = client.count(collection_name=collection, exact=True).count
    false_count = total - true_count
    log.info("  %s distribution:", field)
    log.info("    %-30s %5d", "True  (time-based)", true_count)
    log.info("    %-30s %5d", "False (rep-based)",  false_count)


def print_numeric_range(client: QdrantClient, collection: str,
                         field: str, buckets: list[tuple]) -> None:
    """Print point counts across numeric range buckets."""
    log.info("  %s distribution:", field)
    for label, lo, hi in buckets:
        from qdrant_client.models import Range
        n = client.count(
            collection_name=collection,
            count_filter=Filter(
                must=[FieldCondition(key=field, range=Range(gte=lo, lte=hi))]
            ),
            exact=True,
        ).count
        log.info("    %-30s %5d", label, n)


# ---------------------------------------------------------------------------
# Sample points
# ---------------------------------------------------------------------------

def print_samples(client: QdrantClient, collection: str, n: int = 2) -> None:
    section(f"Sample points (first {n})")
    points, _ = client.scroll(
        collection_name=collection,
        limit=n,
        with_payload=True,
        with_vectors=False,
    )
    for i, pt in enumerate(points, 1):
        log.info("  [Point %d]  id: %s", i, pt.id)
        for key, val in pt.payload.items():
            log.info("    %-28s %s", key, truncate(val))
        if i < len(points):
            log.info("  %s", "·" * 40)


# ---------------------------------------------------------------------------
# Per-collection report
# ---------------------------------------------------------------------------

def inspect_collection(client: QdrantClient, name: str,
                        is_programs: bool) -> bool:
    header(f"COLLECTION: {name}")

    # ── existence check ───────────────────────────────────────────────────────
    if not client.collection_exists(name):
        log.error("  Collection '%s' does not exist!", name)
        return False

    info = client.get_collection(name)
    cfg  = info.config.params.vectors

    # ── overview ──────────────────────────────────────────────────────────────
    section("Overview")
    status_str = info.status.name
    kv("Status",              status_str)
    kv("Points (exact)",      client.count(collection_name=name, exact=True).count)
    kv("Indexed vectors",     info.indexed_vectors_count or 0)
    kv("Segments",            info.segments_count)
    kv("Vector dim",          cfg.size)
    kv("Distance metric",     cfg.distance.name)
    kv("On-disk vectors",     getattr(cfg, "on_disk", "N/A"))

    # ── optimizer ─────────────────────────────────────────────────────────────
    section("Optimizer state")
    opt = info.optimizer_status
    kv("Status",              opt.ok if hasattr(opt, "ok") else str(opt))

    # ── payload indexes ───────────────────────────────────────────────────────
    section("Payload indexes")
    schema = info.payload_schema
    if schema:
        for field, fschema in sorted(schema.items()):
            kv(field, fschema.data_type.name)
    else:
        log.info("  (none)")

    # ── payload distributions ─────────────────────────────────────────────────
    section("Payload distributions")

    print_distribution(client, name, P_GOAL,      KNOWN_GOALS)
    log.info("")
    print_distribution(client, name, P_LEVEL,     KNOWN_LEVELS)
    log.info("")
    print_distribution(client, name, P_EQUIPMENT, KNOWN_EQUIPMENT)

    if is_programs:
        log.info("")
        print_numeric_range(client, name, P_PROGRAM_LENGTH_WEEKS, [
            ("1–4 weeks",    1,  4),
            ("5–8 weeks",    5,  8),
            ("9–12 weeks",   9, 12),
            ("13–18 weeks", 13, 18),
        ])
        log.info("")
        print_numeric_range(client, name, P_TIME_PER_WORKOUT_MIN, [
            ("≤30 min",      0,  30),
            ("31–60 min",   31,  60),
            ("61–90 min",   61,  90),
            ("91–180 min",  91, 180),
        ])
    else:
        log.info("")
        print_bool_distribution(client, name, P_IS_TIME_BASED)

    # ── sample points ─────────────────────────────────────────────────────────
    print_samples(client, name, n=2)

    healthy = (info.status.name == "GREEN")
    if not healthy:
        log.warning("  Collection status is %s — may still be indexing.", status_str)
    return healthy


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    log.info("")
    log.info("Qdrant Collection Inspector")
    log.info("Target: %s", QDRANT_URL)
    log.info("")

    client = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY, timeout=30)

    print_server_info(client)

    healthy_programs  = inspect_collection(client, QDRANT_PROGRAMS_COLLECTION,  is_programs=True)
    healthy_exercises = inspect_collection(client, QDRANT_EXERCISES_COLLECTION, is_programs=False)

    # ── final summary ─────────────────────────────────────────────────────────
    sep()
    log.info("  SUMMARY")
    sep()
    kv(QDRANT_PROGRAMS_COLLECTION,  "✓ healthy" if healthy_programs  else "✗ unhealthy")
    kv(QDRANT_EXERCISES_COLLECTION, "✓ healthy" if healthy_exercises else "✗ unhealthy")
    sep()

    if not (healthy_programs and healthy_exercises):
        log.error("One or more collections are not healthy.")
        sys.exit(1)

    log.info("  All collections healthy.")
    log.info("")


if __name__ == "__main__":
    main()

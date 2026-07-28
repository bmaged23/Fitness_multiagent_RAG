"""
Embed both JSONL chunk files and upsert into two Qdrant collections.

Collections created:
    fitness_programs  — 2,594 program chunks
    fitness_exercises — 3,213 exercise chunks

The Retriever agent decides at query time which collection(s) to search
and what top-k to use (see config.settings QDRANT_*_TOP_K constants).

Usage:
    python scripts/embed_and_index.py               # upsert into existing collections
    python scripts/embed_and_index.py --reseting    # drop + recreate collections first
"""

import sys
import json
import logging
import argparse
from pathlib import Path

import numpy as np
from tqdm import tqdm
from sentence_transformers import SentenceTransformer
from qdrant_client import QdrantClient
from qdrant_client.models import (
    VectorParams, PointStruct,
    PayloadSchemaType, OptimizersConfigDiff,
)

sys.path.insert(0, str(Path(__file__).parent.parent))
from config.settings import (
    QDRANT_URL, QDRANT_API_KEY,
    QDRANT_PROGRAMS_COLLECTION, QDRANT_EXERCISES_COLLECTION,
    QDRANT_VECTOR_SIZE, QDRANT_DISTANCE,
    EMBEDDING_MODEL, EMBEDDING_BATCH_SIZE, QDRANT_UPSERT_BATCH_SIZE,
    PROGRAM_CHUNKS_JSONL, EXERCISE_CHUNKS_JSONL,
    QDRANT_INDEXING_THRESHOLD,
    P_GOAL, P_LEVEL, P_EQUIPMENT,
    P_PROGRAM_LENGTH_WEEKS, P_TIME_PER_WORKOUT_MIN,
    P_EXERCISE_NAME, P_IS_TIME_BASED,
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

def load_jsonl(path: Path) -> list[dict]:
    records = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    log.info("  Loaded %d records from %s", len(records), path.name)
    return records


def embed_texts(model: SentenceTransformer, texts: list[str]) -> np.ndarray:
    """Embed in batches with a progress bar. Returns (N, dim) float32 array."""
    all_embeddings = []
    for i in tqdm(range(0, len(texts), EMBEDDING_BATCH_SIZE),
                  desc="  Embedding", unit="batch"):
        batch = texts[i : i + EMBEDDING_BATCH_SIZE]
        vecs = model.encode(
            batch,
            normalize_embeddings=True,   # required for cosine similarity
            show_progress_bar=False,
        )
        all_embeddings.append(vecs)
    return np.vstack(all_embeddings)


def build_points(records: list[dict], embeddings: np.ndarray) -> list[PointStruct]:
    """
    Pair each record with its embedding.
    chunk_id becomes the Qdrant point ID.
    source_table is dropped — the collection name is the discriminator.
    """
    points = []
    for rec, vec in zip(records, embeddings):
        payload = {k: v for k, v in rec.items()
                   if k not in ("chunk_id", "source_table")}
        points.append(PointStruct(
            id=rec["chunk_id"],
            vector=vec.tolist(),
            payload=payload,
        ))
    return points


def upsert_points(client: QdrantClient, collection: str,
                  points: list[PointStruct]) -> None:
    """Upsert in batches and show progress."""
    total = len(points)
    for i in tqdm(range(0, total, QDRANT_UPSERT_BATCH_SIZE),
                  desc=f"  Upserting → {collection}", unit="batch"):
        batch = points[i : i + QDRANT_UPSERT_BATCH_SIZE]
        client.upsert(collection_name=collection, points=batch)
    log.info("  Upserted %d points into '%s'", total, collection)


# ---------------------------------------------------------------------------
# Collection setup
# ---------------------------------------------------------------------------

def recreate_collection(client: QdrantClient, name: str) -> None:
    """Drop if exists, then create fresh with flat (exact) search enforced."""
    if client.collection_exists(name):
        log.info("  Dropping existing collection '%s' …", name)
        client.delete_collection(name)
    client.create_collection(
        collection_name=name,
        vectors_config=VectorParams(
            size=QDRANT_VECTOR_SIZE,
            distance=QDRANT_DISTANCE,
        ),
        optimizers_config=OptimizersConfigDiff(
            indexing_threshold=QDRANT_INDEXING_THRESHOLD,
        ),
    )
    log.info("  Created collection '%s'  (dim=%d, metric=%s, flat=True)",
             name, QDRANT_VECTOR_SIZE, QDRANT_DISTANCE.name)


def create_programs_indexes(client: QdrantClient) -> None:
    """
    Payload indexes for fitness_programs.
    Only fields the Retriever will filter on get indexed.
    """
    indexes = [
        (P_GOAL,                  PayloadSchemaType.KEYWORD),
        (P_LEVEL,                 PayloadSchemaType.KEYWORD),
        (P_EQUIPMENT,             PayloadSchemaType.KEYWORD),
        (P_PROGRAM_LENGTH_WEEKS,  PayloadSchemaType.INTEGER),
        (P_TIME_PER_WORKOUT_MIN,  PayloadSchemaType.INTEGER),
    ]
    for field, schema in indexes:
        client.create_payload_index(
            collection_name=QDRANT_PROGRAMS_COLLECTION,
            field_name=field,
            field_schema=schema,
        )
    log.info("  Created %d payload indexes on '%s'",
             len(indexes), QDRANT_PROGRAMS_COLLECTION)


def create_exercises_indexes(client: QdrantClient) -> None:
    """
    Payload indexes for fitness_exercises.
    """
    indexes = [
        (P_GOAL,          PayloadSchemaType.KEYWORD),
        (P_LEVEL,         PayloadSchemaType.KEYWORD),
        (P_EQUIPMENT,     PayloadSchemaType.KEYWORD),
        (P_EXERCISE_NAME, PayloadSchemaType.KEYWORD),
        (P_IS_TIME_BASED, PayloadSchemaType.BOOL),
    ]
    for field, schema in indexes:
        client.create_payload_index(
            collection_name=QDRANT_EXERCISES_COLLECTION,
            field_name=field,
            field_schema=schema,
        )
    log.info("  Created %d payload indexes on '%s'",
             len(indexes), QDRANT_EXERCISES_COLLECTION)


# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------

def verify(client: QdrantClient, collection: str, expected: int) -> None:
    info = client.get_collection(collection)
    actual = info.points_count
    status = "OK" if actual == expected else "MISMATCH"
    log.info("  [%s] '%s': %d / %d points", status, collection, actual, expected)
    if status == "MISMATCH":
        raise RuntimeError(
            f"Point count mismatch in '{collection}': "
            f"expected {expected}, got {actual}"
        )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--reseting",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Drop and recreate both collections before indexing (default: True). Use --no-reseting to skip.",
    )
    args = parser.parse_args()

    # ── connect & verify Qdrant is reachable ─────────────────────────────────
    log.info("Connecting to Qdrant at %s …", QDRANT_URL)
    client = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY, timeout=180)
    client.get_collections()  # fail fast if Qdrant is down
    log.info("  Qdrant reachable.")

    # ── drop + recreate collections if --reseting was passed ─────────────────
    if args.reseting:
        log.info("--reseting: dropping and recreating both collections …")
        recreate_collection(client, QDRANT_PROGRAMS_COLLECTION)
        create_programs_indexes(client)
        recreate_collection(client, QDRANT_EXERCISES_COLLECTION)
        create_exercises_indexes(client)
    else:
        log.info("--reseting not set: upserting into existing collections.")

    # ── load embedding model ─────────────────────────────────────────────────
    log.info("Loading embedding model '%s' …", EMBEDDING_MODEL)
    model = SentenceTransformer(EMBEDDING_MODEL)
    log.info("  Model loaded  (output dim: %d)", model.get_embedding_dimension())

    # ════════════════════════════════════════════════════════════════════════
    # fitness_programs
    # ════════════════════════════════════════════════════════════════════════
    log.info("=" * 60)
    log.info("Step 1/2 — fitness_programs")
    log.info("=" * 60)

    prog_records = load_jsonl(PROGRAM_CHUNKS_JSONL)
    prog_texts   = [r["text"] for r in prog_records]

    log.info("Embedding %d program chunks …", len(prog_texts))
    prog_vecs = embed_texts(model, prog_texts)

    prog_points = build_points(prog_records, prog_vecs)
    upsert_points(client, QDRANT_PROGRAMS_COLLECTION, prog_points)
    verify(client, QDRANT_PROGRAMS_COLLECTION, len(prog_records))

    # ════════════════════════════════════════════════════════════════════════
    # fitness_exercises
    # ════════════════════════════════════════════════════════════════════════
    log.info("=" * 60)
    log.info("Step 2/2 — fitness_exercises")
    log.info("=" * 60)

    exer_records = load_jsonl(EXERCISE_CHUNKS_JSONL)
    exer_texts   = [r["text"] for r in exer_records]

    log.info("Embedding %d exercise chunks …", len(exer_texts))
    exer_vecs = embed_texts(model, exer_texts)

    exer_points = build_points(exer_records, exer_vecs)
    upsert_points(client, QDRANT_EXERCISES_COLLECTION, exer_points)
    verify(client, QDRANT_EXERCISES_COLLECTION, len(exer_records))

    # ── summary ──────────────────────────────────────────────────────────────
    log.info("=" * 60)
    log.info("Done.")
    log.info("  %-25s  %d points", QDRANT_PROGRAMS_COLLECTION,  len(prog_records))
    log.info("  %-25s  %d points", QDRANT_EXERCISES_COLLECTION, len(exer_records))
    log.info("  Total: %d vectors  dim=%d  metric=%s",
             len(prog_records) + len(exer_records),
             QDRANT_VECTOR_SIZE, QDRANT_DISTANCE.name)
    log.info("Next step: python scripts/init_db.py")
    log.info("=" * 60)


if __name__ == "__main__":
    main()

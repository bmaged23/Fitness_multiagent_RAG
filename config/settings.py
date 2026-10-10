from pathlib import Path
import os
from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).parent.parent

# ---------------------------------------------------------------------------
# Data paths
# ---------------------------------------------------------------------------
DATA_DIR           = PROJECT_ROOT / "data"
DATA_RAW_DIR       = DATA_DIR / "raw"
DATA_PROCESSED_DIR = DATA_DIR / "processed"
DATA_SCHEMA_DIR    = DATA_DIR / "schema"

# ---------------------------------------------------------------------------
# Kaggle dataset
# ---------------------------------------------------------------------------
KAGGLE_DATASET_SLUG = "adnanelouardi/600k-fitness-exercise-and-workout-program-dataset"
EXERCISES_CSV       = DATA_RAW_DIR / "programs_detailed_boostcamp_kaggle.csv"
PROGRAMS_CSV        = DATA_RAW_DIR / "program_summary.csv"

# Approximate lower bounds used by download_dataset.py for sanity check
EXERCISES_MIN_ROWS = 600_000
PROGRAMS_MIN_ROWS  = 2_000

# ---------------------------------------------------------------------------
# SQLite
# ---------------------------------------------------------------------------
SQLITE_DB_PATH = PROJECT_ROOT / "data" / "fitness_coach.db"

# ---------------------------------------------------------------------------
# Qdrant — local instance
# ---------------------------------------------------------------------------
QDRANT_URL     = os.getenv("QDRANT_URL", "http://localhost:6333")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY", None)

# Two separate collections — collection name IS the discriminator (no source_table field needed)
QDRANT_PROGRAMS_COLLECTION  = "fitness_programs"
QDRANT_EXERCISES_COLLECTION = "fitness_exercises"

# Vector config — must match the embedding model
from qdrant_client.models import Distance

QDRANT_VECTOR_SIZE = int(os.getenv("EMBEDDING_DIM", "1024"))  # bge-large-en-v1.5
QDRANT_DISTANCE    = Distance.COSINE

# Flat (exact) search — search the entire collection every time.
# indexing_threshold set astronomically high so Qdrant never builds an HNSW graph.
# Both collections are <4k vectors; brute-force is faster and gives perfect recall.
QDRANT_INDEXING_THRESHOLD = 999_999_999   # effectively disables HNSW
QDRANT_EXACT_SEARCH       = True          # passed as SearchParams(exact=True) at query time

# Set to True  → drop + recreate collections, then embed + upsert (full rebuild)
# Set to False → skip drop/create, only embed + upsert into existing collections
RECREATE_COLLECTIONS = True

# Hard ceiling on chunks per single retrieval call — the Retriever agent
# decides the actual top-k dynamically based on query complexity.
# This only exists to prevent runaway requests.
QDRANT_MAX_TOP_K = 3

# ---------------------------------------------------------------------------
# Qdrant payload field names
# Centralised here — embed_and_index.py, vectorstore/, and the Retriever
# all import from here, no string literals scattered across files.
# ---------------------------------------------------------------------------

# --- JSONL-only (written by chunk_data.py, stripped by embed_and_index.py before upsert) ---
# Collection name is the discriminator in Qdrant — source_table is not stored as a payload field.
P_SOURCE_TABLE   = "source_table"
SOURCE_PROGRAMS  = "programs"
SOURCE_EXERCISES = "exercises"

# --- shared (both collections) ---
P_CHUNK_ID  = "chunk_id"   # str       — UUID generated at chunk time
P_TEXT      = "text"       # str       — the string that was embedded
P_TITLE     = "title"      # str       — program name (FK between collections)
P_GOAL      = "goal"       # list[str] — parsed from stringified list
P_LEVEL     = "level"      # list[str] — parsed from stringified list
P_EQUIPMENT = "equipment"  # str (programs) | list[str] (exercises)

# --- fitness_programs only ---
P_DESCRIPTION          = "description"          # str — full program narrative
P_PROGRAM_LENGTH_WEEKS = "program_length_weeks"  # int — total program duration
P_TIME_PER_WORKOUT_MIN = "time_per_workout_min"  # int — minutes per session
P_TOTAL_EXERCISES      = "total_exercises"       # int — total exercise rows in program
P_CREATED              = "created"               # str — original creation timestamp
P_LAST_EDIT            = "last_edit"             # str — last edit timestamp

# --- fitness_exercises only ---
P_EXERCISE_NAME     = "exercise_name"    # str
P_SETS_MEDIAN       = "sets_median"      # int
P_SETS_MIN          = "sets_min"         # int
P_SETS_MAX          = "sets_max"         # int
P_REPS_MEDIAN       = "reps_median"      # int  — absolute value
P_REPS_MIN          = "reps_min"         # int  — absolute value
P_REPS_MAX          = "reps_max"         # int  — absolute value
P_IS_TIME_BASED     = "is_time_based"    # bool — True if majority are time-based
P_INTENSITY_MEDIAN  = "intensity_median" # int  — 0–10 scale
P_PROGRAMS          = "programs"         # list[str] — program titles this exercise appears in
P_OCCURRENCE_COUNT  = "occurrence_count" # int  — total rows in the detail CSV

# ---------------------------------------------------------------------------
# Embedding
# ---------------------------------------------------------------------------
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "BAAI/bge-large-en-v1.5")
EMBEDDING_DIM   = int(os.getenv("EMBEDDING_DIM", "1024"))
EMBEDDING_BATCH_SIZE  = int(os.getenv("EMBEDDING_BATCH_SIZE", "64"))
QDRANT_UPSERT_BATCH_SIZE = int(os.getenv("QDRANT_UPSERT_BATCH_SIZE", "64"))

# ---------------------------------------------------------------------------
# LLM — Groq
# ---------------------------------------------------------------------------
GROQ_API_KEY:     str   = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL:       str   = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
GROQ_TEMPERATURE: float = float(os.getenv("GROQ_TEMPERATURE", "0.3"))
GROQ_TIMEOUT:     int   = int(os.getenv("GROQ_TIMEOUT", "60"))
GROQ_MAX_TOKENS:  int   = int(os.getenv("GROQ_MAX_TOKENS", "4096"))
GROQ_MAX_RETRIES: int   = int(os.getenv("GROQ_MAX_RETRIES", "5"))

# ---------------------------------------------------------------------------
# Tavily web search
# ---------------------------------------------------------------------------
TAVILY_API_KEY: str = os.getenv("TAVILY_API_KEY", "")

# ---------------------------------------------------------------------------
# Chunking
# ---------------------------------------------------------------------------
EXERCISE_CHUNK_BATCH_SIZE = 1_000  # rows flushed to JSONL per write
PROGRAM_CHUNK_FIELDS      = ["title", "description", "goal", "level",
                              "equipment", "program_length_weeks",
                              "time_per_workout_min"]

# Cleaning caps applied at chunk time
REPS_TIME_BASED_CAP_SECONDS = 3_600   # values above this are treated as data errors
SETS_CAP                    = 20      # sets above this are treated as data errors

# Output JSONL paths — written by chunk_data.py, read by embed_and_index.py
PROGRAM_CHUNKS_JSONL  = DATA_PROCESSED_DIR / "program_chunks.jsonl"
EXERCISE_CHUNKS_JSONL = DATA_PROCESSED_DIR / "exercise_chunks.jsonl"

# ---------------------------------------------------------------------------
# Retriever
# ---------------------------------------------------------------------------
# Hard ceiling on total retrieval steps — model cannot loop past this.
# top-k per step is chosen by the model dynamically (capped by QDRANT_MAX_TOP_K).
RETRIEVER_STEP_CEILING = 6

# ---------------------------------------------------------------------------
# Memory truncation
# ---------------------------------------------------------------------------
MEMORY_TRUNCATION_SESSION_COUNT  = 5        # trigger salience pass every N sessions
MEMORY_TRUNCATION_CHAR_THRESHOLD = 4_000    # also trigger if summary exceeds this length


RETRIEVER_PROGRAM_MAX_RETRIES = 2
RETRIEVER_EXERCISE_MAX_RETRIES = 2

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "groq")

OLLAMA_API_KEY = os.getenv("OLLAMA_API_KEY", "")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "gpt-oss:120b")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "https://ollama.com")

RECURSION_LIMIT = 20
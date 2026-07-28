from typing import TypedDict


class SearchResult(TypedDict):
    score: float
    collection: str          # "fitness_programs" or "fitness_exercises"
    chunk_id: str
    text: str
    title: str
    goal: list[str]
    level: list[str]
    equipment: str | list[str]


# Categorical values exactly as stored in Qdrant payloads.
# Used by query_rewrite.py to map free-form user input to valid filter values.
KNOWN_GOALS = [
    "Bodybuilding",
    "Muscle & Sculpting",
    "Powerbuilding",
    "Athletics",
    "Powerlifting",
    "Bodyweight Fitness",
    "Olympic Weightlifting",
    "At-Home & Calisthenics",
]

KNOWN_LEVELS = ["Beginner", "Novice", "Intermediate", "Advanced"]

KNOWN_EQUIPMENT = ["Full Gym", "Garage Gym", "At Home", "Dumbbell Only"]

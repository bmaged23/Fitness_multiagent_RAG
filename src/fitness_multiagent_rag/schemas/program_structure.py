from __future__ import annotations

from pydantic import BaseModel, Field


class ProgramStructure(BaseModel):
    """Compact training skeleton — proposed in Stage 1, approved by the user before any exercises are generated."""

    goal: str                                                  # exact value from allowed goal list
    difficulty: str                                            # Beginner / Novice / Intermediate / Advanced
    equipment_available: list[str]                             # e.g. ["Dumbbell Only"]
    split_type: str                                            # "Full Body" | "Upper/Lower" | "Push/Pull/Legs" | "Body Part"
    days_per_week: int = Field(ge=2, le=6)
    rep_style: str                                             # "Strength (3–6 reps)" | "Hypertrophy (8–12 reps)" | "Endurance (15+ reps)"
    duration_weeks: int = Field(ge=6, le=52)
    day_schedule: list[str] = Field(min_length=7, max_length=7)  # one label per weekday: "Full Body A", "REST", …
    rationale: str                                             # 1 sentence: why this suits the trainee
    # Set programmatically in propose_structure() — LLM does not fill these.
    deload_weeks: list[int] = Field(default_factory=list)      # e.g. [4, 8] — every 4th week + final week
    weight_increment_kg_per_week: float = 2.5                  # kg added each non-deload week

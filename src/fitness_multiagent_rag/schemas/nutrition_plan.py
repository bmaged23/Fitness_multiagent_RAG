"""Validated storage contract for meal plans, rather than free-form chat advice."""
from datetime import date
from pydantic import BaseModel, ConfigDict, Field, model_validator


class NutritionModel(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)


class DailyTargets(NutritionModel):
    calories_kcal: float = Field(gt=0)
    protein_g: float = Field(ge=0)
    carbohydrate_g: float = Field(ge=0)
    fat_g: float = Field(ge=0)

    @model_validator(mode='after')
    def consistent_energy(self):
        macro_energy = 4 * (self.protein_g + self.carbohydrate_g) + 9 * self.fat_g
        if abs(macro_energy - self.calories_kcal) > max(100, self.calories_kcal * .1):
            raise ValueError('Calories and macro targets differ by more than the allowed rounding tolerance.')
        return self


class MealFood(NutritionModel):
    name: str = Field(min_length=1)
    portion: str = Field(min_length=1)
    alternatives: list[str] = Field(default_factory=list)


class Meal(NutritionModel):
    name: str = Field(min_length=1)
    foods: list[MealFood] = Field(min_length=1)
    notes: str = ''


class NutritionPlanSchema(NutritionModel):
    goal: str = Field(min_length=1)
    daily_targets: DailyTargets
    meals: list[Meal] = Field(min_length=1)
    dietary_preferences: list[str]
    allergies: list[str]
    restrictions: list[str]
    start_date: date
    review_date: date
    notes: str = ''

    @model_validator(mode='after')
    def valid_dates(self):
        if self.review_date < self.start_date:
            raise ValueError('Review date must be on or after start date.')
        return self

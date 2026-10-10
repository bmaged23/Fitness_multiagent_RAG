from io import BytesIO
from pypdf import PdfReader
from app.components.plan_pdf import workout_pdf, nutrition_pdf


def read_pdf(data):
    assert data.startswith(b'%PDF-')
    reader = PdfReader(BytesIO(data))
    return reader, '\n'.join(page.extract_text() for page in reader.pages)


def test_workout_exports_all_weeks_and_wraps_long_notes():
    exercise = {'name': 'Squat & Press', 'sets': 3, 'reps': 10, 'rest_seconds': 90,
                'equipment': 'Dumbbell', 'notes': 'Maintain control. ' * 40}
    plan = {'goal': 'Bodybuilding', 'difficulty': 'Beginner', 'duration_weeks': 8,
        'equipment_available': ['Dumbbell'], 'progression': {'deload_weeks': [4, 8],
        'deload_volume_factor': .6}, 'weeks': [{'week': week, 'days': [
            {'day': 1, 'focus': 'Full Body', 'exercises': [exercise]},
            {'day': 2, 'rest_day': True}]} for week in range(1, 9)]}
    reader, text = read_pdf(workout_pdf(plan, 'Test <User>'))
    assert len(reader.pages) >= 9
    assert all(f'Week {week}' in text for week in range(1, 9))
    assert 'Squat & Press' in text and 'Test <User>' in text
    assert 'Rest day' in text and '90 sec' in text
    assert '60% of normal sets' in text
    assert 'Maintain control.' in text
    assert 'Page 1' in text


def test_nutrition_pdf_contains_targets_portions_and_restrictions():
    plan = {'goal': 'Bodybuilding', 'daily_targets': {'calories_kcal': 2000,
        'protein_g': 100, 'carbohydrate_g': 250, 'fat_g': 67},
        'start_date': '2026-10-10', 'review_date': '2026-11-10',
        'meals': [{'name': 'Breakfast', 'foods': [{'name': 'Oats', 'portion': '50 g',
                   'alternatives': ['Rice flakes']}], 'notes': 'Mix with water.'}],
        'allergies': ['Peanuts'], 'dietary_preferences': ['Vegan'],
        'restrictions': ['No dairy'], 'notes': 'Follow the saved portions.'}
    _, text = read_pdf(nutrition_pdf(plan, 'Test User'))
    for expected in ['2000 kcal', '100 g', 'Breakfast', 'Oats', '50 g', 'Rice flakes',
                     'Peanuts', 'Vegan', 'No dairy', 'Mix with water.', '2026-11-10']:
        assert expected in text

"""Read-only, structured displays of saved workout and nutrition plans."""
import json
import re
from datetime import date, datetime, timezone

import streamlit as st
from fitness_multiagent_rag.db import crud, nutrition


def format_chat_reply(text: str) -> str:
    """Make deterministic plain-text plan summaries readable as Markdown."""
    if text.lstrip().startswith('Week ') and 'Day ' in text:
        text = re.sub(r'\s+(?=Day\s+\d+\s*[:—–-])', '\n', text)
        text = re.sub(r'\s*•\s*', '\n• ', text)
        text = re.sub(r'\s+(?=This rotation applies)', '\n\n', text)
    lines = []
    for line in text.splitlines():
        clean = line.strip()
        if re.match(r'^Week\s+\d+\s*[—–-]', clean) or clean.startswith('Your nutrition plan ('):
            lines.extend(['', '### ' + clean.rstrip(':'), ''])
        elif re.match(r'^Day\s+\d+\s*[—–:-]', clean):
            lines.extend(['', '#### ' + clean.rstrip(':'), ''])
        elif clean.startswith('• '):
            lines.append('- ' + clean[2:])
        elif clean.startswith('Alternatives:'):
            lines.append('  - ' + clean)
        elif clean and clean.endswith(':') and text.startswith('Your nutrition plan ('):
            lines.extend(['', '#### ' + clean[:-1], ''])
        else:
            lines.append(line)
    return '\n'.join(lines).strip()


def default_week(plan: dict, saved_at: str | None, today: date | None = None) -> int:
    """Use elapsed weeks since saving as an estimate, bounded by stored weeks."""
    weeks = [w['week'] for w in plan.get('weeks', [])]
    if not weeks:
        return 1
    try:
        start = datetime.fromisoformat(saved_at.replace('Z', '+00:00')).date()
        elapsed = max(0, ((today or datetime.now(timezone.utc).date()) - start).days // 7) + 1
    except (AttributeError, ValueError):
        elapsed = 1
    return min(weeks, key=lambda number: abs(number - elapsed))


def render_workout(plan: dict, *, key: str, saved_at: str | None = None):
    st.caption(f"{plan.get('goal', '')} · {plan.get('difficulty', '')} · {plan.get('duration_weeks', '?')} weeks")
    weeks = plan.get('weeks', [])
    if not weeks:
        st.info('This proposal has no exercises yet. Ask Alex for program details to generate Week 1.')
        for index, label in enumerate(plan.get('day_schedule', []), 1):
            st.write(f'Day {index}: {label}')
        return
    numbers = [week['week'] for week in weeks]
    selected = st.selectbox('Workout week', numbers, index=numbers.index(default_week(plan, saved_at)),
                            format_func=lambda n: f'Week {n}', key=key + '_week')
    if saved_at:
        st.caption('The initial selection estimates your current week from the date the program was saved. Choose another week if your start date differs.')
    week = next(w for w in weeks if w['week'] == selected)
    for day in week.get('days', []):
        if day.get('rest_day'):
            st.markdown(f"**Day {day['day']} · Rest**")
            continue
        st.subheader(f"Day {day['day']} · {day.get('focus', 'Workout')}")
        rows = []
        for exercise in day.get('exercises', []):
            reps = exercise.get('reps', 0)
            rows.append({'Exercise': exercise['name'], 'Sets': exercise['sets'],
                'Reps / time': f'{abs(reps)} sec' if reps < 0 else str(reps),
                'Rest': f"{exercise.get('rest_seconds', 0)} sec", 'Equipment': exercise.get('equipment', ''),
                'Notes': exercise.get('notes', '')})
        if rows:
            st.dataframe(rows, hide_index=True, width='stretch')
        else:
            st.caption('No exercises recorded.')
    progression = plan.get('progression', {})
    if progression:
        st.markdown('**Progression**')
        st.write(f"Recorded weekly weight increment: {progression.get('weight_increment_kg_per_week', 0)} kg. "
                 f"Deload weeks: {', '.join(map(str, progression.get('deload_weeks', []))) or 'None recorded'}.")


def render_nutrition(plan: dict):
    st.caption(plan['goal'])
    targets = plan['daily_targets']
    columns = st.columns(4)
    for column, (label, field, unit) in zip(columns, [('Calories', 'calories_kcal', 'kcal'),
        ('Protein', 'protein_g', 'g'), ('Carbs', 'carbohydrate_g', 'g'), ('Fat', 'fat_g', 'g')]):
        column.metric(label, f"{targets[field]:g} {unit}")
    st.caption(f"Daily meal plan · Start {plan['start_date']} · Review {plan['review_date']}")
    st.caption('These daily targets and meals apply throughout this period; separate weekly menus are not stored.')
    for meal in plan['meals']:
        st.subheader(meal['name'])
        rows = [{'Food': food['name'], 'Portion': food['portion'],
                 'Alternatives': ', '.join(food.get('alternatives', []))} for food in meal['foods']]
        st.dataframe(rows, hide_index=True, width='stretch')
        if meal.get('notes'):
            st.write(meal['notes'])
    for field, label in [('dietary_preferences', 'Preferences'), ('allergies', 'Allergies'), ('restrictions', 'Restrictions')]:
        st.write(f"**{label}:** {', '.join(plan.get(field, [])) or 'None recorded'}")
    if plan.get('notes'):
        st.write(plan['notes'])


def render_my_plans(trainee_id: int, draft: dict):
    if st.button('Refresh plans', key='refresh_plans'):
        st.session_state.pop('workout_record', None)
        st.session_state.pop('nutrition_record', None)
    # Fetch again here rather than relying on the sidebar snapshot.
    from fitness_multiagent_rag.agents.designer.drafts import read_draft
    draft = read_draft(trainee_id)
    workout_tab, nutrition_tab = st.tabs(['Workout program', 'Nutrition plan'],
        key='plan_tabs', on_change='rerun')
    with workout_tab:
        records = crud.get_trainee_plans(trainee_id)
        if draft:
            with st.expander('Pending workout draft', expanded=not records):
                raw = draft.get('week1_plan_json') or draft.get('structure_json')
                if raw:
                    render_workout(json.loads(raw) if isinstance(raw, str) else raw, key='workout_draft')
                st.caption('This draft has not been saved as an active workout program.')
        if records:
            by_id = {p.id: p for p in records}
            selected = st.selectbox('Saved workout programs', list(by_id),
                index=next((i for i, p in enumerate(records) if p.status == 'active'), 0),
                format_func=lambda ident: f"{by_id[ident].status.title()} · {by_id[ident].created_at} · {by_id[ident].duration_weeks} weeks · #{ident}",
                key='workout_record')
            record = by_id[selected]
            render_workout(record.plan_json, key=f'workout_{selected}', saved_at=record.created_at)
            st.subheader('Revision history')
            history = crud.get_plan_revisions(record.id)
            if not history:
                st.caption('No revisions recorded for this program.')
            for revision in history:
                with st.expander(f'Revision {revision.revision_number} · {revision.created_at}'):
                    st.write(revision.change_description)
                    after, before = st.tabs(['Updated program', 'Previous program'])
                    with after:
                        render_workout(revision.new_plan_json, key=f'workout_rev_{revision.id}_new')
                    with before:
                        render_workout(revision.previous_plan_json, key=f'workout_rev_{revision.id}_old')
        elif not draft:
            st.info('No workout program yet. Ask Alex to create one in Chat.')
    with nutrition_tab:
        records = nutrition.list_plans(trainee_id)
        if not records:
            st.info('No nutrition plan yet. Ask Alex to create one in Chat.')
        else:
            by_id = {p['id']: p for p in records}
            selected = st.selectbox('Saved nutrition plans', list(by_id),
                index=next((i for i, p in enumerate(records) if p['status'] == 'active'), 0),
                format_func=lambda ident: f"{by_id[ident]['status'].title()} · {by_id[ident]['created_at']} · #{ident}",
                key='nutrition_record')
            record = by_id[selected]
            if record['status'] == 'draft':
                st.info('Pending approval. Your active nutrition plan remains unchanged.')
            render_nutrition(record['plan_json'])
            st.subheader('Revision history')
            for revision in nutrition.revisions(trainee_id, selected):
                with st.expander(f"Revision {revision['revision_number']} · {revision['created_at']}"):
                    st.write(revision['change_description'])
                    render_nutrition(revision['new_plan_json'])
                    if revision['previous_plan_json']:
                        with st.expander('Previous nutrition plan'):
                            render_nutrition(revision['previous_plan_json'])

"""Readable PDF exports of the saved plans, generated without an LLM."""
from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak


def _document(title, name):
    regular = Path('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf')
    bold = regular.with_name('DejaVuSans-Bold.ttf')
    font, strong = 'Helvetica', 'Helvetica-Bold'
    if regular.exists() and bold.exists():
        if 'PlanSans' not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont('PlanSans', str(regular)))
            pdfmetrics.registerFont(TTFont('PlanSansBold', str(bold)))
        font, strong = 'PlanSans', 'PlanSansBold'
    styles = getSampleStyleSheet()
    for style in styles.byName.values():
        style.fontName = font
    for key in ('Title', 'Heading1', 'Heading2', 'Heading3'):
        styles[key].fontName = strong
        styles[key].textColor = colors.HexColor('#16394c')
    styles['BodyText'].fontSize = 9
    styles['BodyText'].leading = 14
    styles.add(ParagraphStyle('Cell', fontName=font, fontSize=8, leading=12))
    styles.add(ParagraphStyle('HeaderCell', fontName=strong, fontSize=8, leading=12,
                              textColor=colors.white))
    output = BytesIO()
    doc = SimpleDocTemplate(output, pagesize=(595.28, 841.89), rightMargin=38, leftMargin=38,
                            topMargin=42, bottomMargin=42, title=title, author='Alex Fitness Coach')
    story = [Paragraph(escape(title), styles['Title']),
             Paragraph(escape(str(name)), styles['Heading2']), Spacer(1, 12)]
    return output, doc, styles, story


def _p(value, styles, style='BodyText'):
    return Paragraph(escape(str(value)).replace('\n', '<br/>'), styles[style])


def _table(headers, rows, widths, styles):
    data = [[_p(h, styles, 'HeaderCell') for h in headers]]
    data.extend([[_p(cell, styles, 'Cell') for cell in row] for row in rows])
    table = Table(data, colWidths=widths, repeatRows=1, hAlign='LEFT')
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#16394c')),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.HexColor('#f0f5f8'), colors.white]),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
        ('TOPPADDING', (0, 0), (-1, -1), 7),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 7),
        ('LINEBELOW', (0, 0), (-1, 0), 1, colors.HexColor('#16394c')),
    ]))
    return table


def _finish(output, doc, story):
    def footer(canvas, document):
        canvas.saveState()
        canvas.setFont('Helvetica', 8)
        canvas.setFillColor(colors.HexColor('#607080'))
        canvas.drawString(38, 23, 'Alex | Saved plan')
        canvas.drawRightString(document.pagesize[0] - 38, 23, f'Page {document.page}')
        canvas.restoreState()
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return output.getvalue()


def workout_pdf(plan: dict, name: str) -> bytes:
    output, doc, styles, story = _document('Workout program', name)
    story.append(_table(['Goal', 'Level', 'Duration'], [[plan.get('goal', ''),
        plan.get('difficulty', ''), f"{plan.get('duration_weeks', '?')} weeks"]], [190, 160, 169], styles))
    if plan.get('equipment_available'):
        story.append(_p('Available equipment: ' + ', '.join(plan['equipment_available']), styles))
    progression = plan.get('progression', {})
    if progression:
        story.append(_p('Progression', styles, 'Heading2'))
        story.append(_p(f"Recorded weekly weight increment: {progression.get('weight_increment_kg_per_week', 0)} kg. "
            f"Deload weeks: {', '.join(map(str, progression.get('deload_weeks', []))) or 'None recorded'}.", styles))
        if 'deload_volume_factor' in progression:
            story.append(_p(f"Deload volume: {progression['deload_volume_factor'] * 100:g}% of normal sets.", styles))
        if progression.get('notes'):
            story.append(_p(progression['notes'], styles))
    if plan.get('notes'):
        story.append(_p(plan['notes'], styles))
    for week in plan.get('weeks', []):
        story.append(PageBreak())
        story.append(_p(f"Week {week['week']}", styles, 'Heading1'))
        if week.get('notes'):
            story.append(_p(week['notes'], styles))
        for day in week.get('days', []):
            label = 'Rest' if day.get('rest_day') else day.get('focus', 'Workout')
            story.append(_p(f"Day {day['day']} — {label}", styles, 'Heading2'))
            if day.get('rest_day'):
                story.append(_p('Rest day', styles))
                continue
            rows = []
            for ex in day.get('exercises', []):
                reps = ex.get('reps', 0)
                detail = '\n'.join(str(v) for v in (ex.get('equipment'), ex.get('muscle_group'), ex.get('notes')) if v)
                rows.append([ex['name'], ex['sets'], f'{abs(reps)} sec' if reps < 0 else reps,
                             f"{ex.get('rest_seconds', 0)} sec", detail])
            if rows:
                story.append(_table(['Exercise', 'Sets', 'Reps / time', 'Rest', 'Equipment / notes'],
                                    rows, [164, 38, 67, 55, 195], styles))
            if day.get('notes'):
                story.append(_p(day['notes'], styles))
            story.append(Spacer(1, 8))
    return _finish(output, doc, story)


def nutrition_pdf(plan: dict, name: str) -> bytes:
    output, doc, styles, story = _document('Nutrition plan', name)
    story.append(_p(f"Goal: {plan.get('goal', '')}", styles))
    story.append(_p(f"Start: {plan.get('start_date', '')} | Review: {plan.get('review_date', '')}", styles))
    story.append(_p('Daily targets', styles, 'Heading2'))
    targets = plan.get('daily_targets', {})
    story.append(_table(['Calories', 'Protein', 'Carbohydrates', 'Fat'], [[
        f"{targets.get('calories_kcal', 0):g} kcal", f"{targets.get('protein_g', 0):g} g",
        f"{targets.get('carbohydrate_g', 0):g} g", f"{targets.get('fat_g', 0):g} g"]],
        [130, 130, 130, 129], styles))
    story.append(_p('Daily meal plan', styles, 'Heading1'))
    for meal in plan.get('meals', []):
        story.append(_p(meal['name'], styles, 'Heading2'))
        rows = [[food['name'], food['portion'], ', '.join(food.get('alternatives', [])) or '—']
                for food in meal.get('foods', [])]
        if rows:
            story.append(_table(['Food', 'Portion', 'Alternatives'], rows, [210, 120, 189], styles))
        if meal.get('notes'):
            story.append(_p(meal['notes'], styles))
        story.append(Spacer(1, 8))
    story.append(_p('Dietary preferences and notes', styles, 'Heading2'))
    for field, label in [('dietary_preferences', 'Preferences'), ('allergies', 'Allergies'),
                         ('restrictions', 'Restrictions')]:
        story.append(_p(f"{label}: {', '.join(plan.get(field, [])) or 'None recorded'}", styles))
    if plan.get('notes'):
        story.append(_p(plan['notes'], styles))
    return _finish(output, doc, story)

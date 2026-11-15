"""GAD-7 (Generalized Anxiety Disorder 7-item scale, Spitzer et al. 2006) — a validated,
PATIENT-SELF-ADMINISTERED screening questionnaire. This is deliberately different from the
hidden linguistic markers elsewhere in this app: GAD-7 is designed to be filled in and read by
the patient themselves in ordinary clinical practice, so showing the score and its trend back to
the patient is standard practice, not a disclosure problem — it doubles as a motivating,
patient-owned self-tracking tool.

NOTE: item wording below is a plain-French adaptation for this prototype, not a claim to
reproduce any specific certified/copyrighted translation.
"""
from __future__ import annotations

ITEMS = [
    "Se sentir nerveux(se), anxieux(se) ou à cran",
    "Ne pas être capable d'arrêter de s'inquiéter ou de contrôler ses inquiétudes",
    "Trop s'inquiéter à propos de différentes choses",
    "Avoir du mal à se détendre",
    "Être si agité(e) qu'il est difficile de rester tranquille",
    "Devenir facilement contrarié(e) ou irritable",
    "Avoir peur que quelque chose d'horrible puisse arriver",
]
SCALE = ["Jamais", "Plusieurs jours", "Plus de la moitié des jours", "Presque tous les jours"]

BANDS = [
    (0, 4, "minime", "Anxiété minime", "#18a877"),
    (5, 9, "leger", "Anxiété légère", "#8bc34a"),
    (10, 14, "modere", "Anxiété modérée", "#e8872f"),
    (15, 21, "severe", "Anxiété sévère", "#e5484d"),
]
ALERT_THRESHOLD = 10  # usual clinical cutoff


def band_for(score: int) -> dict:
    for lo, hi, key, label, color in BANDS:
        if lo <= score <= hi:
            return {"key": key, "label": label, "color": color}
    return {"key": "inconnu", "label": "—", "color": "#999"}


def score(answers: list[int]) -> int:
    if len(answers) != 7 or any(a < 0 or a > 3 for a in answers):
        raise ValueError("GAD-7 attend exactement 7 réponses, chacune de 0 à 3")
    return sum(answers)


def streak_minime_or_leger(history: list[dict]) -> int:
    """Consecutive most-recent entries scoring in the 'minime'/'léger' band — for the
    motivational framing (streaks, encouragement) on the patient's own dashboard."""
    n = 0
    for entry in reversed(history):
        if band_for(entry["score"])["key"] in ("minime", "leger"):
            n += 1
        else:
            break
    return n

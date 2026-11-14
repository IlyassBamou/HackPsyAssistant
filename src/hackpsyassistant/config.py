"""Axes tracked by the assistant. The doctor can enable/disable them per patient."""

AXES = {
    "anxiety": {"label": "Anxiety", "risk": False, "color": "#e07a5f"},
    "mood": {"label": "Depressed mood", "risk": False, "color": "#3d5a80"},
    "sleep": {"label": "Sleep problems", "risk": False, "color": "#7b6cb5"},
    "isolation": {"label": "Social isolation", "risk": False, "color": "#2a9d8f"},
    "selfharm": {"label": "Self-harm risk", "risk": True, "color": "#c1121f"},
}

RECOMMENDATIONS = {
    "anxiety": "Try 5 minutes of box breathing (4-4-4-4) and a short walk outside.",
    "mood": "Plan one small pleasant activity today and message someone you trust.",
    "sleep": "Keep a fixed bedtime, no screens 1h before bed, and note your sleep in a diary.",
    "isolation": "Reach out to one friend or relative today, even with a short message.",
    "selfharm": "Please contact your doctor or a crisis line now (in France: 3114). You are not alone.",
}

# Trend alert thresholds
EMA_ALPHA = 0.4
SLOPE_WINDOW = 5
SLOPE_THRESHOLD = 0.03
LEVEL_FLOOR = 0.30
RISK_LEVEL_FLOOR = 0.15

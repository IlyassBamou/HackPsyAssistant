"""Axes tracked by the assistant. The doctor can enable/disable them per patient."""

AXES = {
    "anxiety": {"label": "Anxiété", "risk": False, "color": "#e07a5f"},
    "mood": {"label": "Humeur dépressive", "risk": False, "color": "#3d5a80"},
    "sleep": {"label": "Troubles du sommeil", "risk": False, "color": "#7b6cb5"},
    "isolation": {"label": "Isolement social", "risk": False, "color": "#2a9d8f"},
    "selfharm": {"label": "Risque suicidaire / automutilation", "risk": True, "color": "#c1121f"},
}

RECOMMENDATIONS = {
    "anxiety": "Essayez 5 minutes de respiration carrée (4-4-4-4) et une courte marche dehors.",
    "mood": "Prévoyez aujourd'hui une petite activité agréable et écrivez à une personne de confiance.",
    "sleep": "Gardez un horaire de coucher fixe, pas d'écran 1 h avant, et notez votre sommeil dans un carnet.",
    "isolation": "Contactez aujourd'hui un ami ou un proche, même par un court message.",
    "selfharm": "Contactez votre médecin ou le 3114 (numéro national de prévention du suicide, 24h/24) dès maintenant. Vous n'êtes pas seul(e).",
}

# Trend alert thresholds
EMA_ALPHA = 0.4
SLOPE_WINDOW = 5
SLOPE_THRESHOLD = 0.03
LEVEL_FLOOR = 0.30
RISK_LEVEL_FLOOR = 0.15

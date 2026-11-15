"""Linguistic markers tracked by the assistant.

IMPORTANT (clinical advisory board feedback): internal dict KEYS below (anxiety, mood, sleep,
isolation, selfharm) must stay as-is — they are baked into the fine-tuned model's id2label
mapping (models/xlmr-fr/config.json) and renaming them would require retraining.

What changed instead: every USER-FACING string is now a neutral, descriptive "linguistic marker"
label — never a diagnostic term (no "anxiety", "depression", "suicide risk" shown in the UI).
- `label`      : shown to the doctor, in the optional detailed-analysis panel.
- `hint`       : one-line explanation of what the marker reflects linguistically (shown on hover/click).
- `llm_hint`   : short internal description fed only to the LLM's reasoning, never rendered.
These are automatic linguistic hypotheses, not a diagnosis — interpretation is left to the doctor.
"""

DIAGNOSTIC_DISCLAIMER = (
    "Ces indicateurs sont des hypothèses linguistiques automatiques (fréquence et nature du "
    "vocabulaire employé). Ils ne constituent ni un diagnostic ni une évaluation clinique — "
    "seul le médecin interprète leur pertinence."
)

AXES = {
    "anxiety": {
        "label": "Charge de stress exprimée",
        "hint": "Fréquence de vocabulaire associé à la tension, l'inquiétude ou l'urgence perçue dans le discours.",
        "llm_hint": "charge de stress / tension exprimée",
        "risk": False, "color": "#e07a5f",
    },
    "mood": {
        "label": "Tonalité affective du discours",
        "hint": "Polarité émotionnelle du langage employé (vocabulaire plutôt sombre, neutre ou positif).",
        "llm_hint": "tonalité affective (plutôt sombre ou positive) exprimée",
        "risk": False, "color": "#3d5a80",
    },
    "sleep": {
        "label": "Mentions liées au sommeil",
        "hint": "Fréquence des mentions de sommeil, réveils nocturnes ou fatigue dans les messages.",
        "llm_hint": "mentions de troubles du sommeil",
        "risk": False, "color": "#7b6cb5",
    },
    "isolation": {
        "label": "Retrait social exprimé",
        "hint": "Fréquence du vocabulaire évoquant la solitude, l'évitement social ou le repli.",
        "llm_hint": "retrait social / isolement évoqué",
        "risk": False, "color": "#2a9d8f",
    },
    "selfharm": {
        "label": "Signal de vigilance prioritaire",
        "hint": ("Présence de termes associés à un sentiment de fardeau, un désespoir marqué ou des idées de mort. "
                 "Nécessite systématiquement une évaluation clinique par le médecin — ceci n'est pas un diagnostic."),
        "llm_hint": "signal de vigilance élevé (fardeau, désespoir, idées de mort) à prendre très au sérieux",
        "risk": True, "color": "#c1121f",
    },
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

# ---------------------------------------------------------------------------
# Declared-events detector (events.py): factual, rule-based, auditable — NOT a score.
# Each entry: (regex, kind, polarity, label). Matched on the raw patient message (lowercased).
EVENT_RULES = [
    (r"\b(arr[eê]t[eé]|stopp[eé]|plus pris|oubli[eé])\w*.{0,20}\b(traitement|m[eé]dicament|cachet|comprim[eé])",
     "traitement", "arret", "Arrêt ou interruption du traitement signalé"),
    (r"\b(repris|recommenc[eé]|re-?pris)\w*.{0,20}\b(traitement|m[eé]dicament|cachet)",
     "traitement", "reprise", "Reprise du traitement signalée"),
    (r"\b(nouveau|nouvelle|chang[eé]|augment[eé]|diminu[eé])\w*.{0,20}\b(traitement|m[eé]dicament|dose|ordonnance|posologie)",
     "traitement", "modification", "Modification du traitement signalée"),
    (r"\b(repris|recommenc[eé]|re-?pris|consomm[eé]|bu|pris)\w*.{0,25}\b(alcool|vin|bi[eè]re|cannabis|joint|herbe|coca[iï]ne|coke|drogue|stup[eé]fiant|tabac|cigarette|fumer|fum[eé])",
     "substance", "augmentation", "Reprise ou augmentation d'une consommation signalée"),
    (r"\b(arr[eê]t[eé]|stopp[eé]|plus touch[eé]|sevr[eé])\w*.{0,25}\b(alcool|vin|bi[eè]re|cannabis|joint|herbe|coca[iï]ne|coke|drogue|stup[eé]fiant|fumer|tabac|cigarette)",
     "substance", "arret", "Arrêt d'une consommation signalé"),
]

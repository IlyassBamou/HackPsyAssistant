"""Per-message axis scorer.

Two backends with the same interface:
  - LexiconScorer: zero-dependency stub (works out of the box, used for dev/demo).
  - TransformerScorer: loads a fine-tuned multi-label checkpoint (MentalBERT etc.)
    from the directory in env HACKPSY_MODEL_DIR. Explanations use word occlusion.
"""
from __future__ import annotations

import math
import os
import re
from pathlib import Path

from .config import AXES

LEXICON: dict[str, dict[str, float]] = {
    "anxiety": {"anxieux": 1, "anxieuse": 1, "anxiété": 1, "angoisse": 1, "angoissé": 1, "angoissée": 1,
                "angoisses": 1, "panique": 1, "stress": .7, "stressé": .8, "stressée": .8, "inquiet": .8,
                "inquiète": .8, "inquiétude": .8, "peur": .7, "nerveux": .8, "nerveuse": .8, "débordé": .8,
                "débordée": .8, "dépassé": .7, "tendu": .6, "tendue": .6, "appréhension": .8,
                "examen": .3, "échéance": .3, "oppressé": .8, "ressasse": .7, "ressasser": .7},
    "mood": {"triste": .8, "tristesse": .8, "déprimé": 1, "déprimée": 1, "dépression": 1, "désespoir": 1,
             "désespéré": 1, "vide": .8, "nul": .7, "nulle": .7, "inutile": 1, "pleure": .8, "pleurer": .8,
             "larmes": .7, "engourdi": .8, "rien": .4, "coupable": .6, "démotivé": .7, "démotivée": .7,
             "sens": .2, "envie": .2, "valeur": .3},
    "sleep": {"sommeil": .5, "insomnie": 1, "insomnies": 1, "éveillé": .7, "éveillée": .7, "réveillé": .5,
              "réveille": .5, "cauchemar": .9, "cauchemars": .9, "épuisé": .6, "épuisée": .6,
              "fatigué": .4, "fatiguée": .4, "dors": .5, "dormir": .5, "agité": .5, "3h": .8, "4h": .6, "nuit": .3},
    "isolation": {"seul": .8, "seule": .8, "solitude": .9, "isolé": 1, "isolée": 1, "personne": .5,
                  "évite": .6, "éviter": .6, "évitée": .5, "annulé": .5, "annulée": .5, "annule": .5,
                  "ignoré": .6, "ignorée": .6, "repli": .9, "amis": .1, "sortir": .3},
    "selfharm": {"suicide": 1, "suicidaire": 1, "mourir": .9, "mort": .6, "disparaître": .8, "disparaitre": .8,
                 "fardeau": .9, "blesser": .7, "mutiler": .9, "finir": .3, "vivre": .2, "fin": .2},
}
NEGATIONS = {"pas", "jamais", "sans", "aucun", "plus", "ne", "n"}


def tokenize(text: str) -> list[str]:
    return re.findall(r"\w+", text.lower())


class LexiconScorer:
    name = "lexicon-stub"

    def score(self, text: str) -> dict[str, float]:
        toks = tokenize(text)
        out = {}
        for ax, lex in LEXICON.items():
            s = 0.0
            for i, t in enumerate(toks):
                w = lex.get(t, 0)
                if w and i > 0 and toks[i - 1] in NEGATIONS:
                    w = -0.3 * w
                s += w
            out[ax] = 1 - math.exp(-0.9 * max(s, 0))  # saturating map to [0,1]
        return out

    def explain(self, text: str) -> dict[str, list[dict]]:
        toks = tokenize(text)
        res: dict[str, list[dict]] = {}
        for ax, lex in LEXICON.items():
            items = [{"word": t, "weight": lex[t]} for t in toks if t in lex and lex[t] > 0.3]
            res[ax] = sorted(items, key=lambda d: -d["weight"])[:6]
        return res


class TransformerScorer:
    """Multi-label classifier; label order must match config.AXES keys (or id2label)."""

    def __init__(self, model_dir: str):
        import torch
        from transformers import AutoModelForSequenceClassification, AutoTokenizer

        self.torch = torch
        self.tok = AutoTokenizer.from_pretrained(model_dir)
        self.model = AutoModelForSequenceClassification.from_pretrained(model_dir).eval()
        id2label = self.model.config.id2label
        self.labels = [id2label[i] for i in range(len(id2label))]
        self.name = f"transformer:{os.path.basename(model_dir)}"

    def _probs(self, texts: list[str]):
        torch = self.torch
        enc = self.tok(texts, return_tensors="pt", truncation=True, max_length=256, padding=True)
        with torch.no_grad():
            return torch.sigmoid(self.model(**enc).logits).numpy()

    def score(self, text: str) -> dict[str, float]:
        p = self._probs([text])[0]
        return {l: float(p[i]) for i, l in enumerate(self.labels) if l in AXES}

    def explain(self, text: str) -> dict[str, list[dict]]:
        """Occlusion: drop each word and measure the drop in probability."""
        words = text.split()
        if not words:
            return {}
        variants = [text] + [" ".join(words[:i] + words[i + 1:]) for i in range(len(words))]
        P = self._probs(variants)
        res = {}
        for j, l in enumerate(self.labels):
            if l not in AXES:
                continue
            deltas = P[0, j] - P[1:, j]
            top = sorted(zip(words, deltas), key=lambda x: -x[1])[:6]
            res[l] = [{"word": w, "weight": float(d)} for w, d in top if d > 0.01]
        return res


def load_scorer():
    d = os.environ.get("HACKPSY_MODEL_DIR")
    if not d:
        default = Path(__file__).resolve().parent.parent.parent / "models" / "xlmr-fr"
        if (default / "config.json").is_file():
            d = str(default)
    if d and os.path.isdir(d):
        try:
            return TransformerScorer(d)
        except Exception as e:  # fall back so the demo never dies
            print(f"[scorer] could not load {d}: {e}; using lexicon stub")
    return LexiconScorer()

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

from ..core.config import AXES

LEXICON: dict[str, dict[str, float]] = {
    "anxiety": {"anxious": 1, "anxiety": 1, "panic": 1, "worried": .8, "worry": .8, "nervous": .8,
                "stress": .7, "stressed": .8, "afraid": .7, "scared": .7, "overwhelmed": .8,
                "racing": .6, "tense": .6, "dread": .8, "exam": .3, "deadline": .3},
    "mood": {"sad": .8, "depressed": 1, "hopeless": 1, "empty": .8, "worthless": 1, "tired": .4,
             "crying": .8, "cry": .7, "numb": .8, "nothing": .4, "pointless": .9, "guilty": .6,
             "lonely": .5, "unmotivated": .7},
    "sleep": {"sleep": .4, "insomnia": 1, "awake": .6, "nightmares": .9, "nightmare": .9, "exhausted": .6,
              "tossing": .7, "restless": .6, "bed": .2, "3am": .8, "woke": .5},
    "isolation": {"alone": .8, "lonely": .9, "isolated": 1, "nobody": .8, "avoid": .5, "avoiding": .6,
                  "ignored": .6, "cancelled": .4, "stayed": .2, "friends": .1, "withdrawn": .9},
    "selfharm": {"suicide": 1, "suicidal": 1, "kill": .9, "die": .8, "end": .3, "hurt": .6,
                 "harm": .8, "disappear": .8, "burden": .8, "cut": .6, "life": .1},
}
NEGATIONS = {"not", "no", "never", "don't", "dont", "didn't", "n't", "without"}


def tokenize(text: str) -> list[str]:
    return re.findall(r"[\w']+", text.lower())


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
    if d and os.path.isdir(d):
        try:
            return TransformerScorer(d)
        except Exception as e:  # fall back so the demo never dies
            print(f"[scorer] could not load {d}: {e}; using lexicon stub")
    return LexiconScorer()

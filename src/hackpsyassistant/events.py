"""Declared-events detector: factual, rule-based, auditable extraction — deliberately NOT a score.

Clinically, "the patient stopped their treatment" or "started drinking again" is a fact the doctor
needs immediately, and it is far more defensible to surface as a transparent regex match with the
exact quote attached than as an opaque model probability. This module never guesses intent —
it only flags messages for the doctor to read.
"""
from __future__ import annotations

import re

from .config import EVENT_RULES

_COMPILED = [(re.compile(pat, re.IGNORECASE), kind, polarity, label) for pat, kind, polarity, label in EVENT_RULES]


def detect(message: str) -> list[dict]:
    out = []
    for rx, kind, polarity, label in _COMPILED:
        if rx.search(message):
            out.append({"kind": kind, "polarity": polarity, "label": label})
    return out

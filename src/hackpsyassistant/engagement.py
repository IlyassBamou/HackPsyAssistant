"""Engagement tracking and peer-matching.

Engagement (frequency of contact) is itself a clinically meaningful, non-diagnostic signal — a
patient going quiet is often as informative as what they say when they do write. Peer matching
finds patients with a similar current linguistic-marker profile so the doctor can consider
suggesting they support each other, optionally through a recovered, consenting peer mentor.
Nothing here is shown to the patient; everything is a doctor-side suggestion requiring consent.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime

import numpy as np

from .config import AXES

AXIS_ORDER = list(AXES)


def engagement_stats(convo: list[dict]) -> dict:
    user_msgs = [m for m in convo if m["role"] == "user" and m.get("ts")]
    if not user_msgs:
        return {"by_day": [], "days_since_last": None, "total_messages": 0, "trend": "flat"}
    days = [m["ts"][:10] for m in user_msgs]
    counts = Counter(days)
    by_day = [{"date": d, "count": c} for d, c in sorted(counts.items())]
    last = max(m["ts"] for m in user_msgs)
    days_since_last = (datetime.now() - datetime.fromisoformat(last)).days
    vals = [d["count"] for d in by_day]
    if len(vals) >= 4:
        h = len(vals) // 2
        trend = "down" if sum(vals[h:]) < sum(vals[:h]) * 0.6 else "up" if sum(vals[h:]) > sum(vals[:h]) * 1.4 else "flat"
    else:
        trend = "flat"
    return {"by_day": by_day, "days_since_last": days_since_last, "total_messages": len(user_msgs), "trend": trend}


def _vector(levels: dict) -> np.ndarray:
    return np.array([levels.get(a, {}).get("level", 0.0) for a in AXIS_ORDER])


def suggest_peers(target_sid: str, target_levels: dict, others: list[dict], top_k: int = 3) -> list[dict]:
    """others: [{sid, name, levels, mentor, n_messages}, ...] (already excludes target)."""
    v1 = _vector(target_levels)
    if np.linalg.norm(v1) < 1e-6:
        return []
    scored = []
    for o in others:
        if o["sid"] == target_sid or o["n_messages"] < 2:
            continue
        v2 = _vector(o["levels"])
        if np.linalg.norm(v2) < 1e-6:
            continue
        sim = float(np.dot(v1, v2) / (np.linalg.norm(v1) * np.linalg.norm(v2)))
        scored.append({"sid": o["sid"], "name": o["name"], "similarity": sim, "mentor": o.get("mentor", False)})
    scored.sort(key=lambda s: (-s["mentor"], -s["similarity"]))
    return scored[:top_k]

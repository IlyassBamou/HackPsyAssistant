"""Temporal layer: EMA smoothing, slope over a window, and alert logic per axis."""
from __future__ import annotations

import numpy as np

from ..core.config import (AXES, EMA_ALPHA, LEVEL_FLOOR, RECOMMENDATIONS, RISK_LEVEL_FLOOR,
                     SLOPE_THRESHOLD, SLOPE_WINDOW)


def ema(series: list[float], alpha: float = EMA_ALPHA) -> list[float]:
    out, prev = [], None
    for x in series:
        prev = x if prev is None else alpha * x + (1 - alpha) * prev
        out.append(prev)
    return out


def slope(series: list[float], window: int = SLOPE_WINDOW) -> float:
    y = series[-window:]
    if len(y) < 3:
        return 0.0
    return float(np.polyfit(np.arange(len(y)), y, 1)[0])


def analyze(history: list[dict[str, float]], active: list[str]) -> dict:
    """history: per-message raw scores. Returns smoothed series, slopes, alerts."""
    series, alerts, levels = {}, [], {}
    for ax in active:
        raw = [h.get(ax, 0.0) for h in history]
        sm = ema(raw)
        series[ax] = {"raw": raw, "ema": sm}
        s = slope(sm)
        lvl = sm[-1] if sm else 0.0
        levels[ax] = {"level": lvl, "slope": s}
        floor = RISK_LEVEL_FLOOR if AXES[ax]["risk"] else LEVEL_FLOOR
        if s > SLOPE_THRESHOLD and lvl > floor:
            alerts.append({"axis": ax, "label": AXES[ax]["label"], "level": lvl, "slope": s,
                           "recommendation": RECOMMENDATIONS[ax],
                           "critical": AXES[ax]["risk"]})
    alerts.sort(key=lambda a: (not a["critical"], -a["slope"]))
    # Global wellbeing-risk index: max-weighted mean of axis levels (higher = worse)
    vals = [levels[a]["level"] * (1.5 if AXES[a]["risk"] else 1.0) for a in active] or [0]
    index = float(min(1.0, np.mean(vals) * 1.4))
    return {"series": series, "levels": levels, "alerts": alerts, "index": index}

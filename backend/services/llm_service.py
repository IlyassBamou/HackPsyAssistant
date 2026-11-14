"""Chat + session summary. Uses Claude when ANTHROPIC_API_KEY is set, else a rule-based fallback."""
from __future__ import annotations

import os
import shutil

from ..core.config import AXES, RECOMMENDATIONS

MODEL = os.environ.get("HACKPSY_LLM_MODEL", "claude-opus-5-5")
CLI_MODEL = os.environ.get("HACKPSY_CLI_MODEL", "sonnet")  # sonnet is faster for live chat

SYSTEM = """You are a supportive companion assistant working under a clinician's guidance.
You are NOT a doctor and never diagnose. Be warm, brief (2-4 sentences), ask one gentle open question.
Doctor's context for this patient:
{context}

Current monitored trends (0-1, higher = more concerning):
{trends}
{alerts}
If an axis is flagged as rising, gently weave in the suggested activity, never as an order.
If self-harm risk is flagged, express care, encourage contacting the doctor or emergency line (3114 in France)."""


def _client():
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return None
    import anthropic
    return anthropic.Anthropic()


def _call_cli(system: str, messages: list[dict]) -> str:
    """Use the local Claude Code CLI (your subscription, no API key) in headless mode."""
    import subprocess
    convo = "\n".join(f"{m['role'].upper()}: {m['content']}" for m in messages)
    prompt = f"{convo}\n\nWrite only the next ASSISTANT reply (or the requested document)."
    r = subprocess.run(
        ["claude", "-p", prompt, "--system-prompt", system, "--tools", "", "--model", CLI_MODEL],
        capture_output=True, text=True, timeout=90)
    if r.returncode != 0 or not r.stdout.strip():
        raise RuntimeError(r.stderr.strip() or "empty cli output")
    return r.stdout.strip()


def _call(system: str, messages: list[dict], max_tokens: int = 1024) -> str:
    """Backend order: API key (if set) -> Claude Code CLI (subscription) -> raise (caller falls back)."""
    client = _client()
    if client is not None:
        r = client.beta.messages.create(
            model=MODEL, max_tokens=max_tokens, system=system, messages=messages,
            output_config={"effort": "low"},
            betas=["server-side-fallback-2026-07-01"], fallbacks="default",
        )
        return "".join(b.text for b in r.content if b.type == "text").strip()
    if os.environ.get("HACKPSY_USE_CLI", "1") == "1" and shutil.which("claude"):
        return _call_cli(system, messages)
    raise RuntimeError("no LLM backend available")


def _fmt(analysis: dict) -> tuple[str, str]:
    trends = "\n".join(f"- {AXES[a]['label']}: level {v['level']:.2f}, slope {v['slope']:+.3f}"
                       for a, v in analysis["levels"].items()) or "- (no data yet)"
    al = analysis["alerts"]
    alerts = ("Flagged rising: " + "; ".join(f"{a['label']} -> suggest: {a['recommendation']}" for a in al)) if al else ""
    return trends, alerts


def chat_reply(context: str, convo: list[dict], analysis: dict) -> tuple[str, str]:
    trends, alerts = _fmt(analysis)
    system = SYSTEM.format(context=context or "(none provided)", trends=trends, alerts=alerts)
    try:
        return _call(system, convo), "claude"
    except Exception as e:
        print(f"[llm] fallback reply ({e})")
        return _fallback_reply(convo, analysis), "fallback"


def _fallback_reply(convo: list[dict], analysis: dict) -> str:
    al = analysis["alerts"]
    if al:
        a = al[0]
        return (f"Thank you for sharing that, it sounds heavy. I've noticed things around "
                f"{a['label'].lower()} seem to be getting harder lately. {a['recommendation']} "
                f"Would you like to tell me more about what today was like?")
    return ("Thanks for telling me. I'm listening. What felt most difficult today, "
            "and was there anything that helped even a little?")


def summarize(context: str, convo: list[dict], analysis: dict) -> tuple[str, str]:
    trends, alerts = _fmt(analysis)
    transcript = "\n".join(f"{m['role']}: {m['content']}" for m in convo)
    system = ("You write concise clinical session summaries for the treating doctor. "
              "Sections: Themes, Evolution (use the trend data), Notable quotes, Suggested follow-up. "
              "Descriptive only, no diagnosis. Max 180 words.")
    user = f"Doctor context:\n{context}\n\nTrends:\n{trends}\n{alerts}\n\nTranscript:\n{transcript}"
    try:
        return _call(system, [{"role": "user", "content": user}], 1500), "claude"
    except Exception as e:
        print(f"[llm] fallback summary ({e})")
        lines = ["**Session summary (automatic, no LLM)**", "", "**Evolution**"]
        for a, v in analysis["levels"].items():
            arrow = "rising" if v["slope"] > 0.03 else "falling" if v["slope"] < -0.03 else "stable"
            lines.append(f"- {AXES[a]['label']}: {v['level']:.2f} ({arrow})")
        if analysis["alerts"]:
            lines += ["", "**Flags**"] + [f"- {a['label']}: {a['recommendation']}" for a in analysis["alerts"]]
        return "\n".join(lines), "fallback"

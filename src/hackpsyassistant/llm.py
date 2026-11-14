"""Chat + session summary. Uses Claude when ANTHROPIC_API_KEY is set, else a rule-based fallback."""
from __future__ import annotations

import os
import shutil

from .config import AXES, RECOMMENDATIONS

MODEL = os.environ.get("HACKPSY_LLM_MODEL", "claude-opus-5-5")
CLI_MODEL = os.environ.get("HACKPSY_CLI_MODEL", "sonnet")  # sonnet is faster for live chat

SYSTEM = """Tu es un assistant de soutien bienveillant qui travaille sous la supervision d'un médecin.
Tu n'es PAS médecin et tu ne poses jamais de diagnostic. Réponds TOUJOURS en français, de façon chaleureuse et brève
(2 à 4 phrases), en vouvoyant le patient, et pose une seule question ouverte et douce.
Contexte fourni par le médecin :
{context}

Tendances suivies (0-1, plus c'est haut plus c'est préoccupant) :
{trends}
{alerts}
Si un axe est signalé en hausse, intègre doucement l'activité suggérée, jamais comme un ordre.
Si le risque suicidaire est signalé, exprime ta sollicitude, encourage à contacter le médecin ou le 3114 (24h/24)."""


def _client():
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return None
    import anthropic
    return anthropic.Anthropic()


def _call_cli(system: str, messages: list[dict]) -> str:
    """Use the local Claude Code CLI (your subscription, no API key) in headless mode."""
    import subprocess
    convo = "\n".join(f"{m['role'].upper()}: {m['content']}" for m in messages)
    prompt = f"{convo}\n\nÉcris uniquement la prochaine réponse de ASSISTANT (ou le document demandé), en français."
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
    trends = "\n".join(f"- {AXES[a]['label']} : niveau {v['level']:.2f}, pente {v['slope']:+.3f}"
                       for a, v in analysis["levels"].items()) or "- (pas encore de données)"
    al = analysis["alerts"]
    alerts = ("Signalé en hausse : " + "; ".join(f"{a['label']} -> suggérer : {a['recommendation']}" for a in al)) if al else ""
    return trends, alerts


def chat_reply(context: str, convo: list[dict], analysis: dict) -> tuple[str, str]:
    trends, alerts = _fmt(analysis)
    system = SYSTEM.format(context=context or "(aucun)", trends=trends, alerts=alerts)
    try:
        return _call(system, convo), "claude"
    except Exception as e:
        print(f"[llm] fallback reply ({e})")
        return _fallback_reply(convo, analysis), "fallback"


def _fallback_reply(convo: list[dict], analysis: dict) -> str:
    al = analysis["alerts"]
    if al:
        a = al[0]
        return (f"Merci de me le confier, cela semble lourd à porter. Je remarque que le thème "
                f"« {a['label'].lower()} » devient plus difficile ces derniers temps. {a['recommendation']} "
                f"Voulez-vous me raconter comment s'est passée votre journée ?")
    return ("Merci de me l'avoir dit, je vous écoute. Qu'est-ce qui a été le plus difficile aujourd'hui, "
            "et y a-t-il eu quelque chose qui vous a aidé, même un peu ?")


def summarize(context: str, convo: list[dict], analysis: dict) -> tuple[str, str]:
    trends, alerts = _fmt(analysis)
    transcript = "\n".join(f"{m['role']}: {m['content']}" for m in convo)
    system = ("Tu rédiges en français des résumés de séance concis pour le médecin traitant. "
              "Sections : Thèmes, Évolution (appuie-toi sur les tendances chiffrées), Citations marquantes, Suivi suggéré. "
              "Descriptif uniquement, aucun diagnostic. 180 mots maximum.")
    user = f"Contexte du médecin :\n{context}\n\nTendances :\n{trends}\n{alerts}\n\nTranscription :\n{transcript}"
    try:
        return _call(system, [{"role": "user", "content": user}], 1500), "claude"
    except Exception as e:
        print(f"[llm] fallback summary ({e})")
        lines = ["**Résumé de séance (automatique, sans LLM)**", "", "**Évolution**"]
        for a, v in analysis["levels"].items():
            arrow = "en hausse" if v["slope"] > 0.03 else "en baisse" if v["slope"] < -0.03 else "stable"
            lines.append(f"- {AXES[a]['label']} : {v['level']:.2f} ({arrow})")
        if analysis["alerts"]:
            lines += ["", "**Alertes**"] + [f"- {a['label']} : {a['recommendation']}" for a in analysis["alerts"]]
        return "\n".join(lines), "fallback"

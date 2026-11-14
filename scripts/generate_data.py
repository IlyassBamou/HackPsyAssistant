"""Generate synthetic labeled FRENCH messages with Claude (uses your Claude Code subscription via the CLI).

GoEmotions only covers anxiety/mood. This fills sleep / isolation / selfharm (and extra anxiety/mood)
with first-person patient-style messages, in a JSONL file consumed by train.py.

  uv run python scripts/generate_data.py --per-axis 150 --out data/synthetic.jsonl
Each line: {"text": "...", "labels": {"anxiety":0|1, "mood":..., "sleep":..., "isolation":..., "selfharm":...}}
"""
import argparse, json, pathlib, random, subprocess

AXES = ["anxiety", "mood", "sleep", "isolation", "selfharm"]
DESC = {
    "anxiety": "inquiétude, panique, tension, sentiment d'être débordé, appréhension",
    "mood": "tristesse, vide, désespoir, perte d'intérêt, sentiment de nullité",
    "sleep": "insomnie, cauchemars, réveils nocturnes, épuisement dû au manque de sommeil",
    "isolation": "solitude, évitement des gens, annulation de rendez-vous, sentiment de déconnexion",
    "selfharm": "idées passives ou actives d'automutilation ou sentiment d'être un fardeau (réalisme de dépistage clinique ; aucune méthode)",
}
PROMPT = """Génère {n} courts messages à la première personne, EN FRANÇAIS (10 à 40 mots), tels qu'un patient pourrait les écrire à un chatbot de soutien thérapeutique.
Cible : exprime clairement **{ax}** ({desc}), avec des intensités variées : {mix}.
Retourne UNIQUEMENT une liste JSON de chaînes. Varie le vocabulaire et le ton (familier, soutenu, SMS léger). N'inclus AUCUNE méthode d'automutilation."""

def ask(prompt):
    r = subprocess.run(["claude", "-p", prompt, "--tools", "", "--model", "sonnet"],
                       capture_output=True, text=True, timeout=180)
    out = r.stdout.strip()
    return json.loads(out[out.index("["): out.rindex("]") + 1])

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-axis", type=int, default=150)
    ap.add_argument("--out", default="data/synthetic.jsonl")
    ap.add_argument("--batch", type=int, default=30)
    a = ap.parse_args()
    pathlib.Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    rows = []
    for ax in AXES:
        got = 0
        while got < a.per_axis:
            mix = random.choice(["surtout léger", "surtout modéré", "mélange de léger à sévère"])
            try:
                texts = ask(PROMPT.format(n=a.batch, ax=ax, desc=DESC[ax], mix=mix))
            except Exception as e:
                print("retry", ax, e); continue
            for t in texts:
                rows.append({"text": t, "labels": {k: int(k == ax) for k in AXES}}); got += 1
            print(ax, got)
    # neutral / positive negatives so the model learns "none"
    for _ in range(a.per_axis // 30 + 1):
        try:
            for t in ask("Génère 30 courts messages à la première personne, EN FRANÇAIS (10-40 mots), neutres ou positifs, du quotidien, sans détresse, adressés à un chatbot. Retourne UNIQUEMENT une liste JSON de chaînes."):
                rows.append({"text": t, "labels": {k: 0 for k in AXES}})
        except Exception as e:
            print("retry neutral", e)
    random.shuffle(rows)
    with open(a.out, "w") as f:
        for r in rows: f.write(json.dumps(r) + "\n")
    print("wrote", len(rows), "rows to", a.out)

if __name__ == "__main__":
    main()

"""Generate synthetic labeled messages with Claude (uses your Claude Code subscription via the CLI).

GoEmotions only covers anxiety/mood. This fills sleep / isolation / selfharm (and extra anxiety/mood)
with first-person patient-style messages, in a JSONL file consumed by train.py.

  uv run python scripts/generate_data.py --per-axis 150 --out data/synthetic.jsonl
Each line: {"text": "...", "labels": {"anxiety":0|1, "mood":..., "sleep":..., "isolation":..., "selfharm":...}}
"""
import argparse, json, pathlib, random, subprocess

AXES = ["anxiety", "mood", "sleep", "isolation", "selfharm"]
DESC = {
    "anxiety": "worry, panic, tension, overwhelm, dread",
    "mood": "sadness, emptiness, hopelessness, loss of interest, worthlessness",
    "sleep": "insomnia, nightmares, waking at night, exhaustion from poor sleep",
    "isolation": "loneliness, avoiding people, cancelling plans, feeling disconnected",
    "selfharm": "passive/active thoughts of self-harm or being a burden (clinical-screening realism; no methods)",
}
PROMPT = """Generate {n} short first-person messages (10-40 words) that a patient might type to a therapy-support chatbot.
Target: clearly expresses **{ax}** ({desc}), at mixed intensities: {mix}.
Return ONLY a JSON list of strings. Vary vocabulary and tone; some casual, some formal. Do NOT include methods of self-harm."""

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
            mix = random.choice(["mostly mild", "mostly moderate", "mixed mild to severe"])
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
            for t in ask("Generate 30 short first-person neutral or positive everyday messages (10-40 words) to a chatbot, no distress. Return ONLY a JSON list of strings."):
                rows.append({"text": t, "labels": {k: 0 for k in AXES}})
        except Exception as e:
            print("retry neutral", e)
    random.shuffle(rows)
    with open(a.out, "w") as f:
        for r in rows: f.write(json.dumps(r) + "\n")
    print("wrote", len(rows), "rows to", a.out)

if __name__ == "__main__":
    main()

# HackPsy Assistant

Plateforme de suivi thérapeutique augmenté : un compagnon conversationnel **vocal** pour le patient,
un **tableau de bord longitudinal** avec alertes pour le médecin. L'IA écoute, quantifie l'évolution
sur 5 axes cliniques et alerte le praticien — elle ne diagnostique jamais.

## Lancer la démo

```bash
uv run hackpsyassistant
# puis ouvrir http://127.0.0.1:8000
```

- **/** — page d'accueil (choix espace patient / médecin)
- **/patient** — chat patient : texte + **micro** (Whisper transcrit le français)
- **/doctor** — file active, trajectoires par axe, alertes de seuil, rapport IA

Deux patients de démonstration sont pré-chargés (Léa Martin — trajectoire qui se dégrade,
Karim Benali — stable).

## Architecture

```
voix patient ──► Whisper (STT) ──► texte ─┐
texte patient ────────────────────────────┼─► Scorer XLM-R fine-tuné (5 axes) ─► EMA + pente ─► alertes
                                          └─► LLM (Claude) conditionné par le contexte médecin + tendances
```

- **Scorer** : `models/xlmr-fr` (XLM-RoBERTa multi-label fine-tuné — voir `scripts/train.py`,
  entraîné sur GoEmotions + données synthétiques françaises avec BCE masquée)
- **STT** : `openai/whisper-small` (variable `HACKPSY_STT` pour changer)
- **LLM** : clé `ANTHROPIC_API_KEY` si présente, sinon CLI Claude Code, sinon repli local
- **Axes** : anxiété, humeur dépressive, sommeil, isolement social, risque suicidaire

## Entraînement

```bash
uv run python scripts/generate_data.py --per-axis 150   # dataset synthétique FR (via Claude)
uv run python scripts/train.py                          # ou scripts/train_colab.ipynb sur GPU
```

> Prototype de hackathon — pas un dispositif médical, aucun diagnostic.
> En cas de danger : **3114** (24h/24) ou 15.

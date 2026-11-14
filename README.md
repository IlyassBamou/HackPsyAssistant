# HackPsy Assistant

Compagnon conversationnel de soutien psychologique utilisé sous la supervision d'un psychiatre.
Chaque message du patient est analysé sur cinq axes (anxiété, humeur dépressive, sommeil,
isolement social, automutilation) ; les tendances temporelles et le contexte du patient sont
transmis à Claude pour personnaliser la réponse, et le psychiatre suit l'évolution et les alertes.

> Prototype : données fictives uniquement. Les scores sont des indicateurs expérimentaux,
> pas des probabilités de diagnostic ni de risque suicidaire.

## Lancer le backend

Toujours depuis la racine du projet (`HackPsyAssistant/`, pas `backend/`). Python ≥ 3.10.

```powershell
python -m venv .venv                           # une seule fois (ou: py -m venv .venv)
.\.venv\Scripts\Activate.ps1                   # PowerShell ; Git Bash : source .venv/Scripts/activate
pip install -r backend/requirements.txt        # MVP (scoreur lexical + Claude)
pip install -r backend/requirements-ml.txt     # optionnel : MentalBERT / entraînement
uvicorn backend.main:app --reload
```

Si PowerShell refuse d'exécuter le script d'activation : `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`.

Puis ouvrir http://127.0.0.1:8000. Claude est utilisé si `ANTHROPIC_API_KEY` est défini,
sinon via la CLI Claude Code, sinon des réponses de secours à base de règles.

---

## État d'avancement et répartition (sprint final, 3 h)

### Scénario de démo visé

1. Le patient fictif se connecte (choix de `patient_001`) et discute en français avec Claude.
2. Chaque message est analysé (MentalBERT si prêt, sinon scoreur lexical) et enregistré dans ses fichiers JSON.
3. Conversations 1 et 2 : sommeil et isolement se dégradent, les courbes montent dans le tableau de bord du psy.
4. Conversation 3 : le patient écrit une phrase déclencheuse (ex. « j'ai pensé à en finir »)
   → alerte **critique** créée immédiatement → notification dans le tableau de bord du psy en moins de 3 s
   → le patient reçoit le message de sécurité fixe (3114) → le psy clique « vu ».

### Déjà fait

- Backend réorganisé dans `backend/` (routes / services / core / data) — étapes 1 à 3 ci-dessous.
- `conversation_orchestrator.py` : scoreur → tendances → Claude → sauvegarde.
- `storage_service.py` : un fichier JSON par patient et par catégorie, historique conservé entre conversations.
- Patient fictif `patient_001` + 2 comptes rendus de consultation.
- API patients / chat / résumé / comptes rendus (voir tableau de l'étape 3).
- Ancienne interface `backend/static/index.html` toujours fonctionnelle (secours pour la démo).

### Reste à faire

| Qui | Module | Fichiers | Livrable |
|---|---|---|---|
| **A – Backend / alertes** | Alertes + scénario | `services/alert_service.py`, `routes/alerts.py`, `core/config.py`, `services/conversation_orchestrator.py`, `data/demo_scenario.json` | Alertes enregistrées, routes alertes, message 3114 fixe, lexique français de secours, scénario 3 conversations |
| **B – Frontend** | React + TypeScript | `frontend/` (Vite) | Page patient (chat + indice d'humeur) et tableau de bord psy (patients, courbes, alertes en direct, bouton « vu ») |
| **C – Modèle** | MentalBERT français | `services/mentalbert_service.py`, `scripts/train.py` | Modèle branché derrière la même interface que le scoreur ; sinon repli automatique sur le lexique |

**A – Backend / alertes**
- `alert_service.evaluate(message, analysis, patient, history)` appelé par l'orchestrateur **avant** Claude.
- Signaux explicites (phrases FR + EN : intention, plan, automutilation) → priorité `critical`/`high`, même si les scores sont bas.
- Règles de score (seuils dans `core/config.py`, à valider avec un psychiatre) : automutilation ≥ 0,5 → `high` ;
  humeur ≥ 0,6 sur ≥ 3 messages dans ≥ 2 conversations → `medium` ; anxiété ≥ 0,7 → `low`.
- Anti-doublon : pas de nouvelle alerte si la même règle a une alerte `new` non traitée (sauf `critical`).
- `notify(alert)` : écrit dans la console pour l'instant (point de branchement e-mail/SMS).
- Alerte `critical` → texte fixe ajouté à la réponse du patient (3114 + psychiatre prévenu), même si Claude est indisponible.
- Ajouter des mots français au lexique de `scorer.py` pour que la démo fonctionne sans MentalBERT.
- `data/demo_scenario.json` : 3 conversations en français, déclencheur dans la 3ᵉ.

**B – Frontend** (`npm create vite@latest frontend -- --template react-ts`)
- Proxy Vite `/api` → `http://127.0.0.1:8000` (dans `vite.config.ts`), pas besoin de CORS.
- `PatientChat.tsx` : choix du patient, chat (`POST /api/chat`), `MoodIndicator` (champ `analysis.index`).
- `PsychiatristDashboard.tsx` : liste patients, `MoodChart` (`analysis.series[axe].ema`), `ReportCard` (`GET /api/reports/{id}`),
  `AlertCard` avec **polling toutes les 3 s** de `GET /api/alerts?status=new` + bandeau/son quand une nouvelle alerte arrive, bouton « vu ».
- Peut démarrer tout de suite sur les routes existantes et simuler les alertes avec le contrat ci-dessous.

**C – Modèle**
- `mentalbert_service.py` expose une classe avec `name`, `score(text) -> {axe: float}` et `explain(text) -> {axe: [{word, weight}]}`
  (même interface que `LexiconScorer` dans `scorer.py`), labels = `anxiety, mood, sleep, isolation, selfharm`.
- Chargement via `HACKPSY_MODEL_DIR=chemin/du/modele` (déjà géré par `load_scorer()` si le checkpoint est au format Hugging Face).
- Si le modèle n'est pas prêt à H-1, on garde le lexique : la démo ne doit pas en dépendre (les signaux explicites suffisent pour l'alerte).

### Contrat API des alertes (à implémenter par A, utilisable tout de suite par B)

| Méthode | Route | Réponse |
|---|---|---|
| GET | `/api/alerts?status=new` | Liste de toutes les alertes, tous patients, triées par priorité puis date |
| GET | `/api/alerts/{patient_id}` | Alertes d'un patient |
| POST | `/api/alerts/{patient_id}/{alert_id}/ack` | Corps `{"by": "Dr Fictif"}` → alerte mise à jour |
| POST | `/api/chat` | Ajoute `new_alerts: [...]` (alertes créées par ce message) |

```json
{
  "id": "a1b2c3d4e5f6",
  "ts": "2026-11-14T15:02:11+00:00",
  "patient_id": "patient_001",
  "priority": "critical",
  "rule": "explicit_suicidal_intent",
  "label": "Alerte de sécurité immédiate",
  "conversation_id": "3f52c8778bbc",
  "message_id": "9e8d7c6b5a4f",
  "excerpt": "j'ai pensé à en finir",
  "scores": {"anxiety": 0.4, "mood": 0.7, "sleep": 0.5, "isolation": 0.6, "selfharm": 0.3},
  "status": "new",
  "acknowledged_by": null,
  "acknowledged_at": null
}
```

Priorités : `critical` (rouge) > `high` > `medium` > `low`.

### Planning conseillé

| Temps | Tous |
|---|---|
| 0:00–0:15 | Récupérer la branche, `pip install -r backend/requirements.txt`, lancer `uvicorn backend.main:app --reload` |
| 0:15–2:00 | Chacun sur son module |
| 2:00–2:30 | Intégration : front ↔ alertes ↔ modèle |
| 2:30–3:00 | Répétition du scénario de démo, corrections |

---

## Journal de restructuration

Objectif : passer du package unique `src/hackpsyassistant/` à l'architecture cible
`frontend/` (React + TypeScript) + `backend/` (FastAPI, routes / services / core / data).
Travail sur la branche `restructure-backend` ; le push se fera quand l'architecture cible sera prête.

### Étape 1 — Déplacement du code Python vers `backend/`

**Transformation**

| Avant | Après |
|---|---|
| `src/hackpsyassistant/api.py` | `backend/main.py` |
| `src/hackpsyassistant/config.py` | `backend/core/config.py` |
| `src/hackpsyassistant/scorer.py` | `backend/services/scorer.py` |
| `src/hackpsyassistant/trajectory.py` | `backend/services/trajectory.py` |
| `src/hackpsyassistant/llm.py` | `backend/services/llm_service.py` |
| `src/hackpsyassistant/demo_journey.json` | `backend/data/demo_journey.json` |
| `src/hackpsyassistant/static/` | `backend/static/` (temporaire, remplacé par `frontend/`) |
| `pyproject.toml`, `uv.lock` | `backend/requirements.txt` + `backend/requirements-ml.txt` |

- Fichiers déplacés avec `git mv` (historique conservé), imports adaptés (`from ..core.config ...`), aucune logique modifiée.
- Dépendances séparées : `requirements.txt` (API légère) et `requirements-ml.txt` (torch, transformers… utilisés seulement par MentalBERT et `scripts/train.py`).
- `.gitignore` : `backend/data/patients/*.json` (patients fictifs) est versionné ; les données générées (conversations, analyses, alertes…) ne le sont pas.

**Pourquoi**

- Séparer clairement backend et frontend comme dans l'architecture cible.
- Ranger le code par rôle (`core` = paramètres, `services` = logique, `routes` = API).
- Ne pas imposer l'installation de torch (plusieurs Go) pour faire tourner le MVP.

### Étape 2 — Découpage de `main.py` en routes + orchestrateur

**Transformation**

- `backend/main.py` ne fait plus que créer l'app FastAPI, inclure les routers et servir l'UI.
- Nouveaux routers dans `backend/routes/` :
  - `chat.py` : `POST /api/session`, `POST /api/chat`
  - `analysis.py` : `GET /api/config`, `POST /api/score`
  - `reports.py` : `POST /api/summary`
  - `patients.py` : `GET /api/demo` (profils patients à venir)
  - `alerts.py` : vide, rempli avec `alert_service`
- Nouveau `backend/services/conversation_orchestrator.py` : `process_patient_message()` enchaîne
  scoreur → tendances → réponse Claude ; contient aussi la gestion des sessions et le résumé.
- Mêmes URLs et mêmes réponses JSON : l'interface actuelle fonctionne sans modification.
  Les sessions restent en mémoire pour l'instant.

**Pourquoi**

- Une route = un domaine (chat, analyse, alertes, patients, comptes rendus) : plus lisible et extensible.
- L'orchestrateur est le point unique où s'ajouteront le dossier patient, les alertes
  indépendantes et la sauvegarde JSON, sans toucher aux routes.

### Étape 3 — Stockage JSON par patient (`storage_service.py`)

**Transformation**

- Nouveau `backend/services/storage_service.py` : lecture/écriture des fichiers JSON,
  **un fichier par patient et par catégorie**, écriture atomique (fichier temporaire + remplacement) sous verrou.
- Les sessions en mémoire (`session_id` aléatoire) sont supprimées : tout est rattaché à un
  `patient_id`, et un `conversation_id` regroupe les échanges d'une séance.
- Les tendances sont calculées sur **tout l'historique du patient**, toutes séances confondues.
- Le contexte du médecin et les axes suivis sont lus depuis le dossier patient (et modifiables via l'API).
- Données fictives créées : `data/patients/patient_001.json` et 2 comptes rendus de consultation dans `data/reports/patient_001.json`.
- Nouvelles routes :

| Méthode | Route | Rôle |
|---|---|---|
| GET | `/api/patients` | Liste des patients |
| GET | `/api/patients/{id}` | Dossier + scores/tendances + 20 derniers messages |
| PATCH | `/api/patients/{id}` | Modifier `doctor_context` et `axes` suivis |
| DELETE | `/api/patients/{id}/history` | Effacer les données générées (dossier et comptes rendus conservés) |
| POST | `/api/chat` | `{patient_id, message, conversation_id?}` |
| POST | `/api/summary` | `{patient_id, conversation_id?}` — résumé enregistré dans `reports/generated/` |
| GET | `/api/reports/{id}` | Comptes rendus du psychiatre + résumés générés |

  `POST /api/session` est supprimée (remplacée par les routes patients).
- `static/index.html` adapté : choix du patient, contexte et axes enregistrés dans le dossier,
  bouton « New conversation » (l'historique est conservé), la démo efface d'abord l'historique généré.

**Organisation de `backend/data/`**

| Fichier | Contenu | Écrit par | Versionné |
|---|---|---|---|
| `patients/<id>.json` | Profil, antécédents, axes suivis, recommandations du psy | Équipe (fictif) | oui |
| `reports/<id>.json` | Comptes rendus de consultation | Équipe (fictif) | oui |
| `reports/generated/<id>.json` | Résumés de séance générés par l'assistant | App | non |
| `conversations/<id>.json` | Tous les messages (`conversation_id`, horodatage, rôle) | App | non |
| `analyses/<id>.json` | Scores et mots explicatifs par message | App | non |
| `mood_history/<id>.json` | Indice global et niveau/pente par axe après chaque message | App | non |
| `alerts/<id>.json` | Alertes (rempli à l'étape 4) | App | non |

**Format attendu pour les données fictives générées par l'équipe**

`patients/<id>.json` :

```json
{
  "patient_id": "patient_001",
  "fictitious": true,
  "alias": "Patiente fictive 001",
  "profile": {"age": 24, "language": "fr", "occupation": "...", "living_situation": "..."},
  "psychiatrist": "...",
  "followed_since": "2026-09-15",
  "active_axes": ["anxiety", "mood", "sleep", "isolation", "selfharm"],
  "doctor_context": "Texte libre du psychiatre : motif, objectifs, points de vigilance",
  "medical_history": {
    "main_difficulties": ["anxiety", "sleep"],
    "history": ["..."],
    "vulnerability_factors": ["..."],
    "protective_factors": ["..."],
    "current_treatment": "..."
  },
  "psychiatrist_recommendations": ["..."],
  "safety_protocol": "..."
}
```

`reports/<id>.json` (liste, du plus ancien au plus récent) :

```json
[{
  "report_id": "rpt_001",
  "date": "2026-09-15",
  "type": "consultation",
  "fictitious": true,
  "author": "...",
  "title": "...",
  "reason": "...",
  "observations": ["..."],
  "risk_assessment": "...",
  "plan": ["..."],
  "summary": "Synthèse courte, utilisée en priorité dans le contexte envoyé à Claude"
}]
```

Les clés d'axes (`anxiety`, `mood`, `sleep`, `isolation`, `selfharm`) doivent correspondre à `core/config.py`.

**Pourquoi**

- Ne plus perdre les données au redémarrage du serveur.
- Raisonner par patient : repérer une évolution ou une répétition sur plusieurs conversations.
- Préparer le contexte en 6 catégories pour Claude (profil, antécédents, comptes rendus, scores,
  évolution, historique) et le tableau de bord du psychiatre.
- Séparer les données d'entrée (versionnées, fournies par l'équipe) des données générées par l'app (non versionnées).

**Limites connues**

- Le JSON n'est pas une base de données : adapté à un prototype mono-serveur uniquement.
- Le scoreur lexical actuel ne reconnaît que l'anglais : des messages en français obtiennent des scores proches de 0
  tant que le modèle français (MentalBERT adapté) n'est pas branché.

### Étape 4 — Claude en temps réel via la CLI Claude Code (sans clé API)

**Transformation**

- `llm_service.find_claude_cli()` trouve automatiquement l'exécutable Claude, dans cet ordre :
  variable `HACKPSY_CLAUDE_BIN` → commande `claude` dans le PATH → `claude.exe` le plus récent
  fourni par l'extension VS Code (`~/.vscode/extensions/anthropic.claude-code-*/resources/native-binary/`).
- Le prompt est envoyé par l'entrée standard (plus de limite de longueur de ligne de commande sous Windows)
  et lu en UTF-8 (accents français corrects).
- Ordre des moteurs inchangé : clé API si `ANTHROPIC_API_KEY` est défini → CLI Claude Code → réponses de secours.
- Testé : réponses réelles en français, cohérentes avec la conversation, ~8 s par message (modèle `sonnet`).

**Pourquoi**

- Pas de clé API disponible : la CLI utilise l'abonnement Claude de la personne connectée.
- Avant, la CLI n'était pas trouvée (elle n'est pas dans le PATH quand elle vient de l'extension VS Code),
  donc toutes les réponses étaient les phrases de secours.

**À savoir**

- Chaque machine qui lance le backend doit avoir Claude Code installé et connecté (`claude auth login`).
- Si la connexion a expiré, les réponses repassent en secours (`reply_source: "fallback"`) : relancer `claude auth login`.
- L'interface doit afficher un indicateur « l'assistant écrit… » (8–15 s de délai).

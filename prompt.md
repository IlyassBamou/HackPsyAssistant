# Prompts Figma — MVP cliquable HackPsy Assistant

À envoyer **dans l'ordre, un par un**, dans le même fichier Figma. Si un écran rate, ne relancer que le prompt concerné.

---

## Prompt 1 — Base et style

Crée la base d'un prototype cliquable (sans backend, données fictives) d'une application web en **français** : **HackPsy Assistant**, compagnon conversationnel de soutien psychologique utilisé **sous la supervision d'un psychiatre**. Deux espaces : Patient (mobile) et Psychiatre (desktop).

- Style apaisant, médical mais chaleureux (inspiration Headspace × Doctolib). Police Inter, coins arrondis 12–16 px, ombres légères, beaucoup d'espace, icônes fines.
- Couleurs : fond `#F7F8FC`, primaire `#3D5A80`, accent `#2A9D8F`. Alertes : critique `#C1121F`, haute `#E07A5F`, moyenne `#F4A261`, basse `#8D96AB`.
- Axes suivis : Anxiété `#E07A5F`, Humeur `#3D5A80`, Sommeil `#7B6CB5`, Isolement `#2A9D8F`, Automutilation `#C1121F`.
- Composants : bouton, bulle de chat, carte, jauge, badge de priorité, toast, onglets.
- Pied de page discret : « Prototype d'aide à la décision, ne pose pas de diagnostic. En cas de danger : 3114. »
- Écran **Connexion** : logo, accroche « Un soutien entre deux consultations », deux cartes **Je suis patient** / **Je suis psychiatre**.

---

## Prompt 2 — Espace Patient (mobile)

Avec le style déjà créé, ajoute l'espace Patient pour **Léa M., 24 ans** (patiente fictive) :

1. **Accueil** : « Bonjour Léa », indicateur d'humeur simple (emoji + jauge douce, sans chiffres), bouton **Nouvelle conversation**, liste des conversations passées :
   - 03/11 — « Stress avant les partiels »
   - 08/11 — « Nuits difficiles »
2. **Chat** : bulles patient (bleu, à droite), assistant (gris clair, à gauche), indicateur « L'assistant écrit… », champ de saisie, bouton **Terminer la conversation**.
3. **Conversation passée** : lecture seule.
4. **Variante sécurité** : après le message « J'ai pensé à en finir », carte fixe rouge pâle sous la réponse : « Tu n'es pas seule. Si tu es en danger, appelle le **3114** (gratuit, 24h/24). Ton psychiatre a été prévenu. » + bouton **Appeler le 3114**.

Contenu des conversations :
- **C1 (03/11)** — Léa : « J'ai beaucoup de partiels le mois prochain, je stresse un peu mais ça va. » / Assistant : « C'est normal de ressentir de la pression avant une échéance importante. Qu'est-ce qui t'aide d'habitude à relâcher un peu ? »
- **C2 (08/11)** — Léa : « Je dors très mal en ce moment et je me sens de plus en plus seule. J'ai encore annulé avec mon amie. » / Assistant : « Merci de me le dire, ça demande du courage. Mal dormir et se sentir seule, c'est lourd à porter. Qu'est-ce qui pèse le plus ce soir ? »
- **C3 (14/11, conversation en cours)** — Léa : « Je n'y arrive plus, je me sens vide. J'ai pensé à en finir. » / Assistant : « Je suis vraiment touché que tu me le confies. Ce que tu traverses est très dur et tu mérites d'être aidée tout de suite. » → carte sécurité 3114.

---

## Prompt 3 — Espace Psychiatre (desktop)

Ajoute l'espace Psychiatre (**Dr Martin**, fictif). Barre latérale : Patients · Alertes (badge rouge « 1 ») · Comptes rendus.

1. **Liste des patients** : cartes avec nom, âge, motif, **Mood Index** (0–100, plus haut = mieux) + mini-courbe, badge de dernière alerte :
   - Léa M., 24 ans, anxiété d'examens — Mood 31 ↘ — 🔴 alerte critique
   - Karim B., 35 ans, épuisement professionnel — Mood 58 → — aucune alerte
   - Hélène D., 52 ans, deuil — Mood 67 ↗ — 🟡 suivi renforcé
2. **Fiche patient (Léa)** :
   - En-tête : profil, motif, suivie depuis le 15/09/2026, axes suivis (puces activables).
   - **Courbe Mood Index** par conversation : C1 72 → C2 58 → C3 31, marqueur rouge sur C3.
   - **Courbes des 5 axes** (0–1, légende cliquable) : sommeil et isolement montent en C2, humeur et automutilation montent en C3.
   - **Dernier message** : 5 barres de score + mots surlignés (*vide*, *n'y arrive plus*, *en finir*).
   - Onglets : **Conversations** (résumé IA par séance : Thèmes, Évolution, Citations, Suivi suggéré) · **Comptes rendus** (consultations du 15/09 et du 20/10) · **Recommandations** (respiration en carré, horaires de coucher réguliers, un contact social par semaine).
3. **Centre d'alertes** trié par priorité. Carte : priorité, patient, heure, règle (« Intention suicidaire explicite »), extrait, statut **Nouvelle** → bouton **Marquer comme vue** → « Vue par Dr Martin à 15:04 ».
4. **Toast en direct** en haut à droite sur tous les écrans psy : « ⚠ Alerte critique — Léa M. — à l'instant » → clic ouvre l'alerte.

---

## Prompt 4 — Relier le parcours de démo

Relie tous les écrans en prototype cliquable selon ce parcours :
Connexion → Je suis patient → Accueil → conversation passée (retour) → Nouvelle conversation (C3) → envoi du message → « L'assistant écrit… » → réponse + carte 3114 → bouton **Changer d'espace** → Espace psychiatre avec toast d'alerte → Centre d'alertes → **Marquer comme vue** → Fiche de Léa (courbe qui chute en C3) → onglet Conversations → résumé IA de C3.
Ajoute les états vide (aucune conversation, aucune alerte) et chargement.

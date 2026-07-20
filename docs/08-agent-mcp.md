# Agent — Serveur MCP (option B du Moteur IA)

PEAdvisor expose ses fonctions comme **outils MCP** (Model Context Protocol).
Connecté à Claude Desktop, l'agent peut consulter les actifs et leurs
sous-scores, interroger le tableau de bord, lancer un classement TOPSIS,
demander une allocation, gérer la watchlist, déclencher une mise à jour et
lire le rapport d'auto-diagnostic — puis **expliquer et synthétiser** tout
cela en langage naturel.

Principe d'architecture (rappel) : les moteurs déterministes de PEAdvisor
restent seuls responsables des chiffres ; l'agent interprète, explique,
compare. Il ne recalcule jamais un score. L'utilisation passe par votre
abonnement Claude : **aucune clé API n'est nécessaire**.

## 1. Prérequis

- Le dépôt cloné, avec les dépendances installées :
  `pip install -r requirements.txt` (le serveur MCP utilise la bibliothèque
  `mcp`).
- Il n'est **pas nécessaire** que le serveur web (`python run.py`) tourne :
  le serveur MCP accède directement à la base SQLite via les services
  applicatifs, et initialise la base au premier lancement si besoin.

## 2. Déclarer le serveur dans Claude Desktop

Éditer le fichier de configuration de Claude Desktop :

- **macOS** : `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Windows** : `%APPDATA%\Claude\claude_desktop_config.json`

Ajouter (en adaptant le chemin du dépôt, et celui de Python si vous utilisez
un environnement virtuel — recommandé : pointer sur `.venv/bin/python`) :

```json
{
  "mcpServers": {
    "peadvisor": {
      "command": "/chemin/vers/PEAdvisor/.venv/bin/python",
      "args": ["/chemin/vers/PEAdvisor/mcp_server.py"]
    }
  }
}
```

Redémarrer Claude Desktop : les outils « peadvisor » apparaissent dans le
menu des connecteurs.

## 3. Les 16 outils exposés

| Outil | Rôle |
|---|---|
| `lister_actifs` | Actifs triés par score (filtre ACTION / ETF / OPCVM) |
| `fiche_actif` | Fiche complète + sous-scores du score propriétaire |
| `synthese_dashboard` | KPI, répartitions, tops du tableau de bord |
| `classement_multicritere` | Classement TOPSIS ou score pondéré |
| `correlations` | Matrice de corrélation des rendements (diversification réelle) |
| `taux_sans_risque` | Taux sans risque courant (fixe ou BCE) et son origine |
| `proposer_allocation` | Allocation selon capital / risque / horizon / objectif |
| `simuler_investissement` | Projection PEA : versements, dividendes, 3 scénarios, fiscalité |
| `consulter_watchlist` / `gerer_watchlist` | Suivi de valeurs |
| `lancer_mise_a_jour` | Import + dédoublonnage + rescoring |
| `journal_traitements` | Journal des traitements |
| `rapport_systeme` | Auto-diagnostic (dernier rapport ou nouveau) |
| `lister_anomalies` | Anomalies détectées par l'auto-observation |
| `ponderations_score` | Pondérations et bornes actuelles du score |
| `optimiser_ponderations` | Suggestion de pondérations plus prédictives (jamais appliquée automatiquement) |

## 4. Exemples de conversations

- *« Compare le classement TOPSIS et le classement par score pondéré : quelles
  valeurs sont robustes dans les deux ? Explique les écarts. »*
- *« Propose une allocation pour 25 000 €, profil 5, horizon 15 ans, objectif
  croissance, puis justifie chaque poche. »*
- *« Lance un auto-diagnostic et fais-moi un plan d'action à partir des
  recommandations du système. »*
- *« Examine les anomalies ouvertes : lesquelles sont de vraies erreurs de
  données, lesquelles sont explicables ? »*
- *« Rédige une note d'analyse d'une page sur les forces et faiblesses de
  Schneider Electric à partir de sa fiche. »*

## 5. Limites et garde-fous

- **Écritures volontairement limitées** : l'agent peut gérer la watchlist,
  lancer une mise à jour et créer une *suggestion* de pondérations — mais
  l'application d'une suggestion reste une décision humaine (écran Système).
  Les autres écritures (modification directe des pondérations, suppression)
  ne sont pas exposées.
- Les données `seed` sont illustratives : les analyses de l'agent n'ont de
  valeur réelle qu'une fois une source de données vivante branchée.
- Comme partout dans PEAdvisor : sorties indicatives, pas un conseil en
  investissement.

## 6. Trajectoire

Les définitions d'outils de ce serveur sont la base commune des étapes
suivantes du Moteur IA : l'**option A** (agent intégré à l'application via
l'API Claude, onglet « Analyste ») réutilisera les mêmes fonctions, et
l'**option C** (agent autonome planifié, rapport du matin) les consommera à
son tour une fois l'application hébergée.

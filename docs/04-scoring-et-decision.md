# Scoring et moteur de décision

## 1. Sous-notes (0 à 100) — 10 familles de critères

Chaque actif reçoit des sous-notes réparties en **10 familles**, calculées par
normalisation linéaire de l'indicateur brut entre des bornes paramétrables
(`config/scoring.yaml`) :

| Famille | Indicateur brut | Bornes par défaut | Sens |
|---|---|---|---|
| potentiel | (objectif de cours / cours − 1) × 100 | −20 % → +50 % | plus c'est haut, mieux c'est |
| valorisation | PER (EV/EBITDA, P/B, PEG à venir) | 5 → 40 | **inversé** (PER bas = bonne note) |
| croissance | croissance estimée (%) | −10 % → +30 % | croissant |
| qualite | qualité financière : marge nette = BNA × nb titres / CA (proxy ROE/ROIC) | 0 % → 25 % | croissant |
| solidite | dette nette / capitalisation | −0,5 → 2,0 | **inversé** (peu endetté = bonne note) |
| momentum | performance ~12 mois (moteur quantitatif) | −30 % → +40 % | croissant |
| dividende | rendement (%) | 0 % → 8 % | croissant |
| volatilite | volatilité annualisée (%) — risque | 5 % → 40 % | **inversé** (volatilité basse = bonne note) |
| consensus | consensus analystes | 1 → 5 | croissant |
| esg | score ESG | déjà sur 0-100 | croissant |

Les valeurs hors bornes sont plafonnées (note 0 ou 100). Une donnée manquante
donne une sous-note absente (pas 0) — voir ci-dessous. Les familles dont la
donnée brute n'est pas encore collectée (qualité, solidité, momentum sur les
valeurs sans historique) restent neutres et voient leur poids redistribué.

## 2. Score global propriétaire et profils de pondération

Score pondéré sur 100. Les pondérations par défaut couvrent les 10 familles ;
elles sont pilotées depuis **Paramètres → Score**.

**Profils de pondération (CRUD)** — l'écran Score propose des profils
préenregistrés et permet d'en créer/modifier/supprimer :

| Critère | Value | Growth | Dividend | Quality | Momentum |
|---|--:|--:|--:|--:|--:|
| Potentiel | 15 | 20 | 10 | 10 | 15 |
| Valorisation | 30 | 10 | 15 | 15 | 5 |
| Croissance | 10 | 30 | 5 | 15 | 20 |
| Qualité financière | 10 | 10 | 10 | 25 | 10 |
| Solidité | 10 | 5 | 15 | 15 | 5 |
| Dividende | 5 | 0 | 30 | 10 | 0 |
| Volatilité | 10 | 5 | 10 | 5 | 5 |
| Momentum | 5 | 10 | 5 | 0 | 30 |
| Consensus | 3 | 5 | 5 | 3 | 5 |
| ESG | 2 | 5 | 5 | 2 | 5 |

Un profil **IA** (équilibré, orienté facteurs empiriquement robustes) est aussi
fourni et peut être affiné par l'auto-amélioration (onglet Système). Endpoints :
`GET/POST /api/scoring/profils`, `PUT/DELETE /api/scoring/profils/{nom}`,
`POST /api/scoring/profils/{nom}/appliquer`, `GET /api/scoring/criteres`.

Deux règles importantes :

- **Pondérations paramétrables** : modifiables dans `config/scoring.yaml`, via
  l'éditeur (« Enregistrer & recalculer ») ou en **appliquant un profil** (le
  recalcul de tous les scores est immédiat) ;
- **Données manquantes** : le poids des critères absents est **redistribué**
  sur les critères disponibles. Un ETF sans PER n'est donc pas pénalisé
  artificiellement ; si aucune donnée n'existe, la note neutre (50) s'applique.

## 3. Matrice de décision multicritère

Deux méthodes livrées (`peadvisor/services/decision.py`), sélectionnables sur
`/api/dashboard/classement?methode=…` :

### `weighted` — score pondéré
Classement simple par score global décroissant.

### `topsis` — Technique for Order Preference by Similarity to Ideal Solution
1. matrice actifs × 10 critères (sous-notes, donnée manquante → note neutre) ;
2. normalisation vectorielle, pondération par les poids du scoring ;
3. construction de la solution **idéale** (meilleure valeur par critère) et
   **anti-idéale** (pire valeur) ;
4. pour chaque actif, distances euclidiennes aux deux solutions puis
   **coefficient de proximité** `C = d⁻ / (d⁺ + d⁻)` ∈ [0, 1] ;
5. classement par C décroissant.

TOPSIS récompense les profils **équilibrés** (proches de l'idéal sur tous les
critères), là où le score pondéré peut favoriser un actif excellent sur un seul
critère fortement pondéré. Comparer les deux classements sur le tableau de bord
est en soi un indicateur : un actif bien classé par les deux méthodes est un
choix robuste.

### Extensions prévues
AHP (dérivation des poids par comparaisons par paires), PROMETHEE et ELECTRE
s'ajouteront dans le même module avec la même signature
(`classer(actifs, methode, ponderations)`), donc sans impact sur l'API ni
l'interface.

# Scoring et moteur de décision

## 1. Sous-notes (0 à 100)

Chaque actif reçoit 7 sous-notes, calculées par normalisation linéaire de
l'indicateur brut entre des bornes paramétrables (`config/scoring.yaml`) :

| Critère | Indicateur brut | Bornes par défaut | Sens |
|---|---|---|---|
| potentiel | (objectif de cours / cours − 1) × 100 | −20 % → +50 % | plus c'est haut, mieux c'est |
| valorisation | PER | 5 → 40 | **inversé** (PER bas = bonne note) |
| croissance | croissance estimée (%) | −10 % → +30 % | croissant |
| esg | score ESG | déjà sur 0-100 | croissant |
| dividende | rendement (%) | 0 % → 8 % | croissant |
| volatilite | volatilité annualisée (%) | 5 % → 40 % | **inversé** (volatilité basse = bonne note) |
| consensus | consensus analystes | 1 → 5 | croissant |

Les valeurs hors bornes sont plafonnées (note 0 ou 100). Une donnée manquante
donne une sous-note absente (pas 0) — voir ci-dessous.

## 2. Score global propriétaire

Score pondéré sur 100 avec les pondérations du cahier des charges par défaut :

potentiel 25 % · valorisation 15 % · croissance 15 % · ESG 15 % ·
dividende 10 % · volatilité 10 % · consensus 10 %

Deux règles importantes :

- **Pondérations paramétrables** : modifiables dans `config/scoring.yaml` ou
  depuis l'écran Paramètres (le recalcul de tous les scores est immédiat).
- **Données manquantes** : le poids des critères absents est **redistribué**
  sur les critères disponibles. Un ETF sans PER n'est donc pas pénalisé
  artificiellement ; si aucune donnée n'existe, la note neutre (50) s'applique.

## 3. Matrice de décision multicritère

Deux méthodes livrées (`peadvisor/services/decision.py`), sélectionnables sur
`/api/dashboard/classement?methode=…` :

### `weighted` — score pondéré
Classement simple par score global décroissant.

### `topsis` — Technique for Order Preference by Similarity to Ideal Solution
1. matrice actifs × 7 critères (sous-notes, donnée manquante → note neutre) ;
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

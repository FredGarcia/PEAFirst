# Moteur d'allocation automatique

Entrées utilisateur : **capital** (€), **niveau de risque** (1 à 7),
**horizon** (années), **objectif** (croissance / dividendes / équilibré).
Sortie : liste de lignes (valeur, poids, montant, justification) et répartition
par type. Endpoint : `POST /api/allocation`.

## 1. Poches de risque

Les actifs sont regroupés selon leur niveau de risque (SRI fourni ou dérivé de
la volatilité) :

- **Défensive** : niveaux 1-3
- **Cœur** : niveaux 4-5
- **Dynamique** : niveaux 6-7

## 2. Répartition cible par profil

| Profil | Défensive | Cœur | Dynamique |
|---|---|---|---|
| 1 | 70 % | 30 % | 0 % |
| 2 | 55 % | 40 % | 5 % |
| 3 | 40 % | 50 % | 10 % |
| 4 | 25 % | 55 % | 20 % |
| 5 | 15 % | 55 % | 30 % |
| 6 | 5 % | 50 % | 45 % |
| 7 | 0 % | 40 % | 60 % |

**Ajustement horizon** : < 5 ans → 10 points transférés du dynamique vers le
défensif ; ≥ 15 ans → 10 points du défensif vers le dynamique. Une poche cible
sans actif disponible reverse son poids à la poche cœur.

## 3. Sélection selon l'objectif

À l'intérieur de chaque poche, les valeurs sont classées par une métrique liée
à l'objectif :

- **équilibré** : score global ;
- **croissance** : 35 % sous-note croissance + 25 % potentiel + 40 % score global ;
- **dividendes** : 50 % sous-note dividende + 20 % volatilité (inversée) + 30 % score global.

## 4. Contraintes de diversification (paramétrables, `config/settings.yaml`)

| Paramètre | Défaut | Rôle |
|---|---|---|
| `poids_max_par_ligne` | 10 % | Aucune ligne ne dépasse ce poids ; le nombre de lignes est augmenté si nécessaire pour que le plafond soit tenable |
| `poids_max_par_secteur` | 30 % | Un secteur sur-représenté voit ses candidats suivants écartés |
| `lignes_min` / `lignes_max` | 8 / 25 | Nombre de lignes, ajusté au capital (≈ 1 ligne par 1 500 €) |
| `part_min_etf_opcvm` | 30 % | Part minimale de fonds (ETF/OPCVM) dans la poche cœur — le socle indiciel classique d'un PEA |

Les poids intra-poche sont proportionnels à la métrique de sélection, plafonnés
par ligne, puis l'ensemble est renormalisé à 100 % du capital.

## 4 bis. Critères de sélection et complétude des données

La métrique de sélection combine, selon l'objectif, le score global, le
dividende / la croissance / le potentiel, plus un **bonus transversal** de
qualité **ESG** et de **liquidité**, et une **pénalité de complétude** : une
valeur aux données clés manquantes est défavorisée.

Deux garde-fous de qualité de données :

- une valeur n'est **allouable** que si son **cours** et son **score** sont
  connus ; les autres valeurs éligibles sont **écartées** et listées à part
  (`valeurs_incompletes`, avec le détail des informations manquantes) ;
- chaque ligne retenue porte ses éventuelles **informations manquantes**
  (`informations_manquantes` : secteur, ESG, niveau de risque, cours périmé…),
  signalées par ⚠ dans l'écran Allocation.

La réponse expose aussi la liste des **critères appliqués** (`criteres`) pour
la transparence de la proposition.

## 5. Limites et évolutions

Le moteur actuel est **par règles** : transparent, explicable (chaque ligne
porte sa justification), déterministe. Les évolutions prévues (roadmap) :

- optimisation moyenne-variance (Markowitz) et parité de risque, qui
  nécessitent les **corrélations** entre actifs, donc les historiques de cours ;
- ~~simulateur~~ ✅ livré (`services/simulation.py`, écran Simulateur) :
  versements programmés, réinvestissement des dividendes, scénarios
  prudent/médian/optimiste et fiscalité PEA estimée ;
- comparaison allocation cible vs allocation réelle après import d'un
  portefeuille existant.

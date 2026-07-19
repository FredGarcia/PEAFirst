# Modèle de données

Base SQLite (`peadvisor.db`), ORM SQLAlchemy 2 (`peadvisor/models.py`).
Migration vers PostgreSQL possible en changeant l'URL de connexion
(`peadvisor/database.py`).

## Table `actifs` — référentiel des valeurs

Clé métier : **ISIN** (unique, indexé). C'est la clé du dédoublonnage.

| Groupe | Champs |
|---|---|
| Identité | `nom`, `isin`, `mnemonique`, `type` (ACTION / ETF / OPCVM), `marche`, `devise`, `pays`, `secteur` |
| Éligibilité | `eligible_pea`, `eligible_pea_pme` (poche optionnelle, activable dans settings.yaml) |
| Fonds | `societe_gestion` |
| Marché | `capitalisation` (M€), `cours`, `date_cours` |
| Indicateurs | `rendement` (%), `per`, `croissance` (%), `volatilite` (% annualisé), `niveau_risque` (1-7), `score_esg` (0-100), `objectif_cours`, `potentiel` (%), `consensus` (1-5) |
| Scores calculés | `score_global` (0-100), `sous_scores` (JSON des 7 sous-notes) |
| Traçabilité | `source`, `cree_le`, `maj_le` |

### Règles de gestion

- `potentiel` est **recalculé** à chaque scoring : `(objectif_cours / cours − 1) × 100`.
- `niveau_risque` : si absent (actions), il est **dérivé de la volatilité**
  (échelle type SRI 1-7) ; pour les fonds, le SRI du DIC est conservé tel quel.
- Un enregistrement importé est **rejeté** (et compté) si l'ISIN ne fait pas
  12 caractères, si le nom est vide ou si le type est inconnu.

## Table `historique_scores`

Une ligne par actif et par mise à jour : `actif_id`, `date`, `score_global`,
`cours`. Sert au suivi de l'évolution (écran détail / futur backtesting).

## Table `journal_maj` — journalisation des traitements

`date`, `traitement` (ex. `import:seed`), `statut` (succes / avertissement /
erreur), `detail`, `nb_crees`, `nb_maj`, `nb_doublons`, `nb_erreurs`.
Toute exécution d'import — manuelle ou planifiée — y écrit son résultat,
y compris les échecs (erreur réseau, source inconnue…).

## Table `watchlist`

`actif_id` (unique), `ajoute_le`, `commentaire`.

## Volumétrie cible

Le schéma est dimensionné pour la cible du cahier des charges (milliers
d'actions, centaines d'ETF/OPCVM) : index sur `isin`, `type`, `score_global` et
les dates. L'ajout des **historiques de cours** (roadmap : backtesting,
volatilité/Sharpe calculés) se fera par une table `historique_cours`
(`actif_id`, `date`, `cours`, `volume`) alimentée par les sources.

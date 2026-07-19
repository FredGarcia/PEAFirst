# Architecture

## Les 4 niveaux du cahier des charges

| Niveau | Fonction | Implémentation |
|---|---|---|
| **L1 — Collecte** | Import des données | `peadvisor/sources/` (connecteurs) + `services/importer.py` (normalisation, dédoublonnage) |
| **L2 — Analyse** | Indicateurs, scoring, ESG, risque | `services/scoring.py` (sous-notes 0-100, score global, niveau de risque dérivé de la volatilité) |
| **L3 — Décision** | Multicritère, allocation | `services/decision.py` (score pondéré, TOPSIS) + `services/allocation.py` |
| **L4 — Pilotage** | Tableau de bord, journal, watchlist | `routers/` (API REST) + `static/` (interface web) |
| **L5 — Second ordre** | Le système s'observe et s'améliore | `services/introspection.py` + `services/amelioration.py` (voir [docs/07-auto-observation.md](07-auto-observation.md)) |

## Flux de données

```
Source (seed / yahoo / …)
        │  recuperer()
        ▼
Normalisation ──► rejet des enregistrements invalides (journalisés)
        │
        ▼
Dédoublonnage par ISIN ──► existant ? mise à jour : création
        │
        ▼
Scoring (sous-notes + score global + historique)
        │
        ▼
┌───────┴────────────────────────────┐
▼                                    ▼
Tableau de bord / classements     Moteur d'allocation
(KPI, tops, TOPSIS)               (profil → portefeuille)
```

Chaque import écrit une ligne dans `journal_maj` (créés / mis à jour / doublons /
rejets, statut, détail), consultable dans l'écran **Historique**.

## Correspondance avec les modules du cahier des charges

| Module | Fonction | État |
|---|---|---|
| M1 | Collecte des données | ✅ sources branchables + import manuel/planifié |
| M2 | Normalisation et dédoublonnage | ✅ par ISIN, doublons intra-lot écartés |
| M3 | Indicateurs financiers | ✅ champs stockés + potentiel calculé ; ratios avancés (Sharpe, drawdown…) à venir avec les historiques de cours |
| M4 | Scores ESG et risque | ✅ ESG 0-100, niveau 1-7 (SRI fourni ou dérivé de la volatilité) |
| M5 | Moteur de décision multicritère | ✅ score pondéré + TOPSIS (AHP/PROMETHEE/ELECTRE : extension prévue, même signature) |
| M6 | Optimisation de portefeuille | ✅ allocation par poches et contraintes (optimisation type Markowitz : roadmap) |
| M7 | Tableau de bord | ✅ opérationnel |
| M8 | Simulateur d'investissement | ⏳ roadmap |
| M9 | Watchlist et alertes | ✅ watchlist ; alertes : roadmap |
| M10 | Rapports et exports | ⏳ roadmap (Excel/CSV/PDF) |
| M11 | Paramétrage | ✅ YAML + écran Paramètres (pondérations) |
| M12 | Journalisation et audit | ✅ journal des traitements + historique des scores |

## API REST (extraits)

| Méthode | Route | Rôle |
|---|---|---|
| GET | `/api/dashboard/synthese` | KPI, répartitions, tops |
| GET | `/api/dashboard/classement?methode=topsis` | Matrice de décision multicritère |
| GET | `/api/actifs?type=ETF&tri=score_global` | Liste filtrée/triée |
| GET | `/api/actifs/{isin}` (+ `/sous-scores`, `/historique`) | Détail d'un actif |
| POST | `/api/allocation` | Proposition d'allocation |
| POST | `/api/import` | Import manuel |
| POST | `/api/scores/recalculer` | Recalcul des scores |
| GET/PUT | `/api/parametres/scoring` | Pondérations du score |
| GET/POST/DELETE | `/api/watchlist[/{isin}]` | Watchlist |
| GET | `/api/journal` | Journal des traitements |

La documentation interactive complète est sur `/docs` (Swagger généré).

## Automatisation

`services/scheduler.py` démarre avec l'application si
`mise_a_jour.automatique: true` dans `config/settings.yaml` : import complet +
rescoring chaque jour (ou chaque lundi) à l'heure configurée, résultat
journalisé même en cas d'erreur (gestion des exceptions réseau/quota dans
l'importeur).

# Choix technologiques

Le cahier des charges demandait de retenir « la technologie la mieux adaptée ».
Voici les choix retenus et leur justification.

## Synthèse

| Besoin | Choix | Raison principale |
| --- | --- | --- |
| Langage | **Python 3.11+** | Écosystème financier et data inégalé (pandas, numpy, yfinance…), lisible et maintenable |
| API / serveur | **FastAPI + Uvicorn** | API REST typée, documentation Swagger générée automatiquement (exigence « API REST » de la roadmap couverte dès le départ) |
| Base de données | **SQLite + SQLAlchemy 2** | Base relationnelle sans serveur ni administration ; l'ORM permet de migrer vers PostgreSQL en changeant une ligne de configuration |
| Frontend | **HTML/CSS/JS natif** servi par FastAPI | Zéro dépendance, zéro build, fonctionne hors-ligne ; suffisant pour un tableau de bord décisionnel mono-utilisateur |
| Planification | **APScheduler** | Mises à jour quotidiennes/hebdomadaires dans le processus applicatif, sans cron système |
| Paramétrage | **YAML** (`config/`) | Modifiable sans toucher au code, versionnable, lisible |
| Tests | **pytest** | Standard de fait, fixtures simples (base en mémoire) |

## Alternatives écartées

### Google Sheets + Apps Script

Envisagé dans le cahier des charges (§13). Écarté car :

- volumétrie cible (« plusieurs milliers d'actions, historiques de cours ») au-delà
  de ce qu'un tableur gère confortablement ;

- les moteurs prévus (TOPSIS, optimisation de portefeuille, backtesting) sont
  pénibles à écrire et à tester en Apps Script, triviaux en Python ;

- quotas d'exécution Apps Script (6 min/exécution) incompatibles avec une mise à
  jour complète ;

- pas de vraie base relationnelle, pas de tests unitaires sérieux.

L'export vers Excel/CSV reste prévu dans la roadmap pour retrouver le confort du
tableur côté consultation.

### Framework frontend (React/Vue) + build

Écarté à ce stade : le tableau de bord est un ensemble d'écrans de consultation
et deux formulaires. Un SPA « vanilla » de ~300 lignes évite Node, npm et la
maintenance d'une chaîne de build. Si l'interface se complexifie (drag & drop,
graphiques interactifs riches), la migration est possible sans toucher au
backend puisque tout passe déjà par l'API REST.

### Base PostgreSQL immédiate

Inutile en mono-utilisateur local. SQLAlchemy rend la migration transparente le
jour où l'application devient multi-utilisateurs (roadmap : authentification).

## Données de marché

Le connecteur est **abstrait** (`peadvisor/sources/base.py`) : chaque source
implémente une seule méthode `recuperer()`. Deux sources sont livrées :

- **`seed`** (par défaut) : jeu local de 32 valeurs représentatives, données
  **illustratives** — permet de développer, tester et démontrer sans réseau ;

- **`yahoo`** : enrichissement des cours/PER/objectifs via `yfinance`
  (bibliothèque non officielle : robustesse au mieux, repli automatique sur la
  fiche locale en cas d'erreur ou de quota).

Pour la cible « plusieurs milliers de valeurs avec historiques », il faudra une
source de qualité professionnelle (EOD Historical Data, Euronext, Morningstar…),
à brancher en ajoutant un module dans `peadvisor/sources/` et une entrée dans le
`REGISTRE` — sans toucher au reste du code.

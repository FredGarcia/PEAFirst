# Sources de données — état et étude comparative

## 1. Sources intégrées

Huit sources sont branchées dans le `REGISTRE` (`peadvisor/sources/`). Toutes
alimentent les fiches **et les historiques de cours** (moteur quantitatif),
avec repli sur la fiche locale en cas d'erreur ou de quota. Les clés se
déclarent dans `config/cles_api.yaml` (copier `cles_api.exemple.yaml`, jamais
versionné) ou par variable d'environnement (**prioritaire**), et se vérifient
via le bouton « Tester » de l'écran Sources.

| Source | Clé | Offre gratuite | Couverture PEA | Notes |
|---|---|---|---|---|
| `seed` | non | — | démo | Jeu local illustratif + séries synthétiques |
| **`stooq`** | **non** | **illimitée (usage raisonnable)** | Paris (suffixe `.fr`) | **La plus simple à activer** : historiques EOD réels, CSV, sans inscription |
| `yahoo` | non | oui (non officiel) | large | Via yfinance : pratique mais fragile (pas d'API contractuelle) |
| `alphavantage` | oui | ~25 req/jour, 5/min | Euronext (`.PAR`) | Quota gratuit trop faible pour un import complet : tests seulement |
| `twelvedata` | oui | 800 req/jour, 8/min | bonne (MIC `XPAR`) | Bon compromis gratuit (import complet en ~2 passes) |
| `financialmodelingprep` | oui | ~250 req/jour | correcte (`.PA`) | Le plus riche en fondamentaux (PER, capitalisation, objectif de cours) |
| `eodhd` | oui | ~20 req/jour ; payant abordable | **excellente** (actions + fonds EU) | Meilleur candidat payant pour la cible « milliers de valeurs » |
| `marketstack` | oui | ~100 req/mois | correcte (MIC `.XPAR`) | Gratuit trop limité ; EOD uniquement |

Recommandation pratique : **`stooq` gratuitement dès aujourd'hui** (cours et
historiques réels, sans clé), `twelvedata` en complément gratuit avec clé,
et **`eodhd` en payant** le jour du passage à l'échelle (référentiel complet
des valeurs éligibles PEA, OPCVM compris).

⚠️ Les formats de symboles (suffixes `.PA`, `.PAR`, `.XPAR`, `.fr`, MIC…)
sont centralisés dans la méthode `symbole()` de chaque connecteur — c'est le
premier endroit à ajuster si le bouton « Tester » renvoie une réponse vide.

## 2. Sources évaluées et écartées (pour l'instant)

### API sérieuses mais peu adaptées au PEA

| Source | Raison |
|---|---|
| Polygon.io | Excellente API mais couverture actions **US uniquement** — inutilisable pour un univers PEA |
| Alpaca Market Data | Données de courtage **US** |
| Tradier API | Courtage **US** |
| Tiingo | Sérieux et bon marché, mais couverture surtout US ; Europe lacunaire |
| Finnhub | Temps réel séduisant ; en gratuit, fondamentaux et historiques EU très restreints |
| Intrinio | Qualité institutionnelle, tarification entreprise — surdimensionné ici |
| Nasdaq Data Link (ex Quandl) | Plateforme de *datasets* ; plus de flux gratuit de cours EU depuis l'arrêt de WIKI |
| Benzinga API | Orienté **actualités**, payant — pas un fournisseur de cours |
| IEX Cloud | **Service fermé en 2024** — à rayer de la liste |
| FinancialData.io, StockData.org, Finnworlds, Financial Edge, Finnove, Webull API | Petits agrégateurs ou API non officielles : couverture EU incertaine, pérennité douteuse — aucun avantage sur les sources intégrées |

### Sites sans API officielle (scraping exclu)

Investing.com, Boursorama, TradingView, Google Finance, Macrotrends : pas
d'API publique — y accéder supposerait du *scraping*, contraire à leurs CGU
et structurellement fragile (chaque refonte du site casse l'import). Écartés
par principe : le cahier des charges exige des « sources autorisées ».
TradingView propose bien une offre broker/charting, mais pas de flux de
données licencié pour ce cas d'usage.

### Compléments utiles (autres rôles que les cours)

| Source | Rôle pertinent pour PEAdvisor |
|---|---|
| **OpenFIGI** | Gratuit : correspondance **ISIN → ticker/place**. Très utile le jour du référentiel complet (résoudre automatiquement les symboles par source) — candidat sérieux pour un module « référentiel » |
| **FRED** (Federal Reserve) | Séries macro gratuites : pourrait alimenter automatiquement le `taux_sans_risque_pct` (Sharpe/Sortino) et de futurs indicateurs de contexte |
| SEC EDGAR | Fondamentaux officiels mais **émetteurs US** — hors périmètre PEA |

## 3. Ajouter une source

1. Créer `peadvisor/sources/<nom>.py` héritant de `SourceHTTPBase` :
   implémenter `symbole()`, `cotation()` et/ou `serie()` (~30 lignes, voir
   `stooq.py` pour le cas minimal).
2. L'enregistrer dans `REGISTRE` (`sources/__init__.py`).
3. Si clé : ajouter `nom_cle`/`variable_env` + une ligne dans
   `config/cles_api.exemple.yaml`.
4. Ajouter un test de parsing dans `tests/test_sources_http.py` (réponses
   simulées — aucun réseau en test).

Le bouton « Tester » de l'écran Sources fonctionne alors automatiquement.

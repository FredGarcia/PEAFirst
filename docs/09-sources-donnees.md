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
| **OpenFIGI** | Gratuit : correspondance **ISIN → ticker/place**. Très utile le jour du référentiel complet (résoudre automatiquement les symboles par source) — candidat sérieux pour un module « référentiel ». ⚠️ **V2 fermée le 1er juillet 2026 (HTTP 410) : viser directement l'API V3** |
| **FRED** (Federal Reserve) | Séries macro gratuites (clé requise) : rendements souverains, y compris séries internationales (ex. `IRLTLT01FRM156N`, taux long français). Alternative à la BCE pour le taux sans risque |
| SEC EDGAR | Fondamentaux officiels mais **émetteurs US** — hors périmètre PEA |

## 3. Sources trouvées au-delà de la liste (nouvelles pistes)

Recherche complémentaire, orientée vers les **manques réels** de PEAdvisor
(univers PEA complet, OPCVM français, taux/devises), avec une priorité aux
sources **institutionnelles, gratuites et sans clé**.

| Source | Rôle | Clé | Intérêt pour PEAdvisor |
|---|---|---|---|
| **BCE — ECB Data Portal (SDMX)** ✅ intégré | Taux zone euro + change | **non** | **Taux sans risque** (rendement 10 ans AAA) pour Sharpe/Sortino et **taux de change** EUR — voir moteur macro ci-dessous |
| **Frankfurter** | Taux de change | **non** | Alternative légère à la BCE pour le change (données BCE reconditionnées en JSON, sans clé) |
| **AMF GECO** | VL des OPCVM français | non (web/open data) | **Comble le trou OPCVM** : les fonds ne sont cotés sur aucune API boursière. Base officielle de l'Autorité des marchés financiers, recherche par ISIN. Accès surtout web ; jeux partiels sur data.gouv.fr — un connecteur demanderait de fiabiliser l'accès programmatique |
| **Euronext — Web Services / post-trade différé** | Cours Euronext officiels | licence | Données de la place elle-même (différé 15 min gratuit, temps réel sous licence) : la source de référence pour l'univers Paris à terme |
| **Deutsche Börse / Boerse Frankfurt** | Cours EU | partiel | Complément pour les valeurs cotées en Allemagne |
| **justETF** | Référentiel ETF (TER, indices, encours) | API non officielle | Riche sur les ETF européens, mais **pas d'API publique documentée** (seulement des wrappers non officiels / scraping) : à éviter en production |

Restent écartées pour les mêmes raisons qu'en §2 : Investing.com, Boursorama,
TradingView, Google Finance, Macrotrends (pas d'API publique → scraping exclu),
et les fournisseurs US-centrés (Polygon, Alpaca, Tradier, Tiingo, SEC EDGAR).

### Moteur macro (BCE) — intégré

`peadvisor/services/macro.py` interroge le portail SDMX de la BCE (CSV, **sans
clé**) pour :

- le **taux sans risque** de la zone euro (rendement 10 ans des emprunts AAA),
  qui alimente désormais les ratios de Sharpe et de Sortino — activable par
  `macro.taux_sans_risque_source: bce` dans `config/settings.yaml` (défaut
  `fixe` : la valeur `quantitatif.taux_sans_risque_pct`, garantie hors-ligne) ;
- les **taux de change** face à l'euro (`taux_change()`), pour de futures
  conversions d'actifs libellés hors EUR.

Exposé via `GET /api/dashboard/taux-sans-risque` et l'outil MCP
`taux_sans_risque`. Repli automatique sur la valeur paramétrée si la BCE est
injoignable — aucune régression hors ligne.

## 3 bis. Diagnostic des tests (retours réels)

Le bouton « Tester » affiche désormais le **message réel de l'API** (et non un
code HTTP nu), avec une aide selon le code : 402 = donnée payante, 403 =
exchange hors offre gratuite, 404 = symbole introuvable pour ce plan, 429 =
quota. Verdict par source d'après les essais :

| Source | Résultat type | Cause / action |
|---|---|---|
| **alphavantage** | ✅ OK (~100 pts) | Fonctionne (suffixe `.PAR`). Quota gratuit faible. |
| **eodhd** | ✅ OK (~250 pts) | Fonctionne (`.PA`). Le meilleur candidat payant. |
| **marketstack** | ✅ OK (~240 pts) | Fonctionne (`.XPAR`). |
| **stooq** | 404 → **corrigé** | Le serveur bloquait `python-requests` : ajout d'un User-Agent navigateur. Couverture des actions FR incertaine (fort sur indices/US/DE) → repli propre si absent. |
| **financialmodelingprep** | 402 payant → **atténué** | Bascule sur l'API gratuite v3 ; mais l'offre gratuite FMP reste **quasi limitée aux valeurs US** — Euronext peut rester 402/403. |
| **twelvedata** | 404 | Le message d'erreur (désormais affiché) précise si XPAR est **hors offre gratuite** : le plan gratuit TwelveData ne couvre que les actions US. Nécessite un plan payant pour Euronext. |
| **finnhub** | 403 | Offre gratuite **US uniquement** ; Euronext hors périmètre — inadapté au PEA. |
| **polygon** | 400 | Polygon **ne cote aucune action Euronext** (US stocks/options/forex/crypto). À retirer pour le PEA. |
| **tiingo** | 404 | Couverture actions surtout US ; Euronext non servi. Inadapté au PEA. |
| **openfigi** | vide → **rôle corrigé** | Ce n'est **pas une source de cours** mais un annuaire ISIN→ticker (POST /v3/mapping). Déplacé dans `services/reference.py` (`GET /api/reference/figi/{isin}`, outil MCP `resoudre_isin`). |

**Conclusion** : pour le PEA, s'appuyer sur **EODHD / Marketstack / AlphaVantage**
(qui fonctionnent) et **stooq** (gratuit, sans clé, sous réserve de couverture) ;
retirer finnhub, polygon et tiingo (US-centrés) ; garder OpenFIGI comme
annuaire, pas comme flux de cours.

## 3 ter. Scraping Boursorama

Faute d'API officielle utilisable pour Euronext en gratuit, un connecteur de
*scraping* Boursorama est fourni (`peadvisor/sources/boursorama.py`).

⚠️ **Le scraping est fragile et sensible aux conditions d'utilisation** : il
dépend de la structure HTML des pages (une refonte peut le casser) et relève
d'un usage personnel. Pour limiter la casse, toute l'analyse est isolée dans
la **fonction pure `parser_page(html)`**, entièrement testée — si la page
change, seules les expressions d'extraction (et le dictionnaire `ETIQUETTES`)
sont à ajuster, sans toucher au reste.

Points clés :

- **Code Boursorama** = préfixe de place + mnémonique ; Euronext Paris = `1rP`
  (Air Liquide `1rPAI`, TotalEnergies `1rPTTE`). Exceptions dans `CODES`.
- **En-tête navigateur** obligatoire (comme stooq, Boursorama refuse
  `python-requests`).
- **Colonnes extraites** (validées sur une page réelle) : nom, ISIN, secteur,
  cours, devise, variation du jour, ouverture / +haut / +bas / clôture veille,
  volume, valorisation (capitalisation), PER et rendement estimés, **objectif
  de cours 3 mois**, **potentiel**, **risque ESG**, **consensus analystes**.
- **Deux conversions de convention** (documentées et testées) :
  - *Risque ESG* Boursorama (Sustainalytics, plus bas = mieux, ex. 12,7) →
    **score ESG** PEAdvisor (0-100, plus haut = mieux) : `score = 100 − risque`.
  - *Consensus* Boursorama (échelle 1 = achat … 5 = vente, ex. 1,55) →
    **consensus** PEAdvisor (1 = vente … 5 = achat fort) : `6 − valeur`.
- **Cours en direct** : rempli par JavaScript, donc absent du HTML statique →
  repli automatique sur la **clôture veille**.
- **Historique** : cette page ne le fournit pas → indicateurs quantitatifs
  (volatilité, Sharpe…) toujours issus d'une source EOD (EODHD, Marketstack…).

Utilisation — **ajout à la demande par nom, ISIN ou code** :

- Onglet Actions : champ « Ajouter une valeur (nom, ISIN ou code) » →
  « Rechercher & ajouter » ; la recherche Boursorama résout le code
  automatiquement (« Air Liquide » ou « FR0000120073 » → `1rPAI`).
- `POST /api/import/boursorama/{nom|isin|code}` ou l'outil MCP
  `importer_boursorama`. La ligne est créée/mise à jour, **Source =
  boursorama**, et la réponse expose tous les indicateurs extraits
  (`donnees_extraites`).
- **Tout l'univers** : `donnees.source_active: boursorama` (une requête par
  valeur, pause d'une seconde — courtois mais lent).

La fonction `parser_page` est validée par test contre la structure réelle
(`tests/fixtures_boursorama.py`) : objectif 190,46, potentiel 7,18 %, risque
ESG 12,7, consensus 1,55, PER 27,6, rendement 2,01 %, valorisation 113 401 M€.

L'onglet Actions affiche désormais la **variation du jour**, le **volume** et
une colonne **Source** indiquant l'origine de chaque ligne.

## 3 quater. Scraping multi-sources (framework)

Plusieurs sites peuvent être scrapés via un registre commun
(`peadvisor/sources/web.py`). Chaque source est un `Scraper` : soit **validé**
avec son parseur dédié (Boursorama), soit **best-effort** piloté par
configuration (URL de recherche + motif de lien + `parser_generique`), à
fiabiliser dès qu'une page exemple est fournie.

| Source | État | Notes |
|---|---|---|
| **Boursorama** | ✅ validé | Parseur dédié, indicateurs riches (objectif, potentiel, ESG, consensus) |
| Boursier, Zonebourse, Bourse Direct, Ouest-France, Euronext Paris | ⚠️ à valider | Branchées avec un parseur générique (nom, ISIN, cours) — envoyer une page exemple de chacune pour un parseur dédié, comme pour Boursorama |

Dans l'onglet **Actions** : un champ « nom, ISIN ou code » + **un bouton par
source**. Les sources non validées portent un « * » ; en cas d'extraction
pauvre, le message indique qu'un parseur dédié est nécessaire (envoyer une
page). API : `GET /api/sources/scrapers` (liste), `POST /api/import/web/
{source}/{requête}` (import). Outil MCP : `importer_valeur(requete, source)`.

Ajouter/fiabiliser une source = ~15 lignes : une entrée dans `SCRAPERS` et,
après examen d'une vraie page, une fonction `parser_page` dédiée (le chemin
suivi pour Boursorama, cf. `tests/fixtures_boursorama.py`).

## 3 quinquies. Recherche, ventilation et tableaux de valeurs

**Recherche (API indépendante `/api/recherche`)** — partagée par les onglets
Actions / ETF / OPCVM : saisir un nom, un ISIN ou un code, choisir la source
(un bouton par source). Le service :
- **détecte le type d'instrument** (depuis le `<title>` Boursorama : « Cours
  Action / Tracker / OPCVM ») et **ventile** la valeur dans le bon onglet ;
- **vérifie l'éligibilité PEA** (marqueur `eligible-pea` de la fiche) ; si non
  confirmée, **rien n'est enregistré** : une **fenêtre modale** décrit la cause
  et propose « Ajouter quand même » (`?confirmer=true`). Toute autre erreur
  (ISIN introuvable, réseau…) ouvre aussi une modale décrivant la cause ;
- un bouton **« ↻ Réactualiser le tableau »** re-scrape toutes les valeurs de
  l'onglet depuis leur source et recalcule les scores
  (`POST /api/actifs/reactualiser`).

**Champs Boursorama étendus** (parseur enrichi, `parser_page`) : ouverture,
+haut/+bas, clôture veille, 52 semaines haut/bas, volume, quantité échangée,
valorisation, nombre de titres, PER, rendement, BNA, dividende, taux de
distribution, dette nette, CA, objectif de cours, potentiel, consensus,
nombre d'analystes, risque ESG. L'**objectif de cours** gère le séparateur de
milliers (« 1 366,50 EUR »), le champ « dernier échange » est scindé en
**date + heure de cotation**, et les fondamentaux d'une **table « chiffres
clés »** (BNA, rendement…) sont récupérés hors de la liste principale. Le cours
« live » (attribut vide en HTML statique) est lu dans le **texte** de
l'élément, avec repli sur la clôture veille.

**Tableaux (Actions / ETF / OPCVM, même composant)** :
- **tri** par colonne (▴/▾) ; **suppression** d'une ligne (🗑, `DELETE
  /api/actifs/{isin}`) ; **en-tête figé** au défilement vertical ;
- **pleine largeur** disponible (colonnes ajustées) et **colonnes Nom / ISIN /
  Secteur figées** au défilement **horizontal** ;
- la colonne **Source** est un **lien** (nom de la source → fiche de l'ISIN) ;
- **entêtes propres à chaque tableau** : le jeu de colonnes visibles se choisit
  par onglet (Paramètres → « Colonnes », avec **« Tout sélectionner »** et
  **« Réinitialiser »**). Le tableau **Actions** est aligné par défaut sur
  `CHAMPS_FICHE` (et ses préfixes) : nom, ISIN, secteur, cours, devise,
  date/heure, variation, ouverture, +haut/+bas, clôture veille, 52 s haut/bas,
  volume, quantité échangée, capitalisation, nombre de titres, PER, rendement,
  BNA, dividende, taux de distribution, dette nette, CA, objectif, potentiel,
  consensus, nombre d'analystes, ESG, risque ESG, éligibilité PEA, source
  (+ score global). ETF / OPCVM ont un jeu par défaut plus resserré ;
- **couleur d'en-tête paramétrable par onglet** (Paramètres → Apparence) ;
- **données de démonstration** : bouton « Charger » sur la ligne `seed`
  (onglet Sources) et bascule « Masquer / Afficher (seed) ».

**Test des sources** — bouton « Tester » sur chaque ligne (onglet Sources) :
récupère la **page exemple** de la source (URL paramétrable par source dans
Paramètres → « Sources ») et affiche un **extrait JSON** ; si la réponse n'est
pas du JSON (HTML, CSV), un **extrait texte** ; en cas d'échec, la **cause en
texte**. À défaut d'URL exemple, une source HTTP est testée via son API
(présence de clé, appel réel).

**Barre latérale** ajustable : glisser la poignée (double flèche) à droite, ou
régler la **largeur en pixels** dans Paramètres → Apparence (persistée dans le
profil, `largeur_barre`).

## 4. Ajouter une source

1. Créer `peadvisor/sources/<nom>.py` héritant de `SourceHTTPBase` :
   implémenter `symbole()`, `cotation()` et/ou `serie()` (~30 lignes, voir
   `stooq.py` pour le cas minimal).
2. L'enregistrer dans `REGISTRE` (`sources/__init__.py`).
3. Si clé : ajouter `nom_cle`/`variable_env` + une ligne dans
   `config/cles_api.exemple.yaml`.
4. Ajouter un test de parsing dans `tests/test_sources_http.py` (réponses
   simulées — aucun réseau en test).

Le bouton « Tester » de l'écran Sources fonctionne alors automatiquement.

# PEAFirst — Base ISIN

Base d'identifiants ISIN pour le projet PEA Advisor, construite depuis les listes officielles Euronext (toutes places : Paris, Amsterdam, Bruxelles, Lisbonne, Oslo, Milan, Dublin…).

## Fichiers

| Fichier | Contenu |
|---|---|
| `data/base_isin.csv` | Base consolidée dédoublonnée (6 188 ISIN) |
| `data/base_isin_actions.csv` | Actions (2 798) |
| `data/base_isin_etf.csv` | ETF (3 232) |
| `data/base_isin_opcvm.csv` | OPCVM (158) |
| `data/base_isin_fonds_pea.csv` | ETF + OPCVM enrichis de l'éligibilité PEA fiabilisée (3 390) |
| `data/pea_emetteurs.csv` | Référence d'éligibilité vérifiée auprès des émetteurs (fait autorité) |
| `data/openfigi_cache.csv` | Cache OpenFIGI (créé par `scripts/enrich_openfigi.py`) |

## Colonnes

`ISIN;Nom;Symbole;Type;Marché(s);Devise;Pays_émission;PEA_indicatif;ESG_classification;Source;Date_MAJ`

- Séparateur : `;` — encodage UTF-8.
- Les multi-cotations sont agrégées dans `Marché(s)` (séparateur ` | `).

## Éligibilité PEA (`PEA_indicatif`)

Règle par préfixe pays de l'ISIN (UE/EEE incluant NO, IS, LI) :
- **Actions** : règle fiable (siège dans l'EEE).
- **ETF/OPCVM** : indicatif seulement. Un fonds domicilié IE/LU n'est éligible PEA que s'il respecte le quota de 75 % d'actions UE (réplication physique ou synthétique). Un enrichissement dédié est nécessaire pour fiabiliser cette colonne.

## Éligibilité PEA fiabilisée (`data/base_isin_fonds_pea.csv`)

> **Il n'existe aucune liste officielle des ETF éligibles au PEA.** Ni l'AMF, ni
> l'administration fiscale, ni Euronext n'en publient. L'éligibilité est un
> engagement pris par la société de gestion dans le prospectus du fonds, sous sa
> responsabilité. La seule source qui fait foi est donc **la fiche produit de
> l'émetteur**, à une date donnée. `data/pea_emetteurs.csv` matérialise ce
> relevé, avec la source et la date de vérification de chaque entrée.
>
> Deux niveaux de fiabilité y coexistent, tracés dans la colonne `Source` :
> relevé direct sur la documentation de l'émetteur (le plus fort), ou relevé
> secondaire à reconfirmer sur la fiche émetteur avant tout usage décisionnel.

Produit par `scripts/enrich_pea.py`, qui croise par priorité décroissante :

1. **`data/pea_emetteurs.csv`** — liste vérifiée auprès des émetteurs (fait autorité, `LISTE_EMETTEUR`) ;
2. domicile hors EEE → `NON` (`HORS_EEE`) ;
3. marquage « PEA » dans le nom émetteur → `OUI` (`NOM_PEA`) ;
4. classe d'actifs incompatible (obligataire, monétaire, crypto, matières premières) → `NON` (`CLASSE_ACTIFS`) ;
5. indice actions européen + domicile EEE → `PROBABLE` (`INDICE_EUROPEEN`) ;
6. reste → `A_VERIFIER` (fonds EEE sur indices monde/US/EM sans marquage PEA).

Colonnes ajoutées : `PEA_eligible` (`OUI` | `PROBABLE` | `NON` | `A_VERIFIER`), `PEA_methode`, `PEA_source`.

Pour réduire le stock `A_VERIFIER` : exécuter `scripts/enrich_openfigi.py` (noms complets décodant les libellés techniques Euronext) et fusionner les listes émetteurs via `scripts/maj_pea_emetteurs.py`.

## Scripts

| Script | Rôle |
|---|---|
| `scripts/validate_base.py` | Validation automatique : checksums ISIN, doublons, cohérence inter-fichiers, règle EEE, fichiers enrichis. Code retour ≠ 0 en cas d'erreur. |
| `scripts/enrich_pea.py` | Classement de l'éligibilité PEA des fonds (règles + listes émetteurs + noms OpenFIGI). Hors-ligne. |
| `scripts/enrich_openfigi.py` | FIGI, ticker et nom complet via l'API OpenFIGI (cache incrémental, reprise ; nécessite le réseau, clé gratuite optionnelle `OPENFIGI_API_KEY`). |
| `scripts/maj_pea_emetteurs.py` | Fusion des listes d'éligibilité téléchargées chez les émetteurs (Amundi, iShares, BNP…) dans `data/pea_emetteurs.csv`, avec traçabilité source/date. |

Chaîne complète : `enrich_openfigi.py` → `maj_pea_emetteurs.py --merge …` → `enrich_pea.py` → `validate_base.py`.

## Intégration continue

`.github/workflows/validate.yml` s'exécute sur chaque pull request et sur les push vers `main` :

1. `validate_base.py` sur la base livrée ;
2. régénération du classement PEA et échec si `data/base_isin_fonds_pea.csv` n'est pas à jour (garde-fou contre une modification de `pea_emetteurs.csv` ou des règles sans régénération) ;
3. nouvelle validation après régénération.

Aucune dépendance à installer, aucun accès réseau requis — l'étape OpenFIGI reste manuelle.

## Données de marché et indicateurs (`data/base_isin_marche.csv`)

Produit par `scripts/enrich_marche.py` : cours de clôture, puis volatilité
annualisée, drawdown maximal, Sharpe et Sortino (252 séances/an, taux sans
risque paramétrable via `--taux-sans-risque`).

Quotas constatés sur comptes gratuits (août 2026) — ils dictent la stratégie :

| Source | Quota | Couverture Euronext | Usage |
|---|---|---|---|
| EODHD | 20 requêtes/**jour** | Paris, Amsterdam, Bruxelles, Lisbonne, Oslo, Milan, Dublin | `--historique` (défaut) |
| Marketstack | 100 requêtes/**mois**, lots de 50 | Paris, Amsterdam, Bruxelles, Lisbonne — grandes capitalisations seulement | `--cours` en masse |
| Alpha Vantage | 25 requêtes/jour | partielle | repli |
| FMP, Finnhub, Tiingo, Polygon | — | **aucune** en gratuit (US uniquement) | réservés au CTO |

Conséquence : enrichir les 6 188 instruments d'un coup est hors de portée en
gratuit. Le script travaille donc par sous-ensemble priorisé
(`--filtre pea|actions|etf`, `--limite`) et reprend où il s'est arrêté grâce à
`data/marche_cache.json` (non versionné). Les symboles absents du fournisseur
sont marqués une fois pour toutes et ne sont plus réinterrogés.

```bash
export EODHD_API_KEY=...
python3 scripts/enrich_marche.py --etat                        # avancement
python3 scripts/enrich_marche.py --historique --filtre pea --limite 15
```

**Aucune de ces sources ne fournit l'éligibilité PEA** : elle vient uniquement
de `pea_emetteurs.csv`.

## Score propriétaire (`data/base_isin_scores.csv`)

`scripts/scoring.py` calcule un score sur 100 par rang percentile au sein de la
population comparable (même `Type`), avec des pondérations lues dans
`data/scoring_params.json` et modifiables sans toucher au code.
`scripts/scoring.gs` en est la transposition pour Apps Script : module
générique, sans référence d'enveloppe, à appeler depuis un `config.gs`.

Deux garde-fous, parce qu'un score global tiré d'un seul critère induirait en
erreur : au moins **2 critères notés** et **30 % du barème couvert**. En deçà,
l'instrument n'est pas noté — il n'est jamais noté zéro, ce qui le ferait
apparaître comme mauvais alors qu'il est seulement non documenté. La colonne
`Couverture_pct` accompagne chaque score : à 60 %, il classe sur le risque et
la performance passée, pas sur la valorisation ni les perspectives.

Critères alimentables aujourd'hui (sources gratuites) : performance,
volatilité, Sharpe, Sortino, drawdown, et ESG partiel (classification SFDR
art. 8/9, ETF seulement). Les critères du CDC sans source gratuite en Europe
— potentiel, valorisation, croissance, dividende, consensus — sont déjà
déclarés dans les pondérations : ils entreront dans le score dès qu'une source
les alimentera, sans modification du code.

## Allocation (`scripts/allocation.py`, `scripts/allocation.gs`)

Répartit un capital selon les quatre entrées du CDC : capital, horizon, profil
de risque (1 à 7) et objectif. Le profil suit les bornes de volatilité de
**PRIIPS (indicateur SRI)**, donc comparables à celles des documents
d'information des fonds. Un horizon court resserre automatiquement le plafond
de volatilité, et le poids maximal par ligne dépend du profil.

```bash
python3 scripts/allocation.py --capital 10000 --risque 5 --horizon 10 \
    --objectif croissance --pea-uniquement
```

Deux limites assumées, affichées à chaque exécution plutôt que masquées :

- **les corrélations ne sont pas modélisées** : la volatilité annoncée est une
  moyenne pondérée, donc un *majorant* du risque réel d'un portefeuille
  diversifié. Elle sert à comparer des allocations, pas à prédire le risque ;
- **l'objectif « revenus » ne peut pas être servi** faute de source gratuite
  sur les dividendes européens. La sélection privilégie alors la régularité,
  et le script le dit explicitement.

Si aucun instrument ne respecte la contrainte, le moteur ne force pas une
allocation : il l'indique et propose d'élargir l'univers ou de relever le profil.

## Tableau de bord (`data/dashboard.html`)

`scripts/dashboard.py` produit une page autonome, consultable hors ligne et
régénérée à chaque collecte.

**Bandeau de fraîcheur** en tête : date de génération, dernière mise à jour de
la base, cours le plus récent, cours le plus ancien et nombre de cours périmés
(seuil réglable via `--seuil-fraicheur`, 7 jours par défaut). L'âge est aussi
affiché par ligne et mis en évidence au-delà du seuil : un cours de trois mois
n'a pas la valeur d'un cours de la veille.

**Explorateur** sur les 6 188 instruments : recherche, filtres (nature, pays,
éligibilité PEA, état des données), tri par clic sur n'importe quelle colonne,
et regroupement par nature, pays, éligibilité ou état. Chaque ligne porte son
état — *noté*, *collecté* ou *en attente* — ce qui rend l'avancement de la
collecte lisible instrument par instrument.

**Constitution de lots** : cocher des lignes (ou « tout sélectionner », qui
porte sur l'ensemble du filtre courant et non sur la seule page) produit soit
une commande à copier, soit une file d'attente à télécharger. Les scripts la
consomment ensuite :

```bash
python3 scripts/enrich_marche.py --historique --isins FR0000120073,BE0974293251
python3 scripts/enrich_marche.py --historique --file-attente data/file_attente.txt
```

La page **n'embarque aucune clé d'API** et n'appelle donc aucune source
directement : elle est versionnée sur GitHub, où une clé serait publiquement
exposée. Elle prépare les lots, le script les exécute.

**Progression de la collecte** : trois courbes (instruments notés, couverture
moyenne, cours périmés) alimentées par `scripts/historique.py`. Une courbe qui
stagne signale un quota épuisé ou un workflow en échec — ce qu'aucun score ne
montrerait. `--reconstruire` amorce la série depuis l'historique Git plutôt que
de la faire démarrer aujourd'hui ; il ne fabrique aucune donnée, il relit des
états déjà commités.

**Comparateur** : sélectionner 2 à 5 instruments affiche leurs indicateurs côte
à côte, la meilleure valeur de chaque ligne mise en évidence — sauf quand toutes
sont identiques, où surligner n'apprendrait rien.

**Anomalies** (`scripts/anomalies.py`) : série trop courte, volatilité extrême
ou quasi nulle, Sharpe aberrant, drawdown incohérent avec la volatilité,
performance extrême, cours périmé, couverture faible. Un indicateur
spectaculaire est plus souvent le symptôme d'une donnée douteuse que d'une
opportunité. Les instruments concernés portent un marqueur dans l'explorateur ;
ces signalements demandent une vérification, ils ne disqualifient pas
l'instrument.

Le reste réunit les indicateurs du CDC alimentables — répartitions, éligibilité
PEA, diversification, meilleurs scores — la **matrice multicritère TOPSIS**, et
la liste des indicateurs prévus mais sans source, avec leur motif. Une case vide
passerait pour un oubli ; un motif affiché est un constat.

```bash
python3 scripts/dashboard.py --top 12 --seuil-fraicheur 7
```

## Collecte automatisée

`.github/workflows/collecte-marche.yml` collecte chaque jour ouvré (06h15 UTC)
un lot d'instruments, recalcule les scores et publie le résultat. Le quota
gratuit EODHD étant de 20 requêtes/jour, l'univers se construit progressivement ;
`data/marche_cache.json` est versionné pour que chaque exécution reprenne où la
précédente s'est arrêtée.

**Prérequis** : ajouter le secret `EODHD_API_KEY` dans
*Settings > Secrets and variables > Actions*. Sans lui, le workflow s'arrête
avec un message explicite. Déclenchement manuel possible via *Run workflow*,
avec choix du filtre et du nombre d'instruments.

## Pipeline de mise à jour

1. Télécharger les listes Euronext (actions, ETF, fonds).
2. Dédoublonner par ISIN, agréger les places de cotation.
3. Calculer `PEA_indicatif` par règle métier.
4. Enrichir via OpenFIGI (`scripts/enrich_openfigi.py`) : FIGI, ticker exact, nom complet.
5. Croiser les listes émetteurs (`scripts/maj_pea_emetteurs.py`) puis reclasser (`scripts/enrich_pea.py`).
6. Valider (`scripts/validate_base.py`).

*Données à usage d'aide à la décision uniquement — ni conseil en investissement, ni conseil fiscal.*

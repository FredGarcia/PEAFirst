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

## Pipeline de mise à jour

1. Télécharger les listes Euronext (actions, ETF, fonds).
2. Dédoublonner par ISIN, agréger les places de cotation.
3. Calculer `PEA_indicatif` par règle métier.
4. Enrichir via OpenFIGI (`scripts/enrich_openfigi.py`) : FIGI, ticker exact, nom complet.
5. Croiser les listes émetteurs (`scripts/maj_pea_emetteurs.py`) puis reclasser (`scripts/enrich_pea.py`).
6. Valider (`scripts/validate_base.py`).

*Données à usage d'aide à la décision uniquement — ni conseil en investissement, ni conseil fiscal.*

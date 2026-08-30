# PEAFirst

Deux briques complémentaires réunies dans un même dépôt :

- **la chaîne de données** (`scripts/`) — de la liste brute des instruments
  Euronext jusqu'aux scores, au SRI et au tableau de bord statique. Sans aucune
  dépendance, exécutée quotidiennement par GitHub Actions ;
- **l'application PEAdvisor** (`peadvisor/`) — API REST FastAPI, base SQLite,
  interface web, scoring paramétrable, allocation, simulateur, watchlist et
  serveur MCP.

Les deux se rejoignent en un point : la source **`peafirst`** de l'application
lit le référentiel produit par la chaîne. L'application dispose ainsi de
données réelles et d'une éligibilité PEA vérifiée, là où son jeu `seed` reste
illustratif.

> **[Mode d'emploi → `docs/MODE_EMPLOI.md`](docs/MODE_EMPLOI.md)**
> Installation, clés d'API, chaîne de traitement pas à pas, réglages,
> problèmes courants et limites connues.

*Aide à la décision — ni conseil en investissement, ni conseil fiscal.*

---

## En bref

| | |
|---|---|
| Univers | 6 188 instruments Euronext (actions, ETF, OPCVM) |
| Identifiants | FIGI, ticker et nom complet via OpenFIGI |
| Éligibilité PEA | relevés émetteurs + règles métier, avec traçabilité de la source |
| Indicateurs | volatilité, drawdown, Sharpe, Sortino, performance |
| Risque | SRI estimé (bornes PRIIPS), volatilité, drawdown |
| Décision | score pondéré paramétrable, TOPSIS, moteur d'allocation SRI |
| Simulation | versements programmés, horizons 2 à 10 ans, scénarios, fiscalité 2026 |
| Restitution | tableau de bord HTML autonome, API REST, interface web, modules Apps Script |
| Agent | serveur MCP pour piloter l'application depuis Claude Desktop |

Deux contraintes structurent tout le projet :

1. **Aucune liste officielle d'ETF éligibles au PEA n'existe.** L'éligibilité
   est un engagement de la société de gestion dans le prospectus. Seule la fiche
   émetteur fait foi — d'où `pea_emetteurs.csv` et sa colonne `Source`.
2. **Les quotas gratuits sont l'étranglement.** 20 requêtes/jour chez EODHD :
   la base se construit progressivement, avec cache et reprise. Cinq des sept
   critères du cahier des charges n'ont aucune source européenne gratuite, ce
   que le tableau de bord affiche au lieu de le masquer.

---

## Modèle de données

```mermaid
classDiagram
    class Instrument {
        +string ISIN
        +string Nom
        +string Type
        +string Marches
        +string Devise
        +string Pays_emission
        +string PEA_indicatif
        +string ESG_classification
        +string Date_MAJ
    }
    class IdentifiantFIGI {
        +string FIGI
        +string Ticker
        +string Nom_complet
        +string Type_instrument
        +string Bourse
        +string Statut
    }
    class EligibilitePEA {
        +string PEA_eligible
        +string PEA_methode
        +string PEA_source
    }
    class ReleveEmetteur {
        +string Emetteur
        +string PEA_eligible
        +string Source
        +date Date_verification
    }
    class DonneeMarche {
        +float Cours
        +date Date_cours
        +float Perf_periode_pct
        +float Volatilite_annualisee_pct
        +float Drawdown_max_pct
        +float Sharpe
        +float Sortino
        +int Nb_seances
    }
    class Score {
        +float Score_global
        +float Couverture_pct
        +string Criteres_notes
        +int Rang
    }
    class Anomalie {
        +string Anomalie
        +string Gravite
        +string Detail
    }
    class PointHistorique {
        +date Date
        +int Collectes
        +int Notes
        +float Couverture_moy_pct
        +int Cours_perimes
    }
    class Ponderations {
        +float performance
        +float sharpe
        +float volatilite
        +float esg
        +float potentiel~sans source~
    }

    Instrument "1" --> "0..1" IdentifiantFIGI : enrichi par
    Instrument "1" --> "0..1" EligibilitePEA : si ETF ou OPCVM
    Instrument "1" --> "0..1" DonneeMarche : si collecté
    Instrument "1" --> "0..1" Score : si assez de données
    Instrument "1" --> "0..*" Anomalie : signalements
    ReleveEmetteur "0..*" ..> EligibilitePEA : fait autorité
    IdentifiantFIGI ..> EligibilitePEA : Nom_complet décode le libellé
    DonneeMarche ..> Score : critères notés
    Ponderations ..> Score : barème paramétrable
    Score ..> PointHistorique : agrégé quotidiennement
```

`Score` n'existe que si l'instrument réunit au moins 2 critères et 30 % du
barème : un instrument insuffisamment documenté est **écarté, jamais noté zéro**.
`Couverture_pct` accompagne toujours la note.

---

## Composants

```mermaid
flowchart TD
    EN["Euronext<br/><i>listes officielles</i>"]:::src
    OF["OpenFIGI<br/><i>250 req/min</i>"]:::src
    EM["Fiches émetteurs<br/><i>Amundi, iShares, BNP</i>"]:::src
    EO["EODHD<br/><i>20 req/jour</i>"]:::src
    MS["Marketstack<br/><i>100 req/mois</i>"]:::src

    B[("base_isin.csv<br/>6 188 instruments")]:::dat
    SO["enrich_openfigi.py"]:::scr
    F[("base_isin_figi.csv")]:::dat
    SE["maj_pea_emetteurs.py"]:::scr
    P[("pea_emetteurs.csv<br/><i>fait autorité</i>")]:::dat
    SP["enrich_pea.py"]:::scr
    FP[("base_isin_fonds_pea.csv")]:::dat
    SM["enrich_marche.py"]:::scr
    M[("base_isin_marche.csv")]:::dat
    SC["scoring.py"]:::scr
    S[("base_isin_scores.csv")]:::dat
    AN["anomalies.py"]:::scr
    HI["historique.py"]:::scr
    AL["allocation.py"]:::scr
    SI["simulateur.py"]:::scr
    DA["dashboard.py"]:::scr
    HT["dashboard.html"]:::out
    GS["scoring.gs · allocation.gs<br/><i>modules Apps Script</i>"]:::out

    EN --> B
    OF --> SO --> F
    EM --> SE --> P
    B --> SP
    F --> SP
    P --> SP
    SP --> FP
    EO --> SM
    MS --> SM
    B --> SM
    SM --> M
    M --> SC
    B --> SC
    SC --> S
    S --> AN
    M --> AN
    S --> HI
    S --> AL
    FP --> AL
    AL -.-> SI
    S --> DA
    FP --> DA
    AN --> DA
    HI --> DA
    DA --> HT
    AL -.-> GS
    SC -.-> GS
    HT -. "file d'attente · aucune clé embarquée" .-> SM

    classDef src fill:#fdf1e0,stroke:#b8762a,color:#16202b
    classDef scr fill:#eef1f4,stroke:#3d4d5c,color:#16202b
    classDef dat fill:#dfeeeb,stroke:#2f6f6b,color:#16202b
    classDef out fill:#e5ecf2,stroke:#1f4a5c,color:#16202b
```

Le tableau de bord **n'appelle aucune source** : il est versionné, une clé y
serait publiquement exposée. Il compose les paramètres du workflow, qui
s'exécute chez GitHub Actions où les clés sont stockées comme secrets.

---

## Collecte quotidienne

```mermaid
sequenceDiagram
    autonumber
    participant GA as GitHub Actions
    participant WF as collecte-marche.yml
    participant EM as enrich_marche.py
    participant CA as marche_cache.json
    participant EO as EODHD
    participant SC as scoring.py
    participant DA as dashboard.py
    participant RE as Dépôt

    GA->>WF: déclenchement 06h15 UTC (jours ouvrés)
    WF->>WF: vérifier le secret EODHD_API_KEY
    alt secret absent
        WF-->>GA: arrêt immédiat, message explicite
    else secret présent
        WF->>EM: --historique --filtre pea --limite 18
        EM->>CA: lire les instruments déjà traités
        CA-->>EM: cache + symboles indisponibles

        loop chaque instrument non traité (max 18)
            EM->>EO: historique 400 jours
            alt réponse valide
                EO-->>EM: séries de clôtures
                EM->>EM: volatilité, drawdown, Sharpe, Sortino
            else symbole absent
                EO-->>EM: erreur
                EM->>CA: marquer indisponible (plus jamais réinterrogé)
            else quota épuisé
                EO-->>EM: limite atteinte
                EM->>CA: sauvegarder puis arrêt propre
            end
        end

        EM->>CA: écrire le cache
        EM-->>WF: base_isin_marche.csv

        WF->>SC: recalculer les scores
        SC-->>WF: scores + couverture (instruments insuffisants écartés)
        WF->>WF: anomalies.py puis historique.py
        WF->>DA: régénérer le tableau de bord
        WF->>WF: validate_base.py
        alt contrôle en échec
            WF-->>GA: build rouge, rien n'est publié
        else contrôle réussi
            WF->>RE: commit et push des données
        end
    end
```

L'arrêt sur quota est **propre** : le cache est écrit avant de rendre la main,
et l'exécution du lendemain reprend exactement où celle-ci s'est arrêtée.

---

## Contenu du dépôt

```
data/        base ISIN, identifiants, éligibilité PEA, marché, scores, SRI,
             anomalies, historique, tableau de bord, caches de reprise
scripts/     chaîne de données : collecte, analyse, décision, restitution
             scoring.gs, allocation.gs (modules Apps Script génériques)
peadvisor/   application : modèles, routeurs, services, sources
config/      settings.yaml, scoring.yaml, clés API (gitignorées)
static/      interface web
tests/       suite de tests de l'application
docs/        mode d'emploi et dossier de conception
.github/     validate.yml (référentiel), tests.yml (application),
             collecte-marche.yml (collecte quotidienne)
```

## Lancer l'application

```bash
pip install -r requirements.txt
python run.py            # http://localhost:8000, Swagger sur /docs
python -m pytest tests/  # 115 tests
```

Pour l'alimenter avec les données réelles plutôt que le jeu illustratif,
choisir `source_active: peafirst` dans `config/settings.yaml`.

Chaque script porte sa documentation en tête (`--help`). Le détail des commandes,
des options et des réglages est dans le [mode d'emploi](docs/MODE_EMPLOI.md).

---

## Intégration continue

`validate.yml` s'exécute à chaque push : contrôle du schéma, cohérence des
sous-fichiers avec la base, puis **régénération** de `base_isin_fonds_pea.csv`
comparée au fichier commité. Modifier ce fichier à la main fait échouer le
build : passer par `enrich_pea.py`.

`collecte-marche.yml` s'exécute chaque jour ouvré et publie les données
collectées. Prérequis : le secret `EODHD_API_KEY`.

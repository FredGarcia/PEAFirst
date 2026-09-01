# Mode d'emploi — PEAFirst

Guide complet du dépôt, qui réunit deux briques complémentaires :

- **la chaîne de données** (`scripts/`) — de la liste brute des instruments
  Euronext jusqu'aux scores, au SRI, aux allocations et au tableau de bord
  statique. Sans aucune dépendance, exécutée quotidiennement par GitHub Actions.
  Sections 1 à 10 ;
- **l'application PEAdvisor** (`peadvisor/`) — API REST, base SQLite, interface
  web, scoring paramétrable, watchlist, auto-observation et serveur MCP.
  Sections 10bis et 10ter.

Les deux se rejoignent par la source `peafirst` de l'application, qui lit le
référentiel produit par la chaîne.

**Aide à la décision — ni conseil en investissement, ni conseil fiscal.**
Les scores et allocations produits ici classent des instruments selon des
critères explicites et partiels. Ils ne remplacent ni la lecture d'un
prospectus, ni l'avis d'un professionnel.

---

## Sommaire

- [Mode d'emploi — PEAFirst](#mode-demploi--peafirst)
  - [Sommaire](#sommaire)
  - [1. Installation](#1-installation)
  - [2. Clés d'API](#2-clés-dapi)
    - [Couverture réelle, testée sur instruments européens](#couverture-réelle-testée-sur-instruments-européens)
  - [3. Démarrage rapide](#3-démarrage-rapide)
3ter. [Depuis un téléphone](#3ter-depuis-un-téléphone)
  - [3bis. Actions initiales](#3bis-actions-initiales)
    - [A. Activer la collecte automatique (5 minutes)](#a-activer-la-collecte-automatique-5-minutes)
    - [B. Vérifier le droit d'écriture du jeton (si vous poussez depuis un poste)](#b-vérifier-le-droit-décriture-du-jeton-si-vous-poussez-depuis-un-poste)
    - [C. Enregistrer vos clés localement](#c-enregistrer-vos-clés-localement)
  - [4. La chaîne complète](#4-la-chaîne-complète)
    - [4.1 Base ISIN (déjà constituée)](#41-base-isin-déjà-constituée)
    - [4.2 Identifiants OpenFIGI](#42-identifiants-openfigi)
    - [4.3 Éligibilité PEA](#43-éligibilité-pea)
    - [4.3bis Éligibilité PEA des actions](#43bis-éligibilité-pea-des-actions)
    - [4.4 Données de marché et indicateurs](#44-données-de-marché-et-indicateurs)
    - [4.4bis Indicateur de risque SRI](#44bis-indicateur-de-risque-sri)
    - [4.5 Scores](#45-scores)
    - [4.6 Anomalies](#46-anomalies)
    - [4.7 Progression](#47-progression)
    - [4.8 Allocation](#48-allocation)
  - [5. Le tableau de bord](#5-le-tableau-de-bord)
  - [6. Automatisation](#6-automatisation)
  - [7. Fichiers produits](#7-fichiers-produits)
  - [8. Réglages](#8-réglages)
  - [9. Problèmes courants](#9-problèmes-courants)
  - [10. Ce que la base ne sait pas](#10-ce-que-la-base-ne-sait-pas)
  - [10bis. L'application PEAdvisor](#10bis-lapplication-peadvisor)
    - [A. Installation et lancement](#a-installation-et-lancement)
    - [B. Les onze écrans](#b-les-onze-écrans)
    - [C. Les sources de données](#c-les-sources-de-données)
    - [D. Ce que la source `peafirst` apporte](#d-ce-que-la-source-peafirst-apporte)
    - [E. Paramétrage sans toucher au code](#e-paramétrage-sans-toucher-au-code)
    - [F. L'API REST](#f-lapi-rest)
    - [G. Le serveur MCP](#g-le-serveur-mcp)
    - [H. Documentation de conception](#h-documentation-de-conception)
  - [10ter. Deux avertissements sur l'application](#10ter-deux-avertissements-sur-lapplication)
  - [11. Simulateur](#11-simulateur)
  - [12. Aide-mémoire des actions](#12-aide-mémoire-des-actions)
    - [Une seule fois](#une-seule-fois)
    - [Sans rien faire](#sans-rien-faire)
    - [Lancer l'application](#lancer-lapplication)
    - [Quand vous le souhaitez](#quand-vous-le-souhaitez)
    - [Avant d'acheter](#avant-dacheter)

---

## 1. Installation

Python 3.9 ou plus récent, sans dépendance externe : tous les scripts
n'utilisent que la bibliothèque standard.

```bash
git clone https://github.com/FredGarcia/PEAFirst.git
cd PEAFirst
python3 scripts/validate_base.py     # doit afficher : OK
```

Si `validate_base.py` affiche « OK : tous les contrôles passent », le dépôt est
sain et vous pouvez travailler. Ce script est aussi le garde-fou de
l'intégration continue : **le lancer avant tout commit** évite un build rouge.

---

## 1bis. Sous Windows

Toutes les commandes de ce guide sont écrites pour Linux et macOS. Voici les
équivalents Windows ; le reste du document s'applique tel quel.

### Python : `python` et non `python3`

```powershell
python --version
```

Si la commande échoue, essayer `py --version`. Utiliser ensuite ce nom partout
où le guide écrit `python3`.

### Environnement virtuel

L'environnement virtuel est **facultatif** : `pip install -r requirements.txt`
fonctionne directement, il isole simplement moins bien les dépendances.

| Terminal | Activation |
|---|---|
| PowerShell | `.venv\Scripts\Activate.ps1` |
| Invite de commandes (cmd) | `.venv\Scripts\activate.bat` |
| Git Bash | `source .venv/Scripts/activate` |

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python run.py
```

`(.venv)` apparaît alors en début de ligne. Pour en sortir : `deactivate`.

Sous Git Bash, noter que le dossier est `Scripts` et non `bin` : la commande
Linux `source .venv/bin/activate` ne fonctionne pas telle quelle.

### Si l'activation est refusée

Un message sur les scripts désactivés vient de la stratégie d'exécution de
PowerShell. À lancer une seule fois :

```powershell
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
```

Ce réglage n'autorise que les scripts locaux et ceux signés — c'est celui que
Microsoft recommande, et il ne s'applique qu'à votre compte.

### Variables d'environnement

Le guide utilise `export`, qui n'existe pas sous Windows.

```powershell
setx EODHD_API_KEY "votre_cle"
setx OPENFIGI_API_KEY "votre_cle"
setx MARKETSTACK_API_KEY "votre_cle"
```

`setx` écrit dans le registre, donc de façon permanente — mais **les variables
ne sont visibles que dans les fenêtres ouvertes ensuite** : fermer et rouvrir le
terminal. Vérification : `echo $env:EODHD_API_KEY`.

Pour la session en cours seulement : `$env:EODHD_API_KEY = "votre_cle"`.

Par l'interface : touche Windows → « variables d'environnement » → *Modifier
les variables d'environnement pour votre compte*.

Sous Git Bash, `export` et `~/.bashrc` fonctionnent comme sous Linux.

### Chemins

PowerShell accepte les deux séparateurs pour les arguments Python :
`python scripts\dashboard.py` et `python scripts/dashboard.py` sont
équivalents.

### Rien de tout cela n'est nécessaire pour consulter

Les clés ne servent qu'à **collecter** des données, ce que le robot GitHub fait
déjà chaque jour ouvré. Ouvrir `data/dashboard.html`, lancer le simulateur ou
l'allocation n'en demande aucune.

---

## 2. Clés d'API

Aucune clé n'est nécessaire pour consulter les données déjà collectées. Elles
ne servent qu'à enrichir la base.

Les clés se passent par variable d'environnement, **jamais en argument dans un
fichier versionné** :

```bash
export EODHD_API_KEY="votre_cle"
export MARKETSTACK_API_KEY="votre_cle"
export OPENFIGI_API_KEY="votre_cle"
```
```powershell
setx EODHD_API_KEY "votre_cle"
setx OPENFIGI_API_KEY "votre_cle"
setx MARKETSTACK_API_KEY "votre_cle"
echo verification
echo $env:EODHD_API_KEY
```
```bash
echo 'export EODHD_API_KEY="votre_cle"' >> ~/.bashrc
source ~/.bashrc
```
Si le fichier n'existe pas, cette commande le crée. C'est l'option la plus simple si vous voulez copier-coller les commandes de la documentation sans les adapter.
### Couverture réelle, testée sur instruments européens

| Source | Quota gratuit | Europe | Usage dans le projet |
|---|---|---|---|
| **EODHD** | 20 requêtes/**jour** | Paris, Amsterdam, Bruxelles, Lisbonne, Oslo, Milan, Dublin | historique + indicateurs (source par défaut) |
| **Marketstack** | 100 requêtes/**mois**, lots de 50 | Paris, Amsterdam, Bruxelles, Lisbonne — grandes capitalisations | cours en masse |
| **OpenFIGI** | 25 req/min sans clé, lots de 10 ; **250 req/min avec clé, lots de 100** | mondiale | FIGI, ticker, nom complet |
| Alpha Vantage | 25 requêtes/jour | partielle | repli |
| FMP, Finnhub, Tiingo, Polygon | — | **aucune** en gratuit (États-Unis seulement) | à réserver à une enveloppe CTO |

Deux conséquences pratiques :

- **Le quota EODHD est journalier** : il se régénère. C'est la source à
  privilégier pour un travail régulier.
- **Le quota Marketstack est mensuel** : une fois épuisé, plus rien avant le
  mois suivant. À réserver aux collectes de cours en masse, et à ne pas gaspiller.
- **Aucune de ces sources ne fournit l'éligibilité PEA.** Elle vient uniquement
  de `data/pea_emetteurs.csv` (voir §4.3).

---

## 3. Démarrage rapide

Consulter l'existant, sans aucune clé :

```bash
python3 scripts/dashboard.py          # régénère data/dashboard.html
python3 scripts/scoring.py --top 10   # classement des instruments notés
```

Ouvrir ensuite `data/dashboard.html` dans un navigateur.

Collecter de nouvelles données (une clé EODHD suffit) :

```bash
export EODHD_API_KEY="votre_cle"
python3 scripts/enrich_marche.py --etat --filtre pea      # où en est-on ?
python3 scripts/enrich_marche.py --historique --filtre pea --limite 18 # max 475
python3 scripts/scoring.py #--top 20
python3 scripts/anomalies.py --resume
python3 scripts/historique.py
python3 scripts/dashboard.py
```

`--limite 18` laisse une marge sous le quota de 20/jour.

---

## 3ter. Depuis un téléphone

Rien à installer : le robot collecte seul et le tableau de bord est une page
web. Le téléphone sert à **consulter et déclencher**, pas à calculer.

### Consulter le tableau de bord

Ouvrir dans le navigateur (une seule ligne, sans retour) :

```
https://htmlpreview.github.io/?https://github.com/FredGarcia/PEAFirst/blob/main/data/dashboard.html
```

Puis menu ⋮ → *Ajouter à l'écran d'accueil* pour obtenir une icône. La page est
responsive et testée en 390 px : tri, filtres, regroupement, comparateur et
export CSV fonctionnent au doigt.

> Ce service tiers rend la page depuis GitHub et peut être lent ou
> indisponible. L'alternative fiable est d'activer **GitHub Pages**
> (*Settings → Pages*, source `main`), ce qui donne une URL propre du type
> `fredgarcia.github.io/PEAFirst/data/dashboard.html`.

### Déclencher une collecte

Application **GitHub** ou github.com dans le navigateur → dépôt **PEAFirst** →
onglet **Actions** → *Collecte quotidienne* → **Run workflow**. Les clés étant
des secrets du dépôt, tout s'exécute chez GitHub.

Pour cibler des instruments : dans le tableau de bord, filtrer, cocher, ouvrir
**Piloter la collecte**, puis **Copier les paramètres** et les coller dans le
formulaire *Run workflow*.

### Ce qui n'est pas disponible

Les scripts Python — simulateur, allocation, scoring local — et l'application
PEAdvisor. Techniquement possible via Termux, mais peu confortable :
**ordinateur pour travailler, téléphone pour consulter et déclencher**.

## 3bis. Actions initiales

Ces gestes ne se font qu'une fois. Chacun est décrit clic par clic.

### A. Activer la collecte automatique (5 minutes)

Sans cette étape, la base n'évolue plus toute seule.

1. Ouvrir **github.com/FredGarcia/PEAFirst**
2. Onglet **Settings** — celui du dépôt, dans la barre au-dessus du code, pas
   les réglages du compte
3. Menu de gauche : **Secrets and variables**, puis **Actions**
4. Bouton vert **New repository secret**
5. **Name** : `EODHD_API_KEY` — exactement cette orthographe. Le workflow
   cherche ce nom précis ; toute variante le fera échouer
6. **Secret** : coller la clé, sans guillemets ni espace
7. **Add secret**

GitHub ne réaffichera plus jamais la valeur en clair : elle pourra seulement
être remplacée ou supprimée. C'est normal.

**Vérifier immédiatement**, sans attendre le lendemain :

1. Onglet **Actions**
2. Colonne de gauche : **Collecte quotidienne des données de marché**
3. Bouton **Run workflow** → laisser les valeurs par défaut → **Run workflow**
4. Rafraîchir après quelques secondes, ouvrir l'exécution

Si l'étape « Vérifier la présence de la clé » est verte, tout s'enchaîne. Si
elle échoue, le secret est absent ou mal nommé — le workflow s'arrête là
volontairement, pour ne pas consommer de quota inutilement.

Un message *« Node.js 20 is deprecated »* peut apparaître : c'est un
**avertissement**, pas une erreur. Les actions s'exécutent quand même. Se fier
à la pastille verte ou rouge de l'exécution, pas à ce message.

### B. Vérifier le droit d'écriture du jeton (si vous poussez depuis un poste)

Un jeton *fine-grained* doit avoir **Contents : Read and write**. La lecture
peut fonctionner alors que le push échoue en 403.

Settings du compte → Developer settings → Personal access tokens →
Fine-grained tokens → le jeton → **Permissions** → **Repository permissions** →
ligne **Contents** → **Read and write** → **Update token** tout en bas.

> Le bouton de confirmation en bas de page est souvent oublié : sans lui, la
> modification n'est pas enregistrée.

Contrôle en une commande (n'écrit rien) :

```bash
curl -s -o /dev/null -w "%{http_code}\n" -X PUT \
  -H "Authorization: Bearer $GITHUB_TOKEN" \
  "https://api.github.com/repos/FredGarcia/PEAFirst/contents/.permcheck" -d '{}'
```

`422` = droit d'écriture présent. `403` = lecture seule.

### C. Enregistrer vos clés localement

Ajouter à votre `~/.bashrc` ou `~/.zshrc` pour ne plus y penser :

```bash
export EODHD_API_KEY="votre_cle"
export OPENFIGI_API_KEY="votre_cle"
export MARKETSTACK_API_KEY="votre_cle"
```

Puis `source ~/.bashrc`. **Ne jamais écrire une clé dans un fichier du dépôt** :
tout ce qui est commité sur un dépôt public est lisible par tous, et une clé
exposée doit être révoquée.

---

## 4. La chaîne complète

Les étapes 4.1 et 4.2 sont déjà faites dans le dépôt : à relancer seulement pour
rafraîchir l'univers.

### 4.1 Base ISIN (déjà constituée)

`data/base_isin.csv` contient 6 188 instruments issus des listes officielles
Euronext (actions, ETF, fonds), dédoublonnés par ISIN, les multi-cotations
agrégées dans `Marché(s)`. Les sous-fichiers `_actions`, `_etf` et `_opcvm` en
sont des extraits, et doivent rester **strictement cohérents** avec la base :
`validate_base.py` échoue sinon.

### 4.2 Identifiants OpenFIGI

```bash
export OPENFIGI_API_KEY="votre_cle"       # facultatif mais 25x plus rapide
python3 scripts/enrich_openfigi.py        # fonds seulement (ETF + OPCVM)
python3 scripts/enrich_openfigi.py --tout # toute la base, actions comprises
```

Produit `data/openfigi_cache.csv` (cache incrémental, reprise automatique) et
`data/base_isin_figi.csv`.

Le champ décisif est **`Nom_complet`** : il décode les libellés techniques
Euronext (`VANETFV3PLIMETFP`) en noms lisibles, ce qui permet à l'étape suivante
d'identifier les fonds obligataires ou monétaires derrière un code opaque.
Interrompre le script avec Ctrl-C est sans risque : le cache est sauvegardé.

### 4.3 Éligibilité PEA

> **Il n'existe aucune liste officielle des ETF éligibles au PEA.** Ni l'AMF,
> ni l'administration fiscale, ni Euronext n'en publient. L'éligibilité est un
> engagement pris par la société de gestion dans le prospectus, sous sa
> responsabilité. La seule source qui fait foi est **la fiche produit de
> l'émetteur**, à une date donnée.

`data/pea_emetteurs.csv` matérialise ce relevé. Pour l'enrichir, préparer un
fichier `ISIN;Nom` puis :

```bash
python3 scripts/maj_pea_emetteurs.py --merge ma_liste.csv \
    --emetteur "Amundi" \
    --source "Fiche produit amundietf.fr, relevée le 2026-08-28" \
    --eligible OUI
python3 scripts/enrich_pea.py        # régénère le classement
python3 scripts/validate_base.py
```

Décrire la source **précisément** : c'est ce qui permettra plus tard de savoir
si une entrée vient d'une fiche émetteur (fiable) ou d'un relevé secondaire
(à reconfirmer). `--eligible NON` sert à marquer les pièges — un ETF à
réplication physique dont l'achat entraînerait la clôture du plan.

`enrich_pea.py` classe ensuite chaque fonds par priorité décroissante :
liste émetteur, mention « PEA » dans le nom, classe d'actifs inéligible, pays
hors EEE, indice européen, puis `A_VERIFIER` par défaut.

### 4.3bis Éligibilité PEA des actions

```bash
python3 scripts/enrich_pea_actions.py --resume
```

Produit `data/base_isin_actions_pea.csv`. La colonne `PEA_indicatif` de la base
repose sur le seul préfixe pays de l'ISIN : elle classait « OUI » des titres
non éligibles. Ce script applique des règles plus fines, par priorité
décroissante :

| Priorité | Règle | Effet |
|---|---|---|
| 1 | correction utilisateur (`corrections_pea.csv`) | fait toujours foi |
| 2 | régime foncier (`Type_instrument = REIT`) | **NON** |
| 2bis | régime annoncé dans la raison sociale (SOCIMI, SIIC, SIIQ, Sicafi, REIT) | **NON** |
| 3 | bon ou droit de souscription | **NON** |
| 4 | pays d'émission hors EEE | **NON** |
| 5 | nature incertaine (préférence, certificat, action d'épargne…) | **A_VERIFIER** |
| 6 | action ordinaire émise dans l'EEE | **OUI** |

> **Foncières cotées.** Les SIIC ne sont plus éligibles au PEA depuis le
> 21 octobre 2011, et il en va de même des régimes européens équivalents :
> Sicafi/SIR belge, SOCIMI espagnol, FBI néerlandais, SIIQ italien, G-REIT
> allemand, UK-REIT. La règle exclut donc 68 titres que l'ancienne méthode
> retenait — Klépierre, Gecina, Unibail, Icade, Covivio et leurs équivalents
> européens. Loger un titre inéligible dans un PEA expose à la clôture du plan.

**Colonne `Vigilance`.** Une société au nom immobilier n'est pas forcément une
foncière à statut transparent : un promoteur reste éligible. Ces titres gardent
donc leur classement mais portent un signal, remonté dans le tableau de bord par
un marqueur **!** sur la colonne PEA et par le filtre *À contrôler*. Le signal
est volontairement large : il attrape quelques faux positifs (un logisticien
n'est pas une foncière), ce qui est sans conséquence puisqu'il ne modifie pas le
classement — alors qu'une foncière manquée coûterait la clôture du plan.

Pour travailler la liste :

```bash
python3 scripts/enrich_pea_actions.py --a-verifier
```

Affiche les titres au statut indéterminé et ceux classés OUI sous réserve.
Chaque exécution se termine par un rappel du risque, sauf avec `--silencieux`.

**Corriger une éligibilité.** Les règles se trompent : elles s'appuient sur la
classification OpenFIGI, qui n'est ni exhaustive ni infaillible. Depuis le
tableau de bord :

1. filtrer et cocher les lignes concernées ;
2. bouton **Corriger l'éligibilité PEA** ;
3. choisir `OUI`, `NON` ou `A_VERIFIER`, saisir un motif ;
4. **Appliquer à la sélection**, puis **Télécharger corrections_pea.csv** ;
5. remplacer `data/corrections_pea.csv` par le fichier obtenu ;
6. relancer `python3 scripts/enrich_pea_actions.py`.

Le fichier est cumulatif : il contient toutes les corrections, y compris celles
déjà enregistrées. Une correction prime sur toutes les règles automatiques.

### 4.4 Données de marché et indicateurs

```bash
export EODHD_API_KEY="votre_cle"
python3 scripts/enrich_marche.py --etat --filtre pea
python3 scripts/enrich_marche.py --historique --filtre pea --limite 18
```

Calcule volatilité annualisée, drawdown maximal, Sharpe, Sortino et performance
sur 400 jours (réglable via `--jours`), et écrit `data/base_isin_marche.csv`.

Options utiles :

| Option | Effet |
|---|---|
| `--etat` | avancement, **sans consommer de quota** |
| `--filtre pea\|actions\|etf\|tout` | restreindre l'univers |
| `--limite N` | plafonner le nombre d'appels |
| `--isins FR000...,BE097...` | traiter un lot précis |
| `--file-attente fichier.txt` | traiter une file exportée du tableau de bord |
| `--source marketstack` | basculer de fournisseur |
| `--cours` | dernier cours en masse (Marketstack, lots de 50) |
| `--forcer` | réinterroger malgré le cache |

Le cache `data/marche_cache.json` permet la reprise : un instrument déjà
collecté n'est jamais réinterrogé, et un symbole absent du fournisseur est
marqué une fois pour toutes.

### 4.4bis Indicateur de risque SRI

```bash
python3 scripts/sri.py --resume
```

Produit `data/base_isin_sri.csv` : estimation du SRI (1 à 7) des PRIIPS à partir
de la volatilité annualisée, selon les bornes du règlement délégué (UE) 2017/653
révisé par le règlement 2021/2268.

| SRI | VEV | SRI | VEV |
|---|---|---|---|
| 1 | < 0,5 % | 5 | 20 – 30 % |
| 2 | 0,5 – 5 % | 6 | 30 – 80 % |
| 3 | 5 – 12 % | 7 | > 80 % |
| 4 | 12 – 20 % | | |

**Ce n'est pas le SRI officiel**, et l'écart est mesurable :

- la VEV réglementaire corrige la volatilité de l'asymétrie et de
  l'aplatissement par un développement de Cornish-Fisher. **Sans ces
  corrections, la formule redonne exactement la volatilité annualisée** : notre
  estimation est donc la méthode officielle sous hypothèse de rendements
  normaux. Les collectes récentes enregistrent ces moments et la correction
  s'applique alors ; la colonne `Methode` indique laquelle a servi ;
- le règlement impose **cinq ans** d'historique hebdomadaire, nous en avons
  environ dix-huit mois quotidiens : toutes les estimations actuelles sont de
  fiabilité « faible » ;
- le **risque de crédit** (CRM) n'est pas évalué : il peut relever le SRI d'un
  fonds au-dessus de son seul risque de marché ;
- le MRM officiel est la valeur la plus fréquente sur quatre mois, non une
  valeur instantanée.

> **Une action n'est pas un PRIIPS** et n'a donc aucun SRI officiel. L'échelle
> lui est appliquée par analogie, pour permettre la comparaison ; la colonne
> `Ecart_officiel` le signale ligne par ligne.

**Enregistrer un SRI officiel.** Le chiffre lu sur un DIC est le SRI
réglementaire : il **remplace** l'estimation, sans réserve. Depuis le tableau
de bord :

1. cocher les lignes concernées ;
2. bouton **Corriger l'éligibilité PEA** → sélecteur **SRI officiel relevé sur
   un DIC** ;
3. choisir la classe, saisir la source et **la date du DIC** ;
4. **Appliquer à la sélection**, puis **Télécharger corrections_sri.csv** ;
5. remplacer `data/corrections_sri.csv`, relancer `python3 scripts/sri.py`.

La date compte : un SRI est révisable, et un relevé ancien reste un relevé
ancien. Le script signale les cas où le chiffre officiel diverge de
l'estimation — un écart est normal, le DIC intégrant le risque de crédit et
cinq ans d'historique.

Dans le tableau de bord, la colonne SRI est triable, avec un code couleur ; un
SRI officiel se distingue d'une estimation par un contour marqué, et la réserve
figure en infobulle. Le DIC de l'émetteur reste la seule référence.

| Fichier | Rôle |
|---|---|
| `data/corrections_pea.csv` | éligibilité PEA corrigée, prime sur les règles |
| `data/corrections_sri.csv` | SRI officiel relevé sur DIC, prime sur l'estimation |

### 4.4ter Potentiel et fondamentaux (persistants)

```bash
python run.py                                    # dans un autre terminal
python3 scripts/enrich_potentiel.py --etat
python3 scripts/enrich_potentiel.py --filtre pea --limite 25
python3 scripts/scoring.py
```

Alimente `data/base_isin_potentiel.csv` : potentiel, objectif de cours,
consensus, PER, rendement, note ESG, secteur et capitalisation — soit les
critères que l'historique de cours ne permet pas de calculer.

**Effet mesuré sur le barème** : la couverture d'un instrument enrichi passe de
**60 % à 94 %**. Dix critères sur onze sont alors notés ; seule la
**croissance** reste absente, aucune source ne la fournissant.

| Option | Effet |
|---|---|
| `--etat` | avancement, **sans aucun appel** |
| `--filtre` | `pea` (défaut, éligibilité confirmée), `actions`, `etf`, `tout` |
| `--isins` | liste précise d'ISIN |
| `--limite N` | valeurs par exécution (défaut 25) |
| `--pause N` | délai entre appels (défaut 2 s) |
| `--forcer` | réinterroger l'acquis |

Le script **n'a aucune dépendance** : il pilote l'API de l'application, dont le
code de scraping est testé, plutôt que de le réécrire. L'application doit donc
tourner ; sinon le script s'arrête avec un message explicite avant d'entamer le
lot.

Il espace ses appels, reprend où il s'est arrêté et écrit après chaque valeur :
une interruption ne perd rien. Interroger des milliers de fiches d'affilée
serait discourtois et fragile — d'où la limite basse par défaut.

**Toutes les valeurs n'ont pas de potentiel.** Une petite capitalisation n'est
suivie par aucun analyste : la colonne reste vide, ce qui est un constat et non
un échec. Sur un lot de six grandes valeurs françaises, cinq potentiels ont été
relevés.

> Le scraping se heurte aux conditions d'utilisation du site et à la licence
> Euronext sur les cours. Ces données entrent ici dans le **référentiel
> versionné**, à la différence de l'import ponctuel du tableau de bord.

**Note ESG : deux échelles.** La classification SFDR (article 8/9) concerne les
fonds, la note du fournisseur (0-100) les actions. Les mélanger dans un même
classement fausserait tout. Ce n'est pas le cas ici parce que le rang percentile
est calculé **par type** et que les deux populations sont disjointes — mais
c'est une propriété à préserver.

### 4.5 Scores

```bash
python3 scripts/scoring.py --top 20
python3 scripts/scoring.py --type ETF --min-couverture 50
```

Score sur 100 par **rang percentile au sein du même `Type`** — on ne compare pas
la volatilité d'un ETF à celle d'une petite capitalisation. Les pondérations
sont dans `data/scoring_params.json`, modifiables sans toucher au code.

Deux garde-fous : au moins **2 critères notés** et **30 % du barème couvert**.
En deçà, l'instrument est **écarté, jamais noté zéro** — le noter zéro le ferait
passer pour mauvais alors qu'il est seulement non documenté.

La colonne `Couverture_pct` accompagne chaque score : à 60 %, il classe sur le
risque et la performance passée, pas sur la valorisation ni les perspectives.

### 4.6 Anomalies

```bash
python3 scripts/anomalies.py --resume
```

Huit règles : série trop courte, volatilité extrême, volatilité quasi nulle,
Sharpe aberrant, drawdown incohérent avec la volatilité, performance extrême, cours
périmé, couverture faible.

Un indicateur spectaculaire est plus souvent le symptôme d'une donnée douteuse
que d'une opportunité : un Sharpe de 5 sur un titre échangé trois fois par mois
traduit une série de cours plate. **Ces signalements demandent une vérification,
ils ne disqualifient pas l'instrument.** Les seuils sont en tête du fichier et
mériteront un recalibrage quand l'univers dépassera quelques centaines de lignes.

### 4.7 Progression

```bash
python3 scripts/historique.py                # point du jour
python3 scripts/historique.py --reconstruire # amorce depuis l'historique Git
```

`--reconstruire` ne fabrique aucune donnée : il relit des états déjà commités.

### 4.8 Allocation

```bash
python3 scripts/allocation.py --capital 10000 --risque 5 --horizon 10 \
    --objectif croissance --pea-uniquement
```

Le profil de risque suit les bornes de volatilité **PRIIPS (indicateur SRI)**,
comparables à celles des documents d'information des fonds :

| SRI | Volatilité annualisée | SRI | Volatilité annualisée |
|---|---|---|---|
| 1 | < 0,5 % | 5 | 20 – 30 % |
| 2 | 0,5 – 5 % | 6 | 30 – 80 % |
| 3 | 5 – 12 % | 7 | > 80 % |
| 4 | 12 – 20 % | | |

Un horizon inférieur à 5 ans resserre automatiquement le plafond : moins de
temps disponible pour absorber une baisse.

Deux limites, affichées à chaque exécution :

- **Les corrélations ne sont pas modélisées.** La volatilité annoncée est une
  moyenne pondérée, donc un *majorant* : un portefeuille réellement diversifié
  sera moins volatil. Le chiffre sert à comparer des allocations entre elles,
  pas à prédire un risque.
- **L'objectif « revenus » n'est pas servi correctement**, faute de source
  gratuite sur les dividendes européens. La sélection privilégie alors la
  régularité, et le script le signale.

Si aucun instrument ne respecte la contrainte, le moteur **n'invente pas une
allocation** : il l'indique et propose d'élargir l'univers ou de relever le profil.

---

## 5. Le tableau de bord

```bash
python3 scripts/dashboard.py --top 12 --seuil-fraicheur 7
```

Ouvrir `data/dashboard.html` dans un navigateur. Page autonome, consultable
hors ligne, organisée en **neuf onglets** qui reprennent les écrans de
l'application PEAdvisor réalisables sans serveur :

| Onglet | Contenu |
|---|---|
| **Synthèse** | fraîcheur, progression de la collecte, couverture du barème, KPI, répartitions, meilleurs scores, matrice TOPSIS |
| **Explorateur** | recherche, filtres, tri, regroupement, comparateur, constitution de lots, pilotage de la collecte, corrections |
| **Allocation** | capital, risque 1-7, horizon, objectif → portefeuille calculé dans le navigateur |
| **Simulateur** | versements programmés, six horizons, trois scénarios, frais, inflation, fiscalité PEA ou compte-titres |
| **Watchlist** | valeurs cochées dans l'Explorateur, export CSV |
| **Historique** | un relevé par jour de collecte, progression, export CSV |
| **Sources** | origine réelle des cours en base, fraîcheur par source, quotas constatés |
| **Paramètres** | pondérations du score, **recalcul immédiat dans le navigateur**, export du fichier |
| **Système** | anomalies détectées, indicateurs prévus non alimentés |

Correspondance avec les onze écrans de l'application :

| Écran PEAdvisor | Onglet statique |
|---|---|
| dashboard | Synthèse |
| actions, etf, opcvm | Explorateur (filtre par nature) |
| allocation, simulateur, watchlist, historique, sources, parametres, systeme | onglet de même nom |

Les onglets Allocation, Simulateur et Paramètres sont des **transpositions
fidèles** de `scripts/allocation.py`, `scripts/simulateur.py` et
`scripts/scoring.py` : à paramètres identiques, les résultats sont les mêmes.
Le recalcul des scores reprend la méthode exacte — rang percentile au sein du
même type, renormalisation sur les critères disponibles, minimum de 2 critères
et 30 % du barème couvert. Ils calculent dans le navigateur,
donc sans serveur ni clé — utilisable depuis un téléphone.

Deux écrans de l'application n'ont pas d'équivalent ici, faute de données :
les **corrélations** (les séries de rendements ne sont pas dans les CSV) et la
**répartition sectorielle** (aucun champ secteur dans les listes Euronext).

La watchlist et les pondérations modifiées vivent le temps de la session :
cette page n'écrit rien sur votre appareil. Les exporter pour les conserver —
`scoring_params.json` remplace alors le fichier du dépôt, et
`scripts/scoring.py` reprend les nouvelles pondérations.

- **Bandeau de fraîcheur** : génération, MAJ base, cours le plus récent et le
  plus ancien, nombre de cours périmés.
- **Progression** : trois courbes. Une courbe qui stagne signale un quota épuisé
  ou un workflow en échec — ce qu'aucun score ne montrerait.
- **Couverture du barème** : part manquante dessinée en creux.
- **Explorateur** : recherche, filtres (nature, pays, éligibilité, état), tri par
  clic sur toute colonne, regroupement. Chaque ligne porte son état — *noté*,
  *collecté*, *en attente* — et un marqueur ▲ si une anomalie la concerne.
- **Comparateur** : cocher 2 à 5 instruments les affiche côte à côte, meilleure
  valeur de chaque ligne mise en évidence.
- **Barre d'actions** au-dessus du tableau :

| Bouton | Ce qu'il fait | Disponible |
|---|---|---|
| **Exporter la vue (CSV)** | télécharge `vue_peafirst.csv` avec les lignes **telles que filtrées et triées** à l'écran, 15 colonnes, encodage compatible Excel | toujours |
| **Copier les ISIN** | met les ISIN sélectionnés dans le presse-papiers, un par ligne | si sélection |
| **File d'attente** | télécharge `file_attente.txt` à passer à `--file-attente` | si sélection |
| **Commande d'allocation** | copie une commande `allocation.py` prête à ajuster | si sélection |
| **Vider la sélection** | décoche tout | si sélection |
| **Piloter la collecte** | ouvre un panneau qui compose les paramètres du workflow et donne le lien vers *Run workflow* | toujours |
| **Corriger l'éligibilité PEA** | marque les lignes sélectionnées OUI/NON/A_VERIFIER et exporte `corrections_pea.csv` | si sélection |
| **Ajouter depuis Boursorama** | prépare la requête d'ajout d'une valeur par scraping, exécutée par l'application | toujours |

  Les boutons sans objet sont **désactivés** plutôt que silencieusement
  inopérants, et chaque action confirme son effet sur le bouton lui-même
  (« 33 ligne(s) exportée(s) », « 2 ISIN copiés »).

- **Constitution de lots** : cocher des lignes fait apparaître un panneau avec
  la commande de collecte correspondante. « Tout sélectionner » porte sur
  l'ensemble du filtre courant, pas sur la seule page affichée.
- **TOPSIS** : classement par distance à la solution idéale, indépendant du
  score pondéré. Un écart de rang entre les deux méthodes signale un instrument
  dont la note dépend fortement des pondérations retenues.

> **La page n'embarque aucune clé d'API et n'appelle aucune source.** Elle est
> versionnée sur GitHub, où une clé serait publiquement exposée. Elle prépare
> les lots ; les scripts les exécutent.

Enchaînement typique : filtrer *En attente* + *Éligible confirmé* → tout
sélectionner → télécharger la file d'attente → puis :

```bash
python3 scripts/enrich_marche.py --historique \
    --file-attente ~/Téléchargements/file_attente.txt --limite 18
```

---

## 6. Automatisation

`.github/workflows/collecte-marche.yml` s'exécute chaque jour ouvré à 06h15 UTC :
collecte un lot, recalcule les scores, détecte les anomalies, enregistre la
progression, régénère le tableau de bord, contrôle l'intégrité, publie.

**Prérequis unique** : ajouter le secret `EODHD_API_KEY` dans
*Settings → Secrets and variables → Actions → New repository secret*. Sans lui,
le workflow s'arrête avec un message explicite.

Déclenchement manuel : onglet *Actions* → *Collecte quotidienne* → *Run
workflow*, avec choix du filtre et du nombre d'instruments. Plusieurs
déclenchements par jour sont possibles dans la limite du quota.

`.github/workflows/validate.yml` s'exécute à chaque push : il vérifie le schéma
et **régénère** `base_isin_fonds_pea.csv` pour le comparer au fichier commité.
Modifier ce fichier à la main fait échouer le build — passer par
`enrich_pea.py`.

---

## 7. Fichiers produits

| Fichier | Contenu | Produit par |
|---|---|---|
| `base_isin.csv` | 6 188 instruments, 11 colonnes | listes Euronext |
| `base_isin_actions/_etf/_opcvm.csv` | extraits par type | listes Euronext |
| `base_isin_figi.csv` | FIGI, ticker, nom complet | `enrich_openfigi.py` |
| `openfigi_cache.csv` | cache incrémental | `enrich_openfigi.py` |
| `pea_emetteurs.csv` | **relevés émetteurs — fait autorité** | `maj_pea_emetteurs.py` |
| `base_isin_fonds_pea.csv` | éligibilité PEA des fonds | `enrich_pea.py` |
| `base_isin_marche.csv` | cours et indicateurs | `enrich_marche.py` |
| `marche_cache.json` | cache de reprise | `enrich_marche.py` |
| `base_isin_scores.csv` | scores et couverture | `scoring.py` |
| `scoring_params.json` | **pondérations, à éditer** | `scoring.py` |
| `anomalies.csv` | signalements | `anomalies.py` |
| `historique_couverture.csv` | progression | `historique.py` |
| `dashboard.html` | tableau de bord | `dashboard.py` |

Les modules `scripts/scoring.gs` et `scripts/allocation.gs` sont les
transpositions Apps Script, génériques (aucune référence d'enveloppe), à
appeler depuis un `config.gs` d'enveloppe.

---

## 8. Réglages

**Pondérations du score** — `data/scoring_params.json`. Un critère à 0 ou absent
est ignoré ; les critères sans source (`potentiel`, `valorisation`,
`croissance`, `dividende`, `consensus`) y sont déjà déclarés et entreront dans
le calcul dès qu'une source les alimentera, **sans modification du code**.

**Seuils du score** — en tête de `scripts/scoring.py` :
`MIN_CRITERES` (2), `MIN_COUVERTURE_DEFAUT` (30 %), `MIN_POPULATION` (5).

**Seuils d'anomalie** — en tête de `scripts/anomalies.py`.

**Contraintes d'allocation** — `BANDES_SRI`, `PLAFOND_LIGNE`, `MIN_LIGNES` en
tête de `scripts/allocation.py`.

**Fraîcheur** — `--seuil-fraicheur` (7 jours par défaut) sur `dashboard.py`,
`anomalies.py` et `historique.py`.

---

## 9. Problèmes courants

**`Bulk requests are prohibited for free users`** — endpoint bulk EODHD réservé
aux offres payantes. Utiliser `--historique` par lots.

**`usage_limit_reached` (Marketstack)** — quota **mensuel** épuisé. Basculer sur
EODHD : `--source eodhd`.

**Quota EODHD atteint** — 20 requêtes par jour. Vérifier la consommation :

```bash
curl -s "https://eodhd.com/api/user?api_token=$EODHD_API_KEY&fmt=json"
```

Le compteur se remet à zéro le lendemain ; le cache reprend où il s'était arrêté.

**`X indisponible chez le fournisseur`** — le symbole n'existe pas chez cette
source (fréquent pour les petites valeurs). Il est marqué et ne sera plus
réinterrogé. Essayer `--source eodhd`, dont la couverture Euronext est plus large.

**`enrich_pea.py` régénère un fichier différent → CI rouge** — normal si
`pea_emetteurs.csv` ou `base_isin_figi.csv` ont changé. Commiter le fichier
régénéré, ne jamais l'éditer à la main.

**Push refusé (HTTP 403)** — le jeton GitHub n'a pas la permission **Contents:
Read and write**. Vérifier :

```bash
curl -s -o /dev/null -w "%{http_code}\n" -X PUT \
  -H "Authorization: Bearer $GITHUB_TOKEN" \
  "https://api.github.com/repos/FredGarcia/PEAFirst/contents/.permcheck" -d '{}'
```

`422` = droit d'écriture présent (aucune écriture effectuée). `403` = lecture
seule. Attention : le champ `permissions.push` renvoyé par l'API reflète le rôle
du propriétaire, **pas** les droits du jeton.

**Le tableau de bord est vide** — aucune donnée de marché collectée. Lancer
`enrich_marche.py --historique`, puis `scoring.py` et `dashboard.py`.

---

## 10. Ce que la base ne sait pas

À connaître avant de fonder une décision sur ces chiffres.

- **Cinq des sept critères du cahier des charges n'ont aucune source gratuite
  européenne** : potentiel, valorisation (PER), croissance, dividende,
  consensus. Le barème est couvert à environ 60 % : les scores classent sur le
  **risque et la performance passée**, pas sur la valorisation ni les
  perspectives.
- **Aucun champ secteur** dans les listes Euronext : pas de répartition
  sectorielle.
- **Pas de matrice de corrélations** : la volatilité de portefeuille est une
  moyenne pondérée, donc un majorant.
- **L'éligibilité PEA de la plupart des fonds reste à vérifier.** Aucune liste
  officielle n'existe ; seule la fiche de l'émetteur fait foi. Un ETF classé
  `PROBABLE` ou `A_VERIFIER` **doit être vérifié avant tout achat** : acheter un
  titre inéligible dans un PEA entraîne la clôture du plan.
- **La collecte est partielle.** À 18 instruments par jour, couvrir les
  ~1 840 candidats PEA demande environ trois mois. Le tableau de bord affiche
  cette progression plutôt que de la masquer.
- **Les seuils d'anomalie sont empiriques** et produiront des faux positifs sur
  un univers plus large.

_(suite ci-dessous)_

Un accès payant à EODHD ou FMP débloquerait les fondamentaux (PER, croissance,
dividendes) et ferait passer la couverture du barème de 60 % à près de 100 %,
sans modification du code : les critères sont déjà déclarés.


---

## 10bis. L'application PEAdvisor

Le dépôt réunit deux briques : la **chaîne de données** (`scripts/`), décrite
plus haut, et l'**application PEAdvisor** (`peadvisor/`). Cette section couvre
la seconde.

### A. Installation et lancement

```bash
python3 -m venv .venv && source .venv/bin/activate   # recommandé
pip install -r requirements.txt
python run.py
```
> **Sous Windows**, `source` n'existe pas et la commande est `python`, pas
> `python3` : voir [§1bis](#1bis-sous-windows).

### B. Les onze écrans

| Écran | Contenu |
|---|---|
| Tableau de bord | KPI, répartitions par type, secteur et pays, tops, classement multicritère |
| Actions / ETF / OPCVM | référentiel filtrable, colonnes choisies et mémorisées, fiche par actif |
| Allocation | capital, risque 1-7, horizon, objectif → portefeuille sous contraintes |
| Simulateur | versement initial et programmés, trois scénarios, fiscalité PEA, trajectoire |
| Watchlist | suivi de valeurs, ajout et retrait en un clic |
| Historique | journal des traitements et des imports |
| Sources | état de chaque source, bouton **Tester** avec diagnostic |
| Paramètres | pondérations du score, profils de scoring, profil investisseur |
| Système | auto-observation : complétude, fraîcheur, anomalies, dérive des scores, suggestions de pondérations |

### C. Les sources de données

Dix sources branchables, choisies par `source_active` dans
`config/settings.yaml` :

| Source | Clé requise | Couverture | Remarque |
|---|---|---|---|
| **`peafirst`** | non | 371 instruments réels | **défaut** — lit le référentiel de `scripts/`, éligibilité PEA vérifiée, aucun quota |
| `seed` | non | jeu illustratif | hors ligne, pour démonstration |
| `stooq`, `yahoo` | non | variable | non officielles |
| `eodhd`, `marketstack`, `alphavantage`, `twelvedata`, `financialmodelingprep` | oui | voir §2 | quotas gratuits limités |
| `boursorama` | non | scraping | **voir l'avertissement en §10ter** |

**Clés API de l'application** : copier `config/cles_api.exemple.yaml` vers
`config/cles_api.yaml` (gitignoré), ou utiliser les variables d'environnement,
**qui priment**. Ne jamais committer de clé : le dépôt est public.

### D. Ce que la source `peafirst` apporte

| | jeu `seed` | source `peafirst` |
|---|---|---|
| Données | illustratives | réelles, collectées quotidiennement |
| Éligibilité PEA | déclarative | vérifiée : régime foncier, nature de l'instrument, pays, relevés émetteurs, corrections utilisateur |
| Risque | valeur fixe | SRI estimé selon les bornes PRIIPS |
| Réseau | aucun | aucun — la collecte a lieu en amont |

Elle ne remonte que les instruments réellement collectés — **371 sur 6 188** —
car peupler la base de lignes vides donnerait un tableau de bord trompeur. Les
cinq critères sans source européenne gratuite restent **vides plutôt
qu'inventés**, ce qui permet au score de renormaliser ses pondérations sur les
critères présents.

Seul le statut `OUI` vaut éligible : `PROBABLE` et `A_VERIFIER` ne suffisent
pas. Dans le doute, un titre n'est pas présenté comme logeable en PEA.

### E. Paramétrage sans toucher au code

`config/settings.yaml` :

| Section | Ce qu'elle règle |
|---|---|
| `donnees` | source active, PEA-PME, plafond de remplissage initial |
| `mise_a_jour` | planification automatique (APScheduler), fréquence, heure |
| `allocation` | poids maximal par ligne et par secteur, nombre de lignes, part minimale de fonds |
| `quantitatif` | profondeur d'historique, taux sans risque |
| `simulation` | scénarios, volatilité par défaut |
| `fiscalite_pea` | seuil d'exonération, prélèvements sociaux, part IR du PFU |
| `meta` | auto-observation et auto-amélioration |

`config/scoring.yaml` : pondérations et bornes de normalisation du score,
modifiables aussi depuis l'écran **Paramètres** avec recalcul immédiat.

> **Fiscalité.** `prelevements_sociaux_pct` vaut **18,6 %** depuis la LFSS 2026
> (loi n° 2025-1403 du 30 décembre 2025), contre 17,2 % auparavant. Le PFU
> ressort donc à **31,4 %**. Ce réglage est aligné sur `scripts/simulateur.py` :
> les deux simulateurs donnent des montants identiques. Le modifier d'un côté
> sans l'autre les ferait diverger.

### F. L'API REST

49 routes, documentées et testables sur <http://localhost:8000/docs>.
Les principales :

| Domaine | Routes |
|---|---|
| Référentiel | `GET /api/actifs`, `/api/actifs/{isin}`, `/api/actifs/{isin}/cours`, `/api/actifs/{isin}/sous-scores` |
| Import | `POST /api/import`, `GET /api/sources`, `POST /api/sources/{nom}/tester` |
| Décision | `GET /api/dashboard/synthese`, `/api/dashboard/classement`, `/api/dashboard/correlations` |
| Allocation | `POST /api/allocation` |
| Simulation | `POST /api/simulation` |
| Scoring | `GET /api/scoring/criteres`, `PUT /api/parametres/scoring`, `POST /api/scores/recalculer` |
| Watchlist | `GET/POST/DELETE /api/watchlist` |
| Auto-observation | `POST /api/meta/observer`, `GET /api/meta/sante`, `/api/meta/anomalies`, `/api/meta/suggestions` |

### G. Le serveur MCP

`mcp_server.py` expose 18 outils permettant de piloter l'application depuis un
client MCP tel que Claude Desktop : `lister_actifs`, `fiche_actif`,
`synthese_dashboard`, `classement_multicritere`, `correlations`,
`proposer_allocation`, `simuler_investissement`, `consulter_watchlist`,
`gerer_watchlist`, `lancer_mise_a_jour`, `importer_valeur`,
`journal_traitements`, `rapport_systeme`, `lister_anomalies`,
`taux_sans_risque`, `resoudre_isin`, `ponderations_score`,
`optimiser_ponderations`.

Configuration détaillée dans [`docs/08-agent-mcp.md`](08-agent-mcp.md).

### H. Documentation de conception

Héritée de PEAdvisor, elle explique les choix plutôt que l'usage :

| Document | Contenu |
|---|---|
| [01](01-choix-technologiques.md) | pourquoi Python, FastAPI, SQLite ; alternatives écartées |
| [02](02-architecture.md) | architecture en 4 niveaux, flux de données |
| [03](03-modele-donnees.md) | modèle de données |
| [04](04-scoring-et-decision.md) | familles de critères, TOPSIS |
| [05](05-allocation.md) | moteur d'allocation et contraintes |
| [06](06-roadmap.md) | feuille de route |
| [07](07-auto-observation.md) | auto-observation et auto-amélioration |
| [08](08-agent-mcp.md) | serveur MCP |
| [09](09-sources-donnees.md) | sources de données |

### Ajouter une valeur depuis le web

Bouton **Ajouter depuis Boursorama** dans l'Explorateur. Saisir un nom, un ISIN
ou un code ; le bouton *Depuis la sélection* reprend les lignes cochées.

La page **ne scrape rien** : elle prépare la requête, l'application l'exécute.
Trois façons de la lancer :

| Moyen | Condition |
|---|---|
| **Essayer maintenant** | affiche une barre de progression et reporte les résultats dans le tableau. Nécessite que la page soit **servie par l'application** : ouvrir <http://localhost:8000/tableau-de-bord> plutôt que le fichier local, sinon le navigateur bloque l'appel — le message le dit et donne l'adresse |
| **Copier la commande** | `curl -X POST "http://localhost:8000/api/import/web/boursorama/FR0000120073"` — fonctionne toujours dans un terminal, l'application étant lancée |
| **Ouvrir l'API** | formulaire Swagger de la route |

Six sites sont déclarés dans l'application, mais **seul Boursorama est
validé** ; les autres sont proposés en l'état.

**Progression et résultats.** Une valeur sélectionnée par ligne donne une barre
de progression réelle (« Import 2 sur 5 ») ; pour une valeur unique, la barre
reste indéterminée, la durée du scraping n'étant pas connue d'avance. À la fin,
le **potentiel** relevé sur le site est reporté dans la colonne du même nom de
l'Explorateur, à côté du **SRI**.

Les deux jeux de données sont complémentaires, et c'est tout l'intérêt :

| | référentiel `data/` | Boursorama |
|---|---|---|
| SRI, volatilité, drawdown, Sharpe | ✅ calculés sur l'historique | ❌ |
| Potentiel, objectif de cours, consensus, PER, rendement, ESG | ❌ aucune source gratuite | ✅ |

Le SRI affiché reste donc celui du référentiel : le site ne le fournit pas.
L'import ne l'écrase pas.

Trois issues possibles, distinguées dans le compte rendu :

- **potentiel reporté** — la valeur est dans le référentiel et le site publie un
  objectif de cours ;
- **sans potentiel publié** — une petite capitalisation n'a souvent aucun
  objectif d'analyste, la colonne reste vide ;
- **absente du référentiel** — la valeur n'existe que dans la base de
  l'application, à consulter là-bas.

Le potentiel affiché ici vit le temps de la session : il n'est pas écrit dans
`data/`. La valeur importée, elle, reste dans la base de l'application.

> Le scraping de Boursorama se heurte à ses conditions d'utilisation, qui
> interdisent l'extraction automatisée, et à la licence Euronext sur les cours,
> que le site n'a pas le droit de redistribuer.

## 10ter. Deux avertissements sur l'application

**Deux scorings coexistent.** `scripts/scoring.py` produit un classement
reproductible et versionné ; l'application recalcule le sien avec ses propres
familles de critères. Les méthodes sont voisines mais distinctes : **ne pas
confondre leurs résultats**. C'est une dette assumée — deux implémentations
divergent avec le temps.

**Le dépôt contient des scrapers Boursorama**
(`peadvisor/sources/boursorama.py`, routes `/api/import/boursorama/…` et
`/api/import/web/…`), hérités de PEAdvisor. Leur usage se heurte aux conditions
d'utilisation du site, qui interdisent l'extraction automatisée, et à la
licence Euronext sur les cours, que Boursorama n'a pas le droit de
redistribuer. Ils ne sont **pas activés par défaut** : la source active est
`peafirst`. Les conserver, les désactiver ou les retirer est une décision qui
vous revient.

## 11. Simulateur

```bash
python3 scripts/simulateur.py --capital 10000 --versement 500
python3 scripts/simulateur.py --capital 5000 --versement 750 --horizons 5,10 --sequence
python3 scripts/simulateur.py --capital 20000 --enveloppe cto
```

Versements programmés (`--periodicite mensuel|trimestriel|annuel`), horizons de
2 à 10 ans, trois scénarios, frais de gestion et de courtage, inflation, et
fiscalité estimée au retrait.

**Fiscalité appliquée (1er janvier 2026)** — les prélèvements sociaux sont
passés de 17,2 % à 18,6 % (LFSS 2026, loi n° 2025-1403 du 30 décembre 2025) :

| Situation | Taux sur les gains |
|---|---|
| PEA, retrait avant 5 ans | **31,4 %** (12,8 % IR + 18,6 % PS) et clôture du plan |
| PEA, retrait après 5 ans | **18,6 %** (exonération d'IR) |
| Compte-titres | **31,4 %** quelle que soit la durée |

Le taux retenu est celui en vigueur **au moment du retrait**, y compris sur des
gains antérieurs à 2026. Conséquence directe : les horizons de 2 et 3 ans sont
structurellement défavorables en PEA, ce que le simulateur chiffre au lieu de
le passer sous silence.

Les scénarios sont **déterministes** — un rendement annuel constant, paramétrable
dans `SCENARIOS` en tête du script. C'est un choix assumé : une simulation de
Monte-Carlo produirait des percentiles d'allure scientifique reposant sur les
mêmes hypothèses de départ, avec une précision apparente que rien ne justifie.
`--sequence` montre l'essentiel de ce qu'une moyenne masque : à rendement cumulé
identique, l'ordre des rendements change le résultat dès qu'on verse
régulièrement — et des rendements faibles au début sont **favorables** à
l'épargnant, dont les versements achètent plus de parts tant que les cours sont bas.

C'est une projection d'hypothèses, **pas une prévision**.

## 12. Aide-mémoire des actions

### Une seule fois

| Action | Où | Détail |
|---|---|---|
| Ajouter le secret `EODHD_API_KEY` | Settings → Secrets and variables → Actions | [§3bis A](#3bis-actions-initiales) |
| Vérifier **Contents: Read and write** du jeton | Developer settings → Fine-grained tokens | [§3bis B](#3bis-actions-initiales) |
| Exporter les clés dans le shell | `~/.bashrc` | [§3bis C](#3bis-actions-initiales) |

### Sans rien faire

La collecte tourne chaque jour ouvré à 06h15 UTC et publie elle-même les
données, les anomalies, l'historique et le tableau de bord.

### Lancer l'application

```bash
pip install -r requirements.txt
python run.py          # http://localhost:8000
```

### Quand vous le souhaitez

| Envie | Geste |
|---|---|
| Accélérer la collecte | Tableau de bord → **Piloter la collecte** → régler les paramètres → **Ouvrir Run workflow** |
| Rafraîchir les identifiants | Piloter → mode `openfigi` (retraite toute la base et régénère l'éligibilité PEA) |
| Simuler un plan de versements | `simulateur.py --capital … --versement … --periodicite trimestriel` |
| Explorer les pondérations du score | application → écran **Paramètres** (recalcul immédiat) |
| Piloter depuis Claude Desktop | serveur MCP, voir [docs/08](08-agent-mcp.md) |
| Repartir d'une base propre | supprimer `peadvisor.db` et relancer `python run.py` |
| Cibler des instruments précis | Tableau de bord → filtrer → cocher → **File d'attente** → `enrich_marche.py --file-attente` |
| Sortir des données vers Excel | Tableau de bord → filtrer → **Exporter la vue (CSV)** |
| Comparer deux ou trois fonds | Tableau de bord → cocher 2 à 5 lignes |
| Tester une allocation | `allocation.py --capital … --risque … --horizon … --objectif …` |
| Changer les pondérations du score | éditer `data/scoring_params.json`, puis `scoring.py` |
| Confirmer l'éligibilité d'un ETF | fiche de l'émetteur, puis `maj_pea_emetteurs.py --merge` |
| Corriger l'éligibilité d'une action | Tableau de bord → cocher → **Corriger l'éligibilité PEA** → télécharger → `enrich_pea_actions.py` |

### Avant d'acheter

1. Vérifier que `PEA_eligible` vaut **OUI** — un `PROBABLE` ou un `A_VERIFIER`
   doit être confirmé sur la fiche de l'émetteur. Acheter un titre inéligible
   dans un PEA **entraîne la clôture du plan**.
2. Regarder `Couverture_pct` : un score couvert à 60 % ne dit rien de la
   valorisation ni des perspectives.
3. Vérifier l'absence de marqueur d'anomalie sur la ligne.
4. Contrôler l'âge du cours : une donnée périmée fausse tous les indicateurs.

*Aide à la décision — ni conseil en investissement, ni conseil fiscal.*

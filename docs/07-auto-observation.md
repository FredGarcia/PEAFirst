# Couche de second ordre : auto-observation et auto-amélioration

Les niveaux L1-L4 traitent les **actifs** (premier ordre). La couche de second
ordre traite le **système lui-même** : PEAdvisor observe la qualité de ses
propres données et de ses propres prédictions, puis propose — ou applique —
ses propres réglages.

```
        ┌──────────────────────── L5 — Second ordre ────────────────────────┐
        │                                                                   │
        │   Auto-observation  ──────────────►  Auto-amélioration            │
        │   (introspection.py)                 (amelioration.py)            │
        │   qualité, anomalies,                recommandations,             │
        │   pouvoir prédictif                  optimisation des poids       │
        │        ▲                                      │                   │
        └────────┼──────────────────────────────────────┼───────────────────┘
                 │ observe                              │ ajuste (borné,
                 │                                      ▼  journalisé)
        ┌─────── L1-L4 : collecte → analyse → décision → pilotage ──────────┐
        │        données, scoring (config/scoring.yaml), allocation         │
        └───────────────────────────────────────────────────────────────────┘
```

## 1. Auto-observation (`services/introspection.py`)

Un **auto-diagnostic** (bouton de l'écran Système, endpoint
`POST /api/meta/observer`, ou automatiquement après chaque mise à jour
planifiée) produit un rapport persisté (table `rapports_systeme`) :

| Observation | Méthode | Ce qui en découle |
|---|---|---|
| Complétude des données | % de champs renseignés, champ par champ | recommandation si < 60 % |
| Fraîcheur | cours plus vieux que `meta.fraicheur_max_jours` | recommandation de mise à jour |
| Discrimination des critères | écart-type des sous-notes par critère | un critère quasi constant n'apporte rien au classement |
| Incohérences unitaires | règles (PER < 0, ESG hors 0-100, potentiel extrême…) | anomalie **critique** ou **avertissement** |
| Valeurs atypiques | z-score robuste (médiane/MAD) > 3,5 sur PER, rendement, volatilité | anomalie **info** (donnée à vérifier) |
| Dérive de score | variation > `meta.seuil_derive_score` entre deux mises à jour | anomalie **avertissement** |
| Erreurs de traitement | journal des 7 derniers jours | recommandation de vérifier la source |
| **Pouvoir prédictif** | corrélation de Spearman entre scores passés et rendements réalisés | déclenche l'auto-amélioration si faible |

Les anomalies sont dédupliquées (pas de doublon tant qu'une anomalie identique
est ouverte) et gérées dans l'écran **Système** (ignorer / résoudre).

## 2. Auto-amélioration (`services/amelioration.py`)

### Boucle fermée sur le score

La question que le système se pose : *« mes scores d'hier prédisaient-ils les
rendements d'aujourd'hui ? »* — mesurée par la corrélation de rang entre le
score en début de fenêtre d'observation et le rendement réalisé depuis
(`fenetre_observation` : première et dernière entrée de l'historique des
scores de chaque actif).

L'optimiseur (**montée de coordonnées bornée**) cherche des pondérations plus
prédictives :

- exploration par pas de `meta.optimisation.pas` points ;
- **garde-fou** : chaque critère reste à ± `ajustement_max` points de sa
  valeur actuelle — l'auto-amélioration ajuste, elle ne bouleverse pas ;
- **anti-sur-apprentissage** : une suggestion n'est émise que si le gain de
  corrélation dépasse `gain_minimal` et que la fenêtre contient au moins
  5 observations avec des rendements réellement différenciés.

### Supervision humaine par défaut

| Mode | Comportement |
|---|---|
| `auto_appliquer: false` (défaut) | La suggestion est stockée (table `suggestions_ponderations`) avec corrélation avant/après ; l'utilisateur l'**applique ou la rejette** dans l'écran Système |
| `auto_appliquer: true` | Boucle fermée : la suggestion est appliquée après chaque mise à jour planifiée, puis tous les scores sont recalculés |

Chaque application écrit `config/scoring.yaml`, rescore tous les actifs et
laisse une trace dans le journal (`optimisation_ponderations`). L'historique
des suggestions conserve toutes les pondérations successives : revenir en
arrière = réappliquer une ancienne suggestion ou modifier l'écran Paramètres.

### Recommandations non automatisables

Tout ce que le système ne peut pas corriger seul (données manquantes côté
source, critère peu discriminant, imports en échec) devient une
**recommandation** lisible dans le rapport — la partie « améliorer » qui passe
par l'humain.

## 3. API

| Méthode | Route | Rôle |
|---|---|---|
| POST | `/api/meta/observer` | Lancer un auto-diagnostic |
| GET | `/api/meta/sante` | Dernier rapport |
| GET | `/api/meta/anomalies?statut=ouverte` | Anomalies |
| POST | `/api/meta/anomalies/{id}/ignorer` (ou `/resoudre`) | Traiter une anomalie |
| GET | `/api/meta/pouvoir-predictif` | Corrélation score → rendement |
| POST | `/api/meta/optimiser` | Chercher de meilleures pondérations |
| GET | `/api/meta/suggestions` | Historique des suggestions |
| POST | `/api/meta/suggestions/{id}/appliquer` (ou `/rejeter`) | Décision humaine |

## 4. Limites actuelles et évolutions

- La fenêtre d'observation recalcule les scores candidats à partir des
  **sous-notes courantes** (les sous-notes datées ne sont pas encore
  historisées). Précis dès que les historiques de cours seront en place,
  l'approximation est documentée dans le code.
- Avec la source `seed` (cours statiques), le pouvoir prédictif est
  volontairement « non mesurable » — le système le dit lui-même dans son
  rapport. Il devient réel dès qu'une source vivante alimente la base.
- Extensions naturelles : validation croisée temporelle (fenêtres glissantes),
  optimisation par recuit simulé si le nombre de critères augmente, détection
  d'anomalies sur les répartitions du tableau de bord (dérive de l'univers).

"""Auto-observation (couche de second ordre, partie « observer »).

Le système s'observe lui-même et produit un rapport d'auto-diagnostic :

- **complétude** des données, champ par champ ;
- **fraîcheur** des cours (données périmées au-delà d'un seuil) ;
- **discrimination** des critères de score (un critère dont les sous-notes
  sont quasi identiques pour tous les actifs n'apporte rien au classement) ;
- **anomalies** : incohérences unitaires (PER négatif, ESG hors bornes...),
  valeurs statistiquement atypiques (z-score robuste par la MAD) et dérives
  de score entre deux mises à jour ;
- **pouvoir prédictif** : corrélation de rang (Spearman) entre les scores
  passés et les rendements réalisés depuis — la mesure de la qualité réelle
  du score, qui alimente l'auto-amélioration (services/amelioration.py) ;
- **recommandations** d'amélioration lisibles, dérivées de tout ce qui précède.

Chaque diagnostic est persisté (table rapports_systeme) et journalisé.
"""

from __future__ import annotations

import json
import math
import statistics
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from peadvisor.config import charger_settings
from peadvisor.models import Actif, Anomalie, JournalMaj, RapportSysteme
from peadvisor.services.decision import CRITERES
from peadvisor.services.scoring import calculer_score_global

# Liste complète des champs de données suivis pour la complétude (onglet Système).
CHAMPS_SUIVIS = [
    "nom", "isin", "type", "secteur", "devise", "pays", "eligible_pea",
    "cours", "variation_pct", "ouverture", "plus_haut", "plus_bas",
    "cloture_veille", "haut_52s", "bas_52s", "volume", "quantite_echangee",
    "capitalisation", "nb_titres", "per", "rendement", "bna", "dividende",
    "taux_distribution", "dette_nette", "ca", "croissance", "volatilite",
    "niveau_risque", "score_esg", "risque_esg", "objectif_cours", "potentiel",
    "consensus", "nb_analystes", "date_cotation", "score_global", "source",
]
# Sous-ensemble « cœur » : seuls ces champs déclenchent une recommandation si
# faiblement renseignés (les fondamentaux étendus restent souvent partiels).
CHAMPS_CRITIQUES = {"cours", "per", "rendement", "score_esg", "objectif_cours",
                    "consensus", "capitalisation", "secteur"}

# Règles de cohérence unitaires : (type, gravité, prédicat, message)
REGLES_COHERENCE = [
    ("cours_invalide", "critique",
     lambda a: a.cours is not None and a.cours <= 0, "Cours nul ou négatif"),
    ("per_negatif", "avertissement",
     lambda a: a.per is not None and a.per < 0, "PER négatif (résultat déficitaire ou donnée erronée)"),
    ("volatilite_extreme", "avertissement",
     lambda a: a.volatilite is not None and a.volatilite > 80, "Volatilité annualisée > 80 %"),
    ("esg_hors_bornes", "critique",
     lambda a: a.score_esg is not None and not 0 <= a.score_esg <= 100, "Score ESG hors de l'échelle 0-100"),
    ("consensus_hors_bornes", "critique",
     lambda a: a.consensus is not None and not 1 <= a.consensus <= 5, "Consensus hors de l'échelle 1-5"),
    ("potentiel_extreme", "avertissement",
     lambda a: a.potentiel is not None and (a.potentiel > 100 or a.potentiel < -60),
     "Potentiel estimé extrême : objectif de cours ou cours probablement erroné"),
]


# --------------------------------------------------------------------------
# Outils statistiques (sans dépendance externe)
# --------------------------------------------------------------------------

def correlation_spearman(x: list[float], y: list[float]) -> float | None:
    """Corrélation de rang de Spearman (gestion des ex æquo par rang moyen)."""
    n = len(x)
    if n < 3 or len(y) != n:
        return None

    def rangs(valeurs: list[float]) -> list[float]:
        ordre = sorted(range(n), key=lambda i: valeurs[i])
        resultat = [0.0] * n
        i = 0
        while i < n:
            j = i
            while j + 1 < n and valeurs[ordre[j + 1]] == valeurs[ordre[i]]:
                j += 1
            rang_moyen = (i + j) / 2 + 1
            for k in range(i, j + 1):
                resultat[ordre[k]] = rang_moyen
            i = j + 1
        return resultat

    rx, ry = rangs(x), rangs(y)
    mx, my = sum(rx) / n, sum(ry) / n
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    den = math.sqrt(sum((a - mx) ** 2 for a in rx) * sum((b - my) ** 2 for b in ry))
    return round(num / den, 4) if den else None


def _zscores_robustes(valeurs: list[tuple[Actif, float]]) -> list[tuple[Actif, float]]:
    """Z-scores robustes (médiane/MAD) — résistants aux valeurs extrêmes elles-mêmes."""
    if len(valeurs) < 8:
        return []
    nombres = [v for _, v in valeurs]
    mediane = statistics.median(nombres)
    mad = statistics.median([abs(v - mediane) for v in nombres])
    if mad == 0:
        return []
    return [(a, (v - mediane) / (1.4826 * mad)) for a, v in valeurs]


# --------------------------------------------------------------------------
# Fenêtre d'observation : scores passés vs rendements réalisés
# --------------------------------------------------------------------------

def fenetre_observation(session: Session) -> list[dict]:
    """Pour chaque actif : sous-notes, score initial et rendement réalisé
    entre la première et la dernière mise à jour disposant d'un cours."""
    observations = []
    for actif in session.query(Actif).all():
        if not actif.sous_scores:
            continue
        hist = sorted((h for h in actif.historique_scores if h.cours), key=lambda h: h.date)
        if len(hist) < 2 or hist[0].date == hist[-1].date or not hist[0].cours:
            continue
        observations.append({
            "actif": actif,
            "sous_scores": json.loads(actif.sous_scores),
            "score_initial": hist[0].score_global,
            "retour": hist[-1].cours / hist[0].cours - 1,
        })
    return observations


def pouvoir_predictif(session: Session, ponderations: dict[str, float] | None = None) -> dict:
    """Corrélation de Spearman entre score et rendement réalisé.

    Avec `ponderations`, le score est recalculé à partir des sous-notes
    courantes — c'est la fonction objectif de l'auto-amélioration.
    """
    obs = fenetre_observation(session)
    retours = [o["retour"] for o in obs]
    if len(obs) < 5 or len({round(r, 6) for r in retours}) < 2:
        return {"correlation": None, "nb_observations": len(obs),
                "detail": "Historique insuffisant : il faut plusieurs mises à jour "
                          "avec des cours qui évoluent pour mesurer le pouvoir prédictif."}
    if ponderations is None:
        scores = [o["score_initial"] for o in obs]
    else:
        cfg = {"ponderations": ponderations, "note_donnee_manquante": 50}
        scores = [calculer_score_global(o["sous_scores"], cfg) for o in obs]
    return {"correlation": correlation_spearman(scores, retours),
            "nb_observations": len(obs),
            "detail": "Corrélation de rang entre le score en début de fenêtre et le rendement réalisé."}


# --------------------------------------------------------------------------
# Détection d'anomalies
# --------------------------------------------------------------------------

def _signaler(session: Session, nouvelles: list[Anomalie], actif_id: int | None,
              type_: str, gravite: str, message: str) -> None:
    """Crée l'anomalie sauf si une anomalie ouverte identique existe déjà."""
    deja = session.query(Anomalie).filter(
        Anomalie.actif_id == actif_id, Anomalie.type == type_,
        Anomalie.statut == "ouverte").count()
    if not deja:
        anomalie = Anomalie(actif_id=actif_id, type=type_, gravite=gravite,
                            message=message, statut="ouverte")
        session.add(anomalie)
        nouvelles.append(anomalie)


def detecter_anomalies(session: Session, cfg_meta: dict) -> list[Anomalie]:
    actifs = session.query(Actif).all()
    nouvelles: list[Anomalie] = []

    # 1. Règles de cohérence unitaires.
    for a in actifs:
        for type_, gravite, predicat, message in REGLES_COHERENCE:
            if predicat(a):
                _signaler(session, nouvelles, a.id, type_, gravite, f"{a.nom} : {message}")

    # 2. Valeurs statistiquement atypiques (z-score robuste > 3,5).
    for champ in ("per", "rendement", "volatilite"):
        valeurs = [(a, getattr(a, champ)) for a in actifs if getattr(a, champ) is not None]
        for a, z in _zscores_robustes(valeurs):
            if abs(z) > 3.5:
                _signaler(session, nouvelles, a.id, f"atypique_{champ}", "info",
                          f"{a.nom} : {champ} = {getattr(a, champ)} très éloigné du reste "
                          f"de l'univers (z robuste {z:.1f}) — donnée à vérifier")

    # 3. Dérive de score entre les deux dernières mises à jour.
    seuil_derive = float(cfg_meta.get("seuil_derive_score", 20))
    for a in actifs:
        hist = sorted(a.historique_scores, key=lambda h: h.date)
        if len(hist) >= 2:
            delta = hist[-1].score_global - hist[-2].score_global
            if abs(delta) >= seuil_derive:
                _signaler(session, nouvelles, a.id, "derive_score", "avertissement",
                          f"{a.nom} : score passé de {hist[-2].score_global:.0f} à "
                          f"{hist[-1].score_global:.0f} — vérifier les données sous-jacentes")

    session.commit()
    return nouvelles


# --------------------------------------------------------------------------
# Rapport d'auto-diagnostic
# --------------------------------------------------------------------------

def observer(session: Session) -> dict:
    """Exécute un cycle complet d'auto-observation, persiste et renvoie le rapport."""
    settings = charger_settings()
    cfg_meta = settings.get("meta", {})
    actifs = session.query(Actif).all()
    recommandations: list[str] = []

    # Complétude, champ par champ.
    completude: dict[str, float] = {}
    for champ in CHAMPS_SUIVIS:
        renseignes = sum(1 for a in actifs if getattr(a, champ) is not None)
        completude[champ] = round(renseignes / len(actifs) * 100, 1) if actifs else 0.0
        if actifs and champ in CHAMPS_CRITIQUES and completude[champ] < 60:
            recommandations.append(
                f"Le champ « {champ} » n'est renseigné que pour {completude[champ]:.0f} % des actifs : "
                "compléter la source de données ou en brancher une plus riche.")
    completude_globale = round(sum(completude.values()) / len(completude), 1) if completude else 0.0

    # Fraîcheur des cours.
    limite = datetime.utcnow() - timedelta(days=int(cfg_meta.get("fraicheur_max_jours", 7)))
    perimes = [a for a in actifs if a.date_cours and a.date_cours < limite]
    if perimes:
        recommandations.append(
            f"{len(perimes)} actif(s) ont un cours de plus de "
            f"{cfg_meta.get('fraicheur_max_jours', 7)} jours : lancer une mise à jour "
            "ou activer la planification automatique (mise_a_jour.automatique).")

    # Discrimination des critères de score.
    seuil_disc = float(cfg_meta.get("seuil_discrimination", 5))
    discrimination: dict[str, float | None] = {}
    for critere in CRITERES:
        notes = []
        for a in actifs:
            if a.sous_scores:
                note = json.loads(a.sous_scores).get(critere)
                if note is not None:
                    notes.append(note)
        ecart = round(statistics.pstdev(notes), 1) if len(notes) >= 2 else None
        discrimination[critere] = ecart
        if ecart is not None and ecart < seuil_disc:
            recommandations.append(
                f"Le critère « {critere} » est peu discriminant (écart-type {ecart}) : "
                "élargir ses bornes de normalisation ou réduire sa pondération.")

    # Erreurs d'import récentes.
    depuis = datetime.utcnow() - timedelta(days=7)
    erreurs_imports = session.query(JournalMaj).filter(
        JournalMaj.date >= depuis, JournalMaj.statut == "erreur").count()
    if erreurs_imports:
        recommandations.append(
            f"{erreurs_imports} traitement(s) en erreur sur 7 jours : consulter le journal "
            "et vérifier la source de données (réseau, quotas).")

    # Anomalies et pouvoir prédictif.
    nouvelles = detecter_anomalies(session, cfg_meta)
    ouvertes = session.query(Anomalie).filter(Anomalie.statut == "ouverte").count()
    if ouvertes:
        recommandations.append(
            f"{ouvertes} anomalie(s) ouverte(s) : les traiter dans l'écran Système "
            "(corriger la donnée à la source ou marquer comme ignorée).")
    predictif = pouvoir_predictif(session)
    if predictif["correlation"] is not None and predictif["correlation"] < 0.1:
        recommandations.append(
            f"Le score prédit mal les rendements observés (corrélation "
            f"{predictif['correlation']:.2f}) : lancer l'optimisation des pondérations "
            "dans l'écran Système.")

    rapport = {
        "date": datetime.utcnow().isoformat(),
        "nb_actifs": len(actifs),
        "completude_globale_pct": completude_globale,
        "completude_par_champ": completude,
        "actifs_cours_perimes": len(perimes),
        "discrimination_criteres": discrimination,
        "imports_en_erreur_7j": erreurs_imports,
        "anomalies_nouvelles": len(nouvelles),
        "anomalies_ouvertes": ouvertes,
        "pouvoir_predictif": predictif,
        "recommandations": recommandations,
    }

    session.add(RapportSysteme(contenu=json.dumps(rapport, ensure_ascii=False)))
    session.add(JournalMaj(
        traitement="auto-diagnostic", statut="succes",
        detail=f"Complétude {completude_globale:.0f} %, {len(nouvelles)} anomalie(s) nouvelle(s), "
               f"{ouvertes} ouverte(s), {len(recommandations)} recommandation(s).",
        nb_crees=0, nb_maj=0, nb_doublons=0, nb_erreurs=0))
    session.commit()
    return rapport


def dernier_rapport(session: Session) -> dict | None:
    dernier = session.query(RapportSysteme).order_by(RapportSysteme.date.desc()).first()
    return json.loads(dernier.contenu) if dernier else None

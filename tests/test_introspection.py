import json
from datetime import datetime, timedelta

from peadvisor.models import Actif, Anomalie, HistoriqueScore, TypeActif
from peadvisor.services.importer import importer
from peadvisor.services.introspection import (
    correlation_spearman,
    detecter_anomalies,
    observer,
    pouvoir_predictif,
)


def test_spearman():
    assert correlation_spearman([1, 2, 3, 4], [10, 20, 30, 40]) == 1.0
    assert correlation_spearman([1, 2, 3, 4], [40, 30, 20, 10]) == -1.0
    assert correlation_spearman([1, 2], [1, 2]) is None  # trop peu de points


def test_detection_anomalies_coherence(session):
    importer(session, "seed")
    actif = session.query(Actif).first()
    actif.per = -12.0          # règle per_negatif
    actif.consensus = 9.0      # règle consensus_hors_bornes
    session.commit()

    nouvelles = detecter_anomalies(session, {})
    types = {a.type for a in nouvelles}
    assert "per_negatif" in types
    assert "consensus_hors_bornes" in types

    # Idempotence : une anomalie ouverte identique n'est pas dupliquée.
    assert not {a.type for a in detecter_anomalies(session, {})} & types
    assert session.query(Anomalie).filter(Anomalie.type == "per_negatif").count() == 1


def test_detection_derive_score(session):
    importer(session, "seed")
    actif = session.query(Actif).first()
    session.add(HistoriqueScore(actif_id=actif.id, score_global=(actif.score_global or 50) + 40,
                                cours=actif.cours, date=datetime.utcnow() + timedelta(minutes=1)))
    session.commit()
    nouvelles = detecter_anomalies(session, {"seuil_derive_score": 20})
    assert any(a.type == "derive_score" for a in nouvelles)


def test_observer_produit_un_rapport(session):
    importer(session, "seed")
    rapport = observer(session)
    assert rapport["nb_actifs"] > 0
    assert 0 < rapport["completude_globale_pct"] <= 100
    assert "recommandations" in rapport
    # Le pouvoir prédictif est inconnu tant que les cours n'ont pas évolué.
    assert rapport["pouvoir_predictif"]["correlation"] is None


def _fabriquer_historique(session, jours=30):
    """Historique synthétique : les rendements suivent la sous-note dividende."""
    for i, actif in enumerate(session.query(Actif).all()):
        sous = json.loads(actif.sous_scores)
        rendement_realise = (sous.get("dividende") or 0) / 100 + (i % 3) * 0.001
        debut = datetime.utcnow() - timedelta(days=jours)
        session.add(HistoriqueScore(actif_id=actif.id, date=debut,
                                    score_global=actif.score_global, cours=100.0))
        session.add(HistoriqueScore(actif_id=actif.id, date=datetime.utcnow(),
                                    score_global=actif.score_global,
                                    cours=100.0 * (1 + rendement_realise)))
    session.commit()


def test_pouvoir_predictif_avec_historique(session):
    importer(session, "seed")
    _fabriquer_historique(session)
    resultat = pouvoir_predictif(session)
    assert resultat["correlation"] is not None
    assert resultat["nb_observations"] >= 5
    # Pondérations 100 % dividende → corrélation quasi parfaite avec ces rendements.
    force = pouvoir_predictif(session, {"dividende": 100})
    assert force["correlation"] > 0.9

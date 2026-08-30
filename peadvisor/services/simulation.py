"""Simulateur d'investissement (niveau L3 — Décision).

Projette la valeur d'un investissement PEA dans le temps :

- versement initial et versements mensuels programmés ;
- rendement décomposé en appréciation du cours et rendement du dividende,
  avec ou sans réinvestissement des dividendes ;
- trois scénarios (prudent / médian / optimiste) dont l'écart de rendement
  annuel se resserre avec l'horizon (dispersion annualisée ≈ volatilité /
  racine(horizon)) ;
- fiscalité PEA estimée : après le seuil de détention, gains exonérés d'impôt
  sur le revenu (seuls les prélèvements sociaux s'appliquent) ; avant, PFU.

Tous les paramètres fiscaux et de scénario sont dans config/settings.yaml.
Résultat volontairement pédagogique — estimation, pas un conseil fiscal.
"""

from __future__ import annotations

import math

from peadvisor.config import charger_settings
from peadvisor.schemas import DemandeSimulation, ReponseSimulation, ScenarioSimulation


def _trajectoire(capital0: float, versement: float, horizon: int,
                 taux_prix_pct: float, taux_div_pct: float, reinvestir: bool):
    """Simule mois par mois. Renvoie (valeur_finale, dividendes_percus,
    versements_cumules, trajectoire annuelle)."""
    # Le dividende ne gonfle le capital que s'il est réinvesti.
    taux_total = taux_prix_pct + (taux_div_pct if reinvestir else 0.0)
    r_m = (1 + taux_total / 100) ** (1 / 12) - 1
    div_m = 0.0 if reinvestir else (1 + taux_div_pct / 100) ** (1 / 12) - 1

    capital = capital0
    dividendes = 0.0
    versements = capital0
    trajectoire = [{"annee": 0, "versements_cumules": round(capital0, 2),
                    "valeur": round(capital0, 2)}]
    for mois in range(1, horizon * 12 + 1):
        if not reinvestir:
            dividendes += capital * div_m  # dividende versé, non capitalisé
        capital = capital * (1 + r_m) + versement
        versements += versement
        if mois % 12 == 0:
            trajectoire.append({
                "annee": mois // 12,
                "versements_cumules": round(versements, 2),
                "valeur": round(capital + dividendes, 2),
            })
    return capital + dividendes, dividendes, versements, trajectoire


def _fiscalite(plus_value: float, horizon: int, cfg: dict) -> tuple[float, str, bool]:
    """Impôt estimé sur la plus-value selon la durée de détention (PEA)."""
    # Défaut aligné sur la LFSS 2026 ; la valeur reste paramétrable dans
    # config/settings.yaml, la fiscalité changeant régulièrement.
    ps = cfg.get("prelevements_sociaux_pct", 18.6) / 100
    pfu_ir = cfg.get("pfu_impot_pct", 12.8) / 100
    seuil = cfg.get("seuil_exoneration_ir_annees", 5)
    if plus_value <= 0:
        return 0.0, "aucune plus-value imposable", horizon >= seuil
    if horizon >= seuil:
        return round(plus_value * ps, 2), f"exonéré d'IR après {seuil} ans, prélèvements sociaux {ps*100:.1f} %", True
    return round(plus_value * (ps + pfu_ir), 2), \
        f"retrait avant {seuil} ans : PFU {(ps+pfu_ir)*100:.1f} %", False


def _scenario(nom: str, capital0: float, versement: float, horizon: int,
              taux_prix_pct: float, taux_div_pct: float, reinvestir: bool,
              cfg_fiscal: dict) -> ScenarioSimulation:
    valeur, dividendes, versements, trajectoire = _trajectoire(
        capital0, versement, horizon, taux_prix_pct, taux_div_pct, reinvestir)
    plus_value = valeur - versements
    impot, regime, exonere = _fiscalite(plus_value, horizon, cfg_fiscal)
    return ScenarioSimulation(
        nom=nom,
        rendement_annuel_pct=round(taux_prix_pct + (taux_div_pct if reinvestir else 0.0), 2),
        versements_cumules=round(versements, 2),
        valeur_finale_brute=round(valeur, 2),
        plus_value_brute=round(plus_value, 2),
        dividendes_percus=round(dividendes, 2),
        impot_estime=impot,
        valeur_finale_nette=round(valeur - impot, 2),
        regime_fiscal=regime,
        exonere_ir=exonere,
        trajectoire=trajectoire,
    )


def simuler(demande: DemandeSimulation) -> ReponseSimulation:
    settings = charger_settings()
    cfg_sim = settings.get("simulation", {})
    cfg_fiscal = settings.get("fiscalite_pea", {})

    volatilite = demande.volatilite_pct
    if volatilite is None:
        volatilite = float(cfg_sim.get("volatilite_defaut_pct", 15.0))
    coef = float(cfg_sim.get("coefficient_scenario", 1.0))

    # Dispersion annualisée du rendement sur l'horizon.
    ecart = coef * volatilite / math.sqrt(demande.horizon_annees)

    def scenario(nom, delta):
        return _scenario(nom, demande.capital_initial, demande.versement_mensuel,
                         demande.horizon_annees, demande.rendement_prix_pct + delta,
                         demande.rendement_dividende_pct, demande.reinvestir_dividendes,
                         cfg_fiscal)

    scenarios = {
        "prudent": scenario("prudent", -ecart),
        "median": scenario("médian", 0.0),
        "optimiste": scenario("optimiste", +ecart),
    }

    med = scenarios["median"]
    commentaire = (
        f"Sur {demande.horizon_annees} ans, {med.versements_cumules:,.0f} € versés → "
        f"scénario médian {med.valeur_finale_nette:,.0f} € net "
        f"({med.regime_fiscal}). Écart de rendement des scénarios : ±{ecart:.1f} pts "
        f"(volatilité {volatilite:.0f} %). Estimation indicative, pas un conseil "
        "en investissement ni fiscal."
    ).replace(",", " ")

    return ReponseSimulation(
        capital_initial=demande.capital_initial,
        versement_mensuel=demande.versement_mensuel,
        horizon_annees=demande.horizon_annees,
        reinvestir_dividendes=demande.reinvestir_dividendes,
        ecart_scenario_pct=round(ecart, 2),
        scenarios=scenarios,
        commentaire=commentaire,
    )

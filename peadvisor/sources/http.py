"""Socle commun des sources de données HTTP (AlphaVantage, TwelveData, FMP,
EODHD, Marketstack, Stooq...).

Chaque connecteur ne définit que trois choses :
- la conversion du mnémonique vers le symbole propre à l'API (`symbole`) ;
- la récupération d'une cotation (`cotation`) — champs à fusionner dans la
  fiche de l'actif ;
- la récupération de la série de clôtures quotidiennes (`serie`) — qui
  alimente le moteur quantitatif.

Le socle gère le reste : univers de référence (fiches seed SANS l'historique
synthétique — une source réelle ne doit jamais faire passer des données de
démonstration pour du réel), clé API (variable d'environnement prioritaire,
sinon config/cles_api.yaml), pause entre requêtes (quotas), repli sur la
fiche locale en cas d'erreur, et fonction `tester()` utilisée par le bouton
« Tester » de l'écran Sources.
"""

from __future__ import annotations

import time
from typing import Any

import requests

from peadvisor.config import cle_api
from peadvisor.sources.base import SourceDonnees
from peadvisor.sources.seed import SourceSeed


def univers_de_base() -> list[dict[str, Any]]:
    """Fiches de référence des actifs, sans l'historique synthétique."""
    actifs = SourceSeed().recuperer()
    for actif in actifs:
        actif.pop("historique", None)
    return actifs


class SourceHTTPBase(SourceDonnees):
    nom = "http"
    nom_cle: str | None = None        # entrée dans config/cles_api.yaml
    variable_env: str | None = None   # variable d'environnement (prioritaire)
    necessite_cle: bool = True
    pause_s: float = 0.2              # pause entre requêtes (quotas API)
    TICKER_TEST = "TTE"               # TotalEnergies, présent partout

    # --- À implémenter par chaque connecteur -----------------------------

    def symbole(self, ticker: str) -> str:
        """Convertit le mnémonique Euronext Paris vers le format de l'API."""
        return ticker if "." in ticker else f"{ticker}.PA"

    def cotation(self, symbole: str, cle: str | None) -> dict[str, Any]:
        """Champs à fusionner dans la fiche (cours, per, rendement...)."""
        return {}

    def serie(self, symbole: str, cle: str | None) -> list[dict[str, Any]]:
        """Clôtures quotidiennes : liste de {"date": "YYYY-MM-DD", "cours": x}."""
        return []

    # --- Comportement commun ---------------------------------------------

    def _cle(self) -> str | None:
        return cle_api(self.nom_cle, self.variable_env)

    def _get_json(self, url: str, params: dict | None = None):
        reponse = requests.get(url, params=params, timeout=20)
        reponse.raise_for_status()
        return reponse.json()

    @staticmethod
    def _message_reponse(reponse) -> str:
        """Message lisible extrait du corps d'une réponse (JSON ou texte).

        Les API renvoient leur raison réelle dans le corps (quota dépassé,
        symbole introuvable, plan payant requis…) — on l'expose plutôt que le
        code HTTP nu.
        """
        if reponse is None:
            return ""
        try:
            data = reponse.json()
        except Exception:
            return (reponse.text or "").strip()[:200]
        if isinstance(data, dict):
            for cle in ("message", "error", "Error Message", "detail", "note",
                        "Note", "Information", "info", "status_message"):
                if data.get(cle):
                    return str(data[cle])[:200]
            return str(data)[:200]
        return str(data)[:200]

    def recuperer(self) -> list[dict[str, Any]]:
        cle = self._cle()
        if self.necessite_cle and not cle:
            raise RuntimeError(
                f"La source '{self.nom}' nécessite une clé API : renseigner la variable "
                f"d'environnement {self.variable_env} ou l'entrée '{self.nom_cle}' "
                "dans config/cles_api.yaml"
            )
        resultats: list[dict[str, Any]] = []
        for actif in univers_de_base():
            ticker = actif.get("mnemonique")
            if not ticker or actif.get("type") == "OPCVM":
                resultats.append(actif)  # OPCVM non cotés : fiche locale conservée
                continue
            symbole = self.symbole(ticker)
            maj = dict(actif)
            try:
                maj.update({k: v for k, v in self.cotation(symbole, cle).items() if v is not None})
            except Exception:
                pass  # cotation indisponible : la fiche locale reste valable
            try:
                points = self.serie(symbole, cle)
                if points:
                    maj["historique"] = points
            except Exception:
                pass  # sans historique, l'actif reste exploitable
            resultats.append(maj)
            if self.pause_s:
                time.sleep(self.pause_s)
        return resultats

    def tester(self) -> dict[str, Any]:
        """Teste la source sur un titre (bouton « Tester » de l'écran Sources)."""
        cle = self._cle()
        if self.necessite_cle and not cle:
            return {"ok": False,
                    "erreur": f"Clé absente : définir {self.variable_env} ou "
                              f"'{self.nom_cle}' dans config/cles_api.yaml"}
        symbole = self.symbole(self.TICKER_TEST)
        resultat: dict[str, Any] = {"ok": False, "symbole_teste": symbole}
        try:
            cotation = self.cotation(symbole, cle)
            resultat["cotation"] = cotation or None
            points = self.serie(symbole, cle)
            resultat["points_historique"] = len(points)
            resultat["ok"] = bool(cotation) or bool(points)
            if not resultat["ok"]:
                resultat["erreur"] = ("Réponse vide : symbole non couvert par la source ou "
                                      "par votre plan, quota atteint, ou format de symbole à ajuster")
        except requests.HTTPError as exc:
            # On expose le message réel de l'API (raison du refus), pas le code nu.
            code = exc.response.status_code if exc.response is not None else "?"
            detail = self._message_reponse(exc.response)
            aide = {402: " — donnée réservée à un plan payant",
                    403: " — accès refusé (souvent : exchange hors offre gratuite)",
                    404: " — symbole introuvable pour cette source/ce plan",
                    429: " — quota dépassé, réessayer plus tard"}.get(code, "")
            resultat["erreur"] = f"HTTP {code}{aide}" + (f" : {detail}" if detail else "")
        except Exception as exc:
            resultat["erreur"] = f"{type(exc).__name__} : {exc}"
        return resultat

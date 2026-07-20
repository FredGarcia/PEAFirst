"""Connecteurs de données (niveau L1 — Collecte).

Chaque source implémente `SourceDonnees.recuperer()` et renvoie une liste de
dictionnaires normalisés (fiche + historique de cours éventuel). Pour ajouter
une source HTTP, hériter de `SourceHTTPBase` (peadvisor/sources/http.py) et
l'enregistrer dans REGISTRE. Étude comparative des sources envisageables :
docs/09-sources-donnees.md.
"""

from peadvisor.sources.alphavantage import SourceAlphaVantage
from peadvisor.sources.base import SourceDonnees
from peadvisor.sources.boursorama import SourceBoursorama
from peadvisor.sources.eodhd import SourceEODHD
from peadvisor.sources.financialmodelingprep import SourceFinancialModelingPrep
from peadvisor.sources.marketstack import SourceMarketstack
from peadvisor.sources.seed import SourceSeed
from peadvisor.sources.stooq import SourceStooq
from peadvisor.sources.twelvedata import SourceTwelveData
from peadvisor.sources.yahoo import SourceYahoo

REGISTRE: dict[str, type[SourceDonnees]] = {
    "seed": SourceSeed,
    "stooq": SourceStooq,
    "yahoo": SourceYahoo,
    "alphavantage": SourceAlphaVantage,
    "twelvedata": SourceTwelveData,
    "financialmodelingprep": SourceFinancialModelingPrep,
    "eodhd": SourceEODHD,
    "marketstack": SourceMarketstack,
    "boursorama": SourceBoursorama,
}

# Instructions pour les assistants de code

Ce dépôt réunit deux briques qu'il ne faut pas confondre.

## `scripts/` — chaîne de données

- **Aucune dépendance externe** : bibliothèque standard uniquement. Ne jamais y
  introduire d'import tiers ; `validate.yml` s'exécute sans installer quoi que
  ce soit, exprès.
- Français partout : noms de variables, commentaires, messages, docstrings.
- `data/base_isin.csv` a **exactement 11 colonnes** et les sous-fichiers
  actions/ETF/OPCVM doivent lui être strictement identiques ligne à ligne.
  `validate_base.py` échoue sinon.
- `data/base_isin_fonds_pea.csv` est **régénéré** par la CI et comparé au
  fichier commité : ne jamais l'éditer à la main, passer par `enrich_pea.py`.
- Toute collecte doit être **reprenable** : cache sur disque, arrêt propre sur
  quota, symboles indisponibles marqués une fois pour toutes. Les quotas
  gratuits sont la contrainte structurante (EODHD 20/jour, Marketstack
  100/mois).

## `peadvisor/` — application FastAPI

- Dépendances déclarées dans `requirements.txt`.
- Les données entrent par le **registre de sources**
  (`peadvisor/sources/__init__.py`). Pour ajouter une source, implémenter
  `SourceDonnees.recuperer()` — ne pas contourner l'importeur.
- La source `peafirst` lit le référentiel produit par `scripts/` : c'est le
  seul point de jonction entre les deux briques.
- Tout changement de comportement doit être couvert par un test dans `tests/`.

## Règles communes

- **Ne jamais committer de secret.** `config/cles_api.yaml` et `.keys/` sont
  ignorés ; le dépôt est public.
- **Ne jamais inventer une donnée absente.** Un critère sans source reste
  `None` et les pondérations se renormalisent sur les critères présents. Une
  valeur par défaut silencieuse est un bug, pas une commodité.
- **L'éligibilité PEA est un sujet à risque.** Seul le statut `OUI` vaut
  éligible ; `PROBABLE` et `A_VERIFIER` ne suffisent pas. Loger un titre
  inéligible dans un PEA entraîne la clôture du plan. Les foncières à régime
  transparent (SIIC, SOCIMI, SIR, FBI, SIIQ, G-REIT, UK-REIT) sont exclues
  depuis le 21 octobre 2011.
- **La fiscalité est datée et paramétrable.** Prélèvements sociaux à 18,6 %
  depuis la LFSS 2026. Le taux figure dans `config/settings.yaml` et dans
  `scripts/simulateur.py` : modifier l'un sans l'autre les ferait diverger.
- Les scores et allocations sont une **aide à la décision**, jamais un conseil
  en investissement. Conserver les avertissements existants.

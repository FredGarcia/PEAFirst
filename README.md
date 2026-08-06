# PEAFirst — Base ISIN

Base d'identifiants ISIN pour le projet PEA Advisor, construite depuis les listes officielles Euronext (toutes places : Paris, Amsterdam, Bruxelles, Lisbonne, Oslo, Milan, Dublin…).

## Fichiers

| Fichier | Contenu |
|---|---|
| `data/base_isin.csv` | Base consolidée dédoublonnée (6 188 ISIN) |
| `data/base_isin_actions.csv` | Actions (2 798) |
| `data/base_isin_etf.csv` | ETF (3 232) |
| `data/base_isin_opcvm.csv` | OPCVM (158) |

## Colonnes

`ISIN;Nom;Symbole;Type;Marché(s);Devise;Pays_émission;PEA_indicatif;ESG_classification;Source;Date_MAJ`

- Séparateur : `;` — encodage UTF-8.
- Les multi-cotations sont agrégées dans `Marché(s)` (séparateur ` | `).

## Éligibilité PEA (`PEA_indicatif`)

Règle par préfixe pays de l'ISIN (UE/EEE incluant NO, IS, LI) :
- **Actions** : règle fiable (siège dans l'EEE).
- **ETF/OPCVM** : indicatif seulement. Un fonds domicilié IE/LU n'est éligible PEA que s'il respecte le quota de 75 % d'actions UE (réplication physique ou synthétique). Un enrichissement dédié est nécessaire pour fiabiliser cette colonne.

## Pipeline de mise à jour

1. Télécharger les listes Euronext (actions, ETF, fonds).
2. Dédoublonner par ISIN, agréger les places de cotation.
3. Calculer `PEA_indicatif` par règle métier.
4. (À venir) Enrichir via OpenFIGI : FIGI, ticker exact, type d'instrument.
5. (À venir) Croiser les listes émetteurs ETF (Amundi, iShares, BNP) pour l'éligibilité PEA réelle.

*Données à usage d'aide à la décision uniquement — ni conseil en investissement, ni conseil fiscal.*

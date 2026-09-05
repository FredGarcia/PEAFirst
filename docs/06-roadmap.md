# Roadmap et état d'avancement

## Critères de réussite du cahier des charges (§12)

| Critère | État |
| --- | --- |
| Données récupérées automatiquement depuis des sources autorisées | 🟡 Architecture de sources branchables en place ; `seed` (démo) et `yahoo` (best effort) livrées ; source professionnelle à brancher |
| Doublons éliminés | ✅ Dédoublonnage par ISIN + comptage des doublons intra-lot |
| Indicateurs calculés automatiquement | ✅ Sous-notes, score global, potentiel, niveau de risque à chaque import |
| Allocations générées selon les paramètres utilisateur | ✅ Capital / risque 1-7 / horizon / objectif |
| Tableau de bord opérationnel | ✅ KPI, répartitions, tops, matrice TOPSIS |
| Ensemble documenté, maintenable, extensible | ✅ docs/, code commenté, tests, paramétrage YAML |

## Prochaines étapes proposées (par ordre de valeur)

1. **Source de données réelle** — brancher un fournisseur fiable (EOD
   Historical Data, Euronext…) et constituer le référentiel complet des valeurs
   éligibles PEA. C'est le prérequis de tout le reste.

2. ~~**Historiques de cours**~~ — ✅ fait : table `historique_cours`
   (append-only, dédoublonnée par date), séries synthétiques côté `seed` et
   réelles côté `yahoo`, moteur quantitatif complet (volatilité réalisée
   intégrée au scoring, perf 1 an, drawdown, Sharpe, Sortino, VaR 95 %,
   corrélations exposées dans l'API, l'interface et l'agent MCP).

3. ~~**Simulateur d'investissement**~~ — ✅ fait : versement initial +
   versements programmés, réinvestissement des dividendes, trois scénarios
   (écart annualisé ∝ volatilité / racine(horizon)), **fiscalité PEA**
   estimée (exonération d'IR après 5 ans, PFU avant), trajectoire graphique,
   exposé dans l'interface, l'API et l'agent MCP.

4. **Exports** Excel / CSV / PDF des listes, classements et allocations.
5. **Alertes** — franchissement de score, de potentiel ou d'objectif de cours
   sur la watchlist (e-mail).

6. **Import du portefeuille existant** + comparaison allocation cible vs réelle.
7. **Méthodes multicritères supplémentaires** — AHP, PROMETHEE, ELECTRE.
8. **Optimisation de portefeuille** (Markowitz, parité de risque) une fois les
   corrélations disponibles.

9. **Backtesting** de stratégies sur les historiques.
10. **Authentification + PostgreSQL** si passage en multi-utilisateurs / hébergé.
11. **Moteur IA** — résumé forces/faiblesses d'un actif, détection d'anomalies,
    explication des recommandations (API Claude, par exemple).

## Évolutions listées au cahier des charges non encore couvertes

Optimisation fiscale (PEA / CTO / assurance-vie), rééquilibrage automatique,
connexion courtier, indicateurs techniques (RSI, MACD, moyennes mobiles),
comparaison de portefeuilles multiples : à planifier après les étapes 1-2 qui
en sont les prérequis.

#!/usr/bin/env python3
"""Tableau de bord de la base et matrice de décision multicritère.

Produit data/dashboard.html, page autonome consultable hors ligne.

Parti pris : ce tableau de bord montre autant ce qui est mesuré que ce qui ne
l'est pas. Les indicateurs du cahier des charges sans source disponible ne sont
pas dissimulés — ils sont listés avec leur motif. Un tableau de bord qui
n'afficherait que les cases remplies laisserait croire que la base est complète.

Inclut la matrice multicritère TOPSIS demandée par le cahier des charges :
classement par distance à la solution idéale, méthode indépendante du score
pondéré, ce qui permet de croiser deux approches sur le même univers.

Usage :
  python3 scripts/dashboard.py
  python3 scripts/dashboard.py --top 15
"""
import argparse
import csv
import html
import math
import sys
from collections import Counter
from datetime import date
from pathlib import Path

# Critères TOPSIS : champ -> (poids, bénéfice ?). Un critère « bénéfice » est à
# maximiser, sinon à minimiser.
TOPSIS_CRITERES = {
    "Perf_periode_pct": (0.30, True),
    "Sharpe": (0.25, True),
    "Volatilite_annualisee_pct": (0.20, False),
    "Drawdown_max_pct": (0.15, True),   # valeurs négatives : -5 % vaut mieux que -40 %
    "Sortino": (0.10, True),
}

PAYS = {
    "FR": "France", "IE": "Irlande", "LU": "Luxembourg", "NL": "Pays-Bas",
    "BE": "Belgique", "DE": "Allemagne", "IT": "Italie", "ES": "Espagne",
    "PT": "Portugal", "NO": "Norvège", "GB": "Royaume-Uni", "US": "États-Unis",
    "FI": "Finlande", "SE": "Suède", "DK": "Danemark", "AT": "Autriche",
    "CH": "Suisse", "CA": "Canada", "JE": "Jersey", "GG": "Guernesey",
    "XS": "International", "AN": "Antilles nl.", "BM": "Bermudes",
}

# Indicateurs prévus au cahier des charges qu'aucune source gratuite
# n'alimente aujourd'hui. Affichés pour que l'absence soit lisible.
NON_ALIMENTES = [
    ("Répartition sectorielle", "aucun champ secteur dans les listes Euronext"),
    ("Rendement moyen", "dividendes européens indisponibles en gratuit"),
    ("Potentiel moyen", "objectifs de cours réservés aux offres payantes"),
    ("Top dividendes", "dividendes européens indisponibles en gratuit"),
    ("Top croissance", "données de croissance indisponibles en gratuit"),
    ("Consensus analystes", "couverture européenne payante"),
    ("Allocation cible vs réelle", "aucun portefeuille réel n'est saisi"),
    ("Évolution du portefeuille", "aucun historique de portefeuille enregistré"),
]


def fr(n):
    """Entier avec espace insécable fine comme séparateur de milliers."""
    return f"{int(n):,}".replace(",", "\u202f")


def lire(chemin):
    if not chemin.exists():
        return []
    with open(chemin, encoding="utf-8") as f:
        return list(csv.DictReader(f, delimiter=";"))


def nombre(valeur):
    if valeur is None:
        return None
    texte = str(valeur).strip().replace(",", ".")
    if texte in ("", "-"):
        return None
    try:
        return float(texte)
    except ValueError:
        return None


def topsis(lignes):
    """Classement TOPSIS : proximité relative à la solution idéale.

    Renvoie une liste triée de (ISIN, nom, coefficient). Le coefficient vaut 1
    pour un instrument confondu avec l'idéal, 0 pour le pire du lot ; il est
    donc relatif à la population analysée et non absolu.
    """
    retenus = [l for l in lignes
               if all(nombre(l.get(c)) is not None for c in TOPSIS_CRITERES)]
    if len(retenus) < 3:
        return []

    # Normalisation vectorielle : chaque critère est ramené à une norme unité,
    # ce qui rend comparables des grandeurs d'échelles différentes.
    normes = {}
    for critere in TOPSIS_CRITERES:
        carres = sum(nombre(l[critere]) ** 2 for l in retenus)
        normes[critere] = math.sqrt(carres) or 1.0

    pondere = []
    for l in retenus:
        ligne = {}
        for critere, (poids, _) in TOPSIS_CRITERES.items():
            ligne[critere] = nombre(l[critere]) / normes[critere] * poids
        pondere.append(ligne)

    ideal, anti = {}, {}
    for critere, (_, benefice) in TOPSIS_CRITERES.items():
        valeurs = [p[critere] for p in pondere]
        ideal[critere] = max(valeurs) if benefice else min(valeurs)
        anti[critere] = min(valeurs) if benefice else max(valeurs)

    resultats = []
    for l, p in zip(retenus, pondere):
        d_plus = math.sqrt(sum((p[c] - ideal[c]) ** 2 for c in TOPSIS_CRITERES))
        d_moins = math.sqrt(sum((p[c] - anti[c]) ** 2 for c in TOPSIS_CRITERES))
        total = d_plus + d_moins
        resultats.append((l["ISIN"], l.get("Nom", ""),
                          (d_moins / total) if total else 0.0))
    resultats.sort(key=lambda x: -x[2])
    return resultats


def barre_repartition(compteur, total, couleurs):
    """Barre empilée proportionnelle, en pur CSS."""
    morceaux = []
    for i, (cle, n) in enumerate(compteur):
        pct = 100 * n / total if total else 0
        couleur = couleurs[i % len(couleurs)]
        morceaux.append(
            f'<span class="seg" style="width:{pct:.2f}%;background:{couleur}" '
            f'title="{html.escape(str(cle))} : {n}"></span>')
    return "".join(morceaux)


def legende(compteur, total, couleurs):
    lignes = []
    for i, (cle, n) in enumerate(compteur):
        pct = 100 * n / total if total else 0
        lignes.append(
            f'<li><span class="puce" style="background:{couleurs[i % len(couleurs)]}">'
            f'</span><span class="lib">{html.escape(str(cle))}</span>'
            f'<span class="val">{fr(n)}</span>'
            f'<span class="pct">{pct:.1f}%</span></li>')
    return "".join(lignes)


def construire(data, top):
    base = lire(data / "base_isin.csv")
    fonds = lire(data / "base_isin_fonds_pea.csv")
    marche = lire(data / "base_isin_marche.csv")
    scores = lire(data / "base_isin_scores.csv")

    total = len(base)
    par_type = Counter(r["Type"] for r in base).most_common()
    par_pays = Counter(PAYS.get(r["Pays_émission"], r["Pays_émission"])
                       for r in base).most_common(8)
    autres = total - sum(n for _, n in par_pays)
    if autres > 0:
        par_pays.append(("Autres", autres))

    elig = Counter(r["PEA_eligible"] for r in fonds)
    ordre_elig = [("OUI", "Éligible confirmé"), ("PROBABLE", "Probable"),
                  ("A_VERIFIER", "À vérifier"), ("NON", "Non éligible")]
    elig_liste = [(lib, elig.get(cle, 0)) for cle, lib in ordre_elig]

    notes = [nombre(r["Score_global"]) for r in scores if nombre(r["Score_global"])]
    couvertures = [nombre(r["Couverture_pct"]) for r in scores
                   if nombre(r["Couverture_pct"])]
    score_moyen = sum(notes) / len(notes) if notes else 0
    couv_moyenne = sum(couvertures) / len(couvertures) if couvertures else 0

    esg_renseigne = sum(1 for r in base
                        if (r.get("ESG_classification") or "").strip() not in ("", "-"))
    avec_figi = sum(1 for r in lire(data / "base_isin_figi.csv") if r.get("FIGI"))

    # Diversification : indice de Herfindahl normalisé sur la répartition pays.
    parts = [n / total for _, n in Counter(r["Pays_émission"] for r in base).items()]
    hhi = sum(p * p for p in parts)
    diversification = (1 - hhi) * 100

    classement_topsis = topsis(marche)[:top]
    par_isin_score = {r["ISIN"]: r for r in scores}
    meilleurs = sorted(scores, key=lambda r: -(nombre(r["Score_global"]) or 0))[:top]

    couleurs_type = ["#2f6f6b", "#4d8f88", "#7fb0a6"]
    couleurs_pays = ["#1f4a5c", "#2f6f6b", "#4d8f88", "#7fb0a6", "#a8c8bd",
                     "#b8762a", "#d09a55", "#e0bd8a", "#c3cbd4"]
    couleurs_elig = ["#2f6f6b", "#7fb0a6", "#c3cbd4", "#8a3d3d"]

    part_notee = 100 * len(scores) / total if total else 0

    lignes_top = "".join(
        f'<tr><td class="rg">{i}</td><td class="nom">{html.escape(r["Nom"][:40])}</td>'
        f'<td class="ty">{html.escape(r["Type"])}</td>'
        f'<td class="nu">{r["Score_global"]}</td>'
        f'<td class="nu couv">{r["Couverture_pct"]}%</td></tr>'
        for i, r in enumerate(meilleurs, 1))

    lignes_topsis = "".join(
        f'<tr><td class="rg">{i}</td><td class="nom">{html.escape(nom[:40])}</td>'
        f'<td class="nu">{coef:.3f}</td>'
        f'<td class="nu couv">{par_isin_score.get(isin, {}).get("Score_global", "—")}</td></tr>'
        for i, (isin, nom, coef) in enumerate(classement_topsis, 1))

    lignes_absents = "".join(
        f'<li><span class="abs-t">{html.escape(t)}</span>'
        f'<span class="abs-m">{html.escape(m)}</span></li>'
        for t, m in NON_ALIMENTES)

    return f"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>PEA Advisor — état de la base</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans+Condensed:wght@400;600;700&family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
:root {{
  --encre:#16202b; --encre-2:#3d4d5c; --papier:#eef1f4; --carte:#ffffff;
  --trait:#c9d2da; --couvert:#2f6f6b; --manquant:#b8762a; --alerte:#8a3d3d;
}}
* {{ box-sizing:border-box; }}
body {{
  margin:0; background:var(--papier); color:var(--encre);
  font-family:"IBM Plex Sans",system-ui,sans-serif; font-size:15px; line-height:1.55;
}}
.page {{ max-width:1080px; margin:0 auto; padding:28px 20px 64px; }}
.eyebrow {{
  font-family:"IBM Plex Mono",monospace; font-size:11px; letter-spacing:.18em;
  text-transform:uppercase; color:var(--encre-2);
}}
h1 {{
  font-family:"IBM Plex Sans Condensed",sans-serif; font-weight:700;
  font-size:clamp(30px,6vw,50px); line-height:1.03; letter-spacing:-.015em;
  margin:.18em 0 .3em;
}}
.these {{ max-width:56ch; color:var(--encre-2); margin:0 0 26px; }}
h2 {{
  font-family:"IBM Plex Sans Condensed",sans-serif; font-size:13px; font-weight:700;
  letter-spacing:.14em; text-transform:uppercase; color:var(--encre-2);
  margin:0 0 14px; padding-bottom:7px; border-bottom:1px solid var(--trait);
}}
.carte {{
  background:var(--carte); border:1px solid var(--trait); border-radius:3px;
  padding:20px; margin-bottom:18px;
}}
/* Signature : la couverture du barème, vide compris. */
.jauge {{ display:flex; height:52px; border:1px solid var(--encre); border-radius:2px; overflow:hidden; }}
.jauge .plein {{ background:var(--couvert); }}
.jauge .vide {{
  background:repeating-linear-gradient(135deg,#f3ece1,#f3ece1 5px,#e6d9c4 5px,#e6d9c4 10px);
}}
.jauge-leg {{ display:flex; justify-content:space-between; margin-top:9px; font-size:12.5px; color:var(--encre-2); }}
.jauge-leg b {{ font-family:"IBM Plex Mono",monospace; color:var(--encre); }}
.kpis {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(158px,1fr)); gap:14px; margin-bottom:18px; }}
.kpi {{ background:var(--carte); border:1px solid var(--trait); border-radius:3px; padding:15px 16px; }}
.kpi .v {{ font-family:"IBM Plex Mono",monospace; font-size:26px; font-weight:500; letter-spacing:-.02em; }}
.kpi .l {{ font-size:12px; color:var(--encre-2); margin-top:3px; }}
.duo {{ display:grid; grid-template-columns:1fr 1fr; gap:18px; }}
.barre {{ display:flex; height:22px; border-radius:2px; overflow:hidden; background:var(--papier); }}
.seg {{ display:block; height:100%; }}
ul.leg {{ list-style:none; margin:13px 0 0; padding:0; font-size:13.5px; }}
ul.leg li {{ display:flex; align-items:center; gap:9px; padding:3.5px 0; border-bottom:1px solid #eef1f4; }}
.puce {{ width:10px; height:10px; border-radius:2px; flex:none; }}
.lib {{ flex:1; }}
.val {{ font-family:"IBM Plex Mono",monospace; }}
.pct {{ font-family:"IBM Plex Mono",monospace; color:var(--encre-2); width:56px; text-align:right; }}
table {{ width:100%; border-collapse:collapse; font-size:13.5px; }}
th {{
  text-align:left; font-family:"IBM Plex Mono",monospace; font-size:10.5px;
  letter-spacing:.1em; text-transform:uppercase; color:var(--encre-2);
  padding:0 7px 7px; border-bottom:1px solid var(--trait); font-weight:500;
}}
td {{ padding:7px; border-bottom:1px solid #eef1f4; }}
.rg {{ font-family:"IBM Plex Mono",monospace; color:var(--encre-2); width:30px; }}
.nu {{ font-family:"IBM Plex Mono",monospace; text-align:right; }}
.couv {{ color:var(--encre-2); }}
.ty {{ font-size:12px; color:var(--encre-2); }}
ul.absents {{ list-style:none; margin:0; padding:0; }}
ul.absents li {{
  display:flex; flex-wrap:wrap; gap:4px 12px; padding:9px 0 9px 15px;
  border-bottom:1px solid #eef1f4; border-left:3px solid var(--manquant);
  padding-left:13px; margin-bottom:2px;
}}
.abs-t {{ font-weight:600; min-width:200px; }}
.abs-m {{ color:var(--encre-2); font-size:13px; }}
.note {{ font-size:13px; color:var(--encre-2); margin-top:11px; }}
footer {{ margin-top:34px; padding-top:16px; border-top:1px solid var(--trait);
  font-size:12.5px; color:var(--encre-2); }}
@media (max-width:720px) {{ .duo {{ grid-template-columns:1fr; }} .abs-t {{ min-width:0; }} }}
</style>
</head>
<body>
<div class="page">

<p class="eyebrow">PEA Advisor · base ISIN · {date.today().isoformat()}</p>
<h1>Ce que la base sait,<br>et ce qu'elle ignore.</h1>
<p class="these">
  {fr(total)} instruments recensés depuis les listes officielles Euronext. Mais un
  tableau de bord n'est utile que s'il distingue une donnée mesurée d'une donnée
  absente. Les deux sont affichées ici.
</p>

<div class="carte">
  <h2>Couverture du barème de score</h2>
  <div class="jauge" role="img"
       aria-label="Barème couvert à {couv_moyenne:.0f} %">
    <div class="plein" style="width:{couv_moyenne:.1f}%"></div>
    <div class="vide" style="width:{100 - couv_moyenne:.1f}%"></div>
  </div>
  <div class="jauge-leg">
    <span><b>{couv_moyenne:.0f} %</b> évalués — risque et performance passée</span>
    <span><b>{100 - couv_moyenne:.0f} %</b> sans source — valorisation, dividende, potentiel</span>
  </div>
  <p class="note">
    Un score de 80 couvert à {couv_moyenne:.0f} % ne vaut pas un score de 80 couvert à 100 %.
    La colonne « couv. » accompagne donc chaque classement ci-dessous.
  </p>
</div>

<div class="kpis">
  <div class="kpi"><div class="v">{fr(total)}</div><div class="l">instruments recensés</div></div>
  <div class="kpi"><div class="v">{fr(avec_figi)}</div><div class="l">identifiés FIGI / ticker</div></div>
  <div class="kpi"><div class="v">{fr(len(scores))}</div><div class="l">notés ({part_notee:.1f} % de la base)</div></div>
  <div class="kpi"><div class="v">{score_moyen:.1f}</div><div class="l">score moyen /100</div></div>
  <div class="kpi"><div class="v">{diversification:.1f}</div><div class="l">diversification pays /100</div></div>
  <div class="kpi"><div class="v">{fr(esg_renseigne)}</div><div class="l">avec classification ESG</div></div>
</div>

<div class="duo">
  <div class="carte">
    <h2>Nature des instruments</h2>
    <div class="barre">{barre_repartition(par_type, total, couleurs_type)}</div>
    <ul class="leg">{legende(par_type, total, couleurs_type)}</ul>
  </div>
  <div class="carte">
    <h2>Pays d'émission</h2>
    <div class="barre">{barre_repartition(par_pays, total, couleurs_pays)}</div>
    <ul class="leg">{legende(par_pays, total, couleurs_pays)}</ul>
  </div>
</div>

<div class="carte">
  <h2>Éligibilité PEA des fonds ({fr(sum(elig.values()))} ETF et OPCVM)</h2>
  <div class="barre">{barre_repartition(elig_liste, sum(elig.values()), couleurs_elig)}</div>
  <ul class="leg">{legende(elig_liste, sum(elig.values()), couleurs_elig)}</ul>
  <p class="note">
    Aucune liste officielle d'ETF éligibles n'existe : l'éligibilité est un
    engagement de la société de gestion dans le prospectus. Les fonds « à
    vérifier » attendent une confirmation sur la fiche de l'émetteur.
  </p>
</div>

<div class="duo">
  <div class="carte">
    <h2>Meilleurs scores pondérés</h2>
    <table><thead><tr><th></th><th>Instrument</th><th>Type</th>
      <th style="text-align:right">Score</th><th style="text-align:right">Couv.</th>
    </tr></thead><tbody>{lignes_top or '<tr><td colspan="5">Aucun instrument noté.</td></tr>'}</tbody></table>
  </div>
  <div class="carte">
    <h2>Matrice multicritère TOPSIS</h2>
    <table><thead><tr><th></th><th>Instrument</th>
      <th style="text-align:right">Coef.</th><th style="text-align:right">Score</th>
    </tr></thead><tbody>{lignes_topsis or '<tr><td colspan="4">Population insuffisante.</td></tr>'}</tbody></table>
    <p class="note">
      Distance à la solution idéale, méthode indépendante du score pondéré. Un
      écart de classement entre les deux colonnes signale un instrument dont la
      note dépend fortement des pondérations choisies.
    </p>
  </div>
</div>

<div class="carte">
  <h2>Indicateurs prévus, non alimentés</h2>
  <ul class="absents">{lignes_absents}</ul>
  <p class="note">
    Ces indicateurs entreront dans le tableau de bord dès qu'une source les
    alimentera. Ils figurent ici pour que leur absence soit un constat, pas un oubli.
  </p>
</div>

<footer>
  Aide à la décision — ni conseil en investissement, ni conseil fiscal.
  Généré par <code>scripts/dashboard.py</code>.
</footer>

</div>
</body>
</html>"""


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--top", type=int, default=10)
    p.add_argument("--data-dir", default="data")
    args = p.parse_args()

    data = Path(args.data_dir)
    if not (data / "base_isin.csv").exists():
        print(f"{data}/base_isin.csv absent.")
        return 1
    sortie = data / "dashboard.html"
    sortie.write_text(construire(data, args.top), encoding="utf-8")
    print(f"{sortie} : {sortie.stat().st_size // 1024} Ko")
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Tableau de bord de la base, matrice TOPSIS et constitution de lots.

Produit data/dashboard.html, page autonome consultable hors ligne.

Trois principes :

1. **Montrer autant ce qui manque que ce qui est mesuré.** Les indicateurs du
   cahier des charges sans source disponible sont listés avec leur motif ; la
   couverture du barème est affichée avec sa part manquante visible.
2. **Dater chaque donnée.** Un cours de trois mois n'a pas la valeur d'un cours
   de la veille : l'âge est affiché par ligne et signalé au-delà d'un seuil.
3. **Ne jamais embarquer de clé d'API.** La page est versionnée sur GitHub :
   y placer une clé l'exposerait publiquement. La sélection de lignes produit
   donc une commande à copier et une file d'attente à télécharger, que
   `scripts/enrich_marche.py` consomme via --isins ou --file-attente.

Usage :
  python3 scripts/dashboard.py
  python3 scripts/dashboard.py --top 15 --seuil-fraicheur 7
"""
import argparse
import csv
import html
import json
import math
import sys
from collections import Counter
from datetime import date, datetime
from pathlib import Path

TOPSIS_CRITERES = {
    "Perf_periode_pct": (0.30, True),
    "Sharpe": (0.25, True),
    "Volatilite_annualisee_pct": (0.20, False),
    "Drawdown_max_pct": (0.15, True),
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


def fr(n):
    return f"{int(n):,}".replace(",", "\u202f")


def age_jours(iso):
    """Nombre de jours depuis une date ISO, ou None si absente/illisible."""
    if not iso:
        return None
    try:
        return (date.today() - datetime.strptime(iso[:10], "%Y-%m-%d").date()).days
    except ValueError:
        return None


def topsis(lignes):
    retenus = [l for l in lignes
               if all(nombre(l.get(c)) is not None for c in TOPSIS_CRITERES)]
    if len(retenus) < 3:
        return []
    normes = {c: math.sqrt(sum(nombre(l[c]) ** 2 for l in retenus)) or 1.0
              for c in TOPSIS_CRITERES}
    pondere = [{c: nombre(l[c]) / normes[c] * p
                for c, (p, _) in TOPSIS_CRITERES.items()} for l in retenus]
    ideal, anti = {}, {}
    for c, (_, benefice) in TOPSIS_CRITERES.items():
        vals = [x[c] for x in pondere]
        ideal[c] = max(vals) if benefice else min(vals)
        anti[c] = min(vals) if benefice else max(vals)
    out = []
    for l, x in zip(retenus, pondere):
        dp = math.sqrt(sum((x[c] - ideal[c]) ** 2 for c in TOPSIS_CRITERES))
        dm = math.sqrt(sum((x[c] - anti[c]) ** 2 for c in TOPSIS_CRITERES))
        out.append((l["ISIN"], l.get("Nom", ""), dm / (dp + dm) if dp + dm else 0.0))
    out.sort(key=lambda x: -x[2])
    return out


def barre(compteur, total, couleurs):
    return "".join(
        f'<span class="seg" style="width:{100 * n / total if total else 0:.2f}%;'
        f'background:{couleurs[i % len(couleurs)]}" '
        f'title="{html.escape(str(c))} : {n}"></span>'
        for i, (c, n) in enumerate(compteur))


def legende(compteur, total, couleurs):
    return "".join(
        f'<li><span class="puce" style="background:{couleurs[i % len(couleurs)]}">'
        f'</span><span class="lib">{html.escape(str(c))}</span>'
        f'<span class="val">{fr(n)}</span>'
        f'<span class="pct">{100 * n / total if total else 0:.1f}%</span></li>'
        for i, (c, n) in enumerate(compteur))


def construire(data, top, seuil):
    base = lire(data / "base_isin.csv")
    fonds = {r["ISIN"]: r for r in lire(data / "base_isin_fonds_pea.csv")}
    marche = lire(data / "base_isin_marche.csv")
    marche_idx = {r["ISIN"]: r for r in marche}
    scores = lire(data / "base_isin_scores.csv")
    scores_idx = {r["ISIN"]: r for r in scores}
    figi = {r["ISIN"]: r for r in lire(data / "base_isin_figi.csv")}

    total = len(base)

    # Lignes de l'explorateur. Tableau plutôt qu'objet : à 6 000 lignes, la
    # différence de poids du fichier est significative.
    lignes = []
    for r in base:
        isin = r["ISIN"]
        m = marche_idx.get(isin, {})
        s = scores_idx.get(isin, {})
        f = fonds.get(isin, {})
        pea = f.get("PEA_eligible") or ("OUI" if r.get("PEA_indicatif") == "OUI" else "NON")
        etat = "note" if s else ("collecte" if m else "attente")
        lignes.append([
            isin,
            r["Nom"][:46],
            r["Type"],
            PAYS.get(r["Pays_émission"], r["Pays_émission"]),
            pea,
            etat,
            nombre(s.get("Score_global")),
            nombre(s.get("Couverture_pct")),
            nombre(m.get("Volatilite_annualisee_pct")),
            nombre(m.get("Perf_periode_pct")),
            nombre(m.get("Sharpe")),
            nombre(m.get("Drawdown_max_pct")),
            m.get("Date_cours") or "",
            age_jours(m.get("Date_cours")),
        ])

    par_type = Counter(r["Type"] for r in base).most_common()
    par_pays = Counter(PAYS.get(r["Pays_émission"], r["Pays_émission"])
                       for r in base).most_common(8)
    reste = total - sum(n for _, n in par_pays)
    if reste > 0:
        par_pays.append(("Autres", reste))

    elig = Counter(r["PEA_eligible"] for r in fonds.values())
    elig_liste = [(lib, elig.get(cle, 0)) for cle, lib in
                  [("OUI", "Éligible confirmé"), ("PROBABLE", "Probable"),
                   ("A_VERIFIER", "À vérifier"), ("NON", "Non éligible")]]

    notes = [nombre(r["Score_global"]) for r in scores if nombre(r["Score_global"])]
    couvs = [nombre(r["Couverture_pct"]) for r in scores if nombre(r["Couverture_pct"])]
    score_moyen = sum(notes) / len(notes) if notes else 0
    couv_moyenne = sum(couvs) / len(couvs) if couvs else 0
    esg = sum(1 for r in base
              if (r.get("ESG_classification") or "").strip() not in ("", "-"))
    avec_figi = sum(1 for r in figi.values() if r.get("FIGI"))
    parts = [n / total for n in Counter(r["Pays_émission"] for r in base).values()]
    diversification = (1 - sum(p * p for p in parts)) * 100

    # Fraîcheur : la donnée la plus ancienne compte autant que la plus récente.
    ages = [a for a in (age_jours(r.get("Date_cours")) for r in marche) if a is not None]
    maj_base = max((r.get("Date_MAJ", "") for r in base), default="—")
    perimes = sum(1 for a in ages if a > seuil)

    top_scores = sorted(scores, key=lambda r: -(nombre(r["Score_global"]) or 0))[:top]
    classement = topsis(marche)[:top]

    c_type = ["#2f6f6b", "#4d8f88", "#7fb0a6"]
    c_pays = ["#1f4a5c", "#2f6f6b", "#4d8f88", "#7fb0a6", "#a8c8bd",
              "#b8762a", "#d09a55", "#e0bd8a", "#c3cbd4"]
    c_elig = ["#2f6f6b", "#7fb0a6", "#c3cbd4", "#8a3d3d"]

    gabarit = MODELE
    remplacements = {
        "__DONNEES__": json.dumps(lignes, ensure_ascii=False, separators=(",", ":")),
        "__DATE__": date.today().isoformat(),
        "__HEURE__": datetime.now().strftime("%H:%M"),
        "__TOTAL__": fr(total),
        "__FIGI__": fr(avec_figi),
        "__NOTES__": fr(len(scores)),
        "__PART_NOTEE__": f"{100 * len(scores) / total if total else 0:.1f}",
        "__SCORE_MOYEN__": f"{score_moyen:.1f}",
        "__DIVERS__": f"{diversification:.1f}",
        "__ESG__": fr(esg),
        "__COUV_MANQ_R__": f"{100 - couv_moyenne:.0f}",
        "__COUV_MANQ__": f"{100 - couv_moyenne:.1f}",
        "__COUV_R__": f"{couv_moyenne:.0f}",
        "__COUV__": f"{couv_moyenne:.1f}",
        "__MAJ_BASE__": maj_base,
        "__MAJ_COURS__": (f"il y a {min(ages)} j" if ages else "aucun cours"),
        "__COURS_PLUS_VIEUX__": (f"{max(ages)} j" if ages else "—"),
        "__PERIMES__": str(perimes),
        "__SEUIL__": str(seuil),
        "__BARRE_TYPE__": barre(par_type, total, c_type),
        "__LEG_TYPE__": legende(par_type, total, c_type),
        "__BARRE_PAYS__": barre(par_pays, total, c_pays),
        "__LEG_PAYS__": legende(par_pays, total, c_pays),
        "__NB_FONDS__": fr(sum(elig.values())),
        "__BARRE_ELIG__": barre(elig_liste, sum(elig.values()), c_elig),
        "__LEG_ELIG__": legende(elig_liste, sum(elig.values()), c_elig),
        "__TOP_SCORES__": "".join(
            f'<tr><td class="rg">{i}</td><td>{html.escape(r["Nom"][:38])}</td>'
            f'<td class="ty">{html.escape(r["Type"])}</td>'
            f'<td class="nu">{r["Score_global"]}</td>'
            f'<td class="nu couv">{r["Couverture_pct"]}%</td></tr>'
            for i, r in enumerate(top_scores, 1)) or
            '<tr><td colspan="5">Aucun instrument noté.</td></tr>',
        "__TOPSIS__": "".join(
            f'<tr><td class="rg">{i}</td><td>{html.escape(n[:38])}</td>'
            f'<td class="nu">{c:.3f}</td>'
            f'<td class="nu couv">{scores_idx.get(k, {}).get("Score_global", "—")}</td></tr>'
            for i, (k, n, c) in enumerate(classement, 1)) or
            '<tr><td colspan="4">Population insuffisante.</td></tr>',
        "__ABSENTS__": "".join(
            f'<li><span class="abs-t">{html.escape(t)}</span>'
            f'<span class="abs-m">{html.escape(m)}</span></li>'
            for t, m in NON_ALIMENTES),
    }
    for cle, valeur in remplacements.items():
        gabarit = gabarit.replace(cle, valeur)
    return gabarit


MODELE = r"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>PEA Advisor — état de la base</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans+Condensed:wght@400;600;700&family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
:root{--encre:#16202b;--encre-2:#3d4d5c;--papier:#eef1f4;--carte:#fff;
--trait:#c9d2da;--couvert:#2f6f6b;--manquant:#b8762a;--alerte:#8a3d3d;}
*{box-sizing:border-box}
body{margin:0;background:var(--papier);color:var(--encre);
font-family:"IBM Plex Sans",system-ui,sans-serif;font-size:15px;line-height:1.55}
.page{max-width:1180px;margin:0 auto;padding:28px 20px 64px}
.eyebrow{font-family:"IBM Plex Mono",monospace;font-size:11px;letter-spacing:.18em;
text-transform:uppercase;color:var(--encre-2)}
h1{font-family:"IBM Plex Sans Condensed",sans-serif;font-weight:700;
font-size:clamp(30px,6vw,50px);line-height:1.03;letter-spacing:-.015em;margin:.18em 0 .3em}
.these{max-width:56ch;color:var(--encre-2);margin:0 0 22px}
h2{font-family:"IBM Plex Sans Condensed",sans-serif;font-size:13px;font-weight:700;
letter-spacing:.14em;text-transform:uppercase;color:var(--encre-2);margin:0 0 14px;
padding-bottom:7px;border-bottom:1px solid var(--trait)}
.carte{background:var(--carte);border:1px solid var(--trait);border-radius:3px;
padding:20px;margin-bottom:18px}
.fraicheur{display:flex;flex-wrap:wrap;gap:0;border:1px solid var(--encre);
border-radius:3px;overflow:hidden;margin-bottom:18px;background:var(--carte)}
.fr-item{flex:1 1 175px;padding:12px 16px;border-right:1px solid var(--trait)}
.fr-item:last-child{border-right:0}
.fr-l{font-family:"IBM Plex Mono",monospace;font-size:10px;letter-spacing:.12em;
text-transform:uppercase;color:var(--encre-2)}
.fr-v{font-family:"IBM Plex Mono",monospace;font-size:16px;margin-top:2px}
.fr-item.alerte{background:#fdf6ec}
.fr-item.alerte .fr-v{color:var(--manquant)}
.jauge{display:flex;height:52px;border:1px solid var(--encre);border-radius:2px;overflow:hidden}
.jauge .plein{background:var(--couvert)}
.jauge .vide{background:repeating-linear-gradient(135deg,#f3ece1,#f3ece1 5px,#e6d9c4 5px,#e6d9c4 10px)}
.jauge-leg{display:flex;justify-content:space-between;flex-wrap:wrap;gap:6px;
margin-top:9px;font-size:12.5px;color:var(--encre-2)}
.jauge-leg b{font-family:"IBM Plex Mono",monospace;color:var(--encre)}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:14px;margin-bottom:18px}
.kpi{background:var(--carte);border:1px solid var(--trait);border-radius:3px;padding:15px 16px}
.kpi .v{font-family:"IBM Plex Mono",monospace;font-size:25px;font-weight:500;letter-spacing:-.02em}
.kpi .l{font-size:12px;color:var(--encre-2);margin-top:3px}
.duo{display:grid;grid-template-columns:1fr 1fr;gap:18px}
.barre{display:flex;height:22px;border-radius:2px;overflow:hidden;background:var(--papier)}
.seg{display:block;height:100%}
ul.leg{list-style:none;margin:13px 0 0;padding:0;font-size:13.5px}
ul.leg li{display:flex;align-items:center;gap:9px;padding:3.5px 0;border-bottom:1px solid #eef1f4}
.puce{width:10px;height:10px;border-radius:2px;flex:none}
.lib{flex:1}.val{font-family:"IBM Plex Mono",monospace}
.pct{font-family:"IBM Plex Mono",monospace;color:var(--encre-2);width:56px;text-align:right}
table{width:100%;border-collapse:collapse;font-size:13.5px}
th{text-align:left;font-family:"IBM Plex Mono",monospace;font-size:10.5px;
letter-spacing:.1em;text-transform:uppercase;color:var(--encre-2);
padding:0 7px 7px;border-bottom:1px solid var(--trait);font-weight:500}
td{padding:7px;border-bottom:1px solid #eef1f4}
.rg{font-family:"IBM Plex Mono",monospace;color:var(--encre-2);width:30px}
.nu{font-family:"IBM Plex Mono",monospace;text-align:right}
.couv{color:var(--encre-2)}.ty{font-size:12px;color:var(--encre-2)}
.outils{display:flex;flex-wrap:wrap;gap:9px;margin-bottom:14px}
.outils input[type=search],.outils select{font-family:inherit;font-size:13.5px;
padding:7px 9px;border:1px solid var(--trait);border-radius:3px;background:#fff;color:inherit}
.outils input[type=search]{flex:1 1 200px}
button{font-family:inherit;font-size:13px;padding:7px 13px;border:1px solid var(--encre);
border-radius:3px;background:var(--encre);color:#fff;cursor:pointer}
button.sec{background:#fff;color:var(--encre)}
button:disabled{opacity:.4;cursor:not-allowed}
button:focus-visible,input:focus-visible,select:focus-visible,th.tri:focus-visible{
outline:2px solid var(--couvert);outline-offset:2px}
#tbl th.tri{cursor:pointer;user-select:none;white-space:nowrap}
#tbl th .fl{opacity:.35;font-size:9px}
#tbl th.actif .fl{opacity:1}
#tbl tbody tr:hover{background:#f7f9fa}
#tbl tbody tr.grp td{background:#e9eef1;font-weight:600;
font-family:"IBM Plex Sans Condensed",sans-serif;letter-spacing:.03em}
.etat{font-size:11px;font-family:"IBM Plex Mono",monospace;padding:2px 6px;border-radius:2px}
.etat.note{background:#dfeeeb;color:#1d534f}
.etat.collecte{background:#fdf1e0;color:#8a5a1c}
.etat.attente{background:#eceff2;color:var(--encre-2)}
.vieux{color:var(--manquant);font-weight:500}
.pied{display:flex;flex-wrap:wrap;gap:10px;align-items:center;
justify-content:space-between;margin-top:13px;font-size:13px;color:var(--encre-2)}
.lot{margin-top:14px;padding:15px;border:1px solid var(--manquant);
border-radius:3px;background:#fdf8f1}
.lot[hidden]{display:none}
.lot code{display:block;font-family:"IBM Plex Mono",monospace;font-size:12px;
background:#fff;border:1px solid var(--trait);border-radius:2px;padding:9px;
margin:9px 0;overflow-x:auto;white-space:pre}
ul.absents{list-style:none;margin:0;padding:0}
ul.absents li{display:flex;flex-wrap:wrap;gap:4px 12px;padding:9px 0 9px 13px;
border-bottom:1px solid #eef1f4;border-left:3px solid var(--manquant);margin-bottom:2px}
.abs-t{font-weight:600;min-width:200px}
.abs-m{color:var(--encre-2);font-size:13px}
.note{font-size:13px;color:var(--encre-2);margin-top:11px}
footer{margin-top:34px;padding-top:16px;border-top:1px solid var(--trait);
font-size:12.5px;color:var(--encre-2)}
/* Le tableau défile horizontalement dans son cadre : sur petit écran, mieux
vaut un défilement local qu'une page entière plus large que l'écran. */
.tbl-wrap{overflow-x:auto;-webkit-overflow-scrolling:touch}
.tbl-wrap table{min-width:520px}
@media (max-width:760px){.duo{grid-template-columns:1fr}.abs-t{min-width:0}
.masq-s{display:none}#tbl{font-size:12.5px}
.lot code{white-space:pre-wrap;word-break:break-all}
.outils input[type=search],.outils select{flex:1 1 100%}}
@media (prefers-reduced-motion:reduce){*{transition:none!important;animation:none!important}}
</style>
</head>
<body>
<div class="page">

<p class="eyebrow">PEA Advisor · base ISIN · __DATE__ __HEURE__</p>
<h1>Ce que la base sait,<br>et ce qu'elle ignore.</h1>
<p class="these">__TOTAL__ instruments recensés depuis les listes officielles Euronext.
Un tableau de bord n'est utile que s'il distingue une donnée mesurée d'une donnée
absente, et une donnée fraîche d'une donnée périmée. Les trois sont affichées ici.</p>

<div class="fraicheur">
  <div class="fr-item"><div class="fr-l">Page générée</div><div class="fr-v">__DATE__ · __HEURE__</div></div>
  <div class="fr-item"><div class="fr-l">Base ISIN</div><div class="fr-v">__MAJ_BASE__</div></div>
  <div class="fr-item"><div class="fr-l">Cours le plus récent</div><div class="fr-v">__MAJ_COURS__</div></div>
  <div class="fr-item"><div class="fr-l">Cours le plus ancien</div><div class="fr-v">__COURS_PLUS_VIEUX__</div></div>
  <div class="fr-item alerte"><div class="fr-l">Périmés (&gt; __SEUIL__ j)</div><div class="fr-v">__PERIMES__</div></div>
</div>

<div class="carte">
  <h2>Couverture du barème de score</h2>
  <div class="jauge" role="img" aria-label="Barème couvert à __COUV_R__ pour cent">
    <div class="plein" style="width:__COUV__%"></div>
    <div class="vide" style="width:__COUV_MANQ__%"></div>
  </div>
  <div class="jauge-leg">
    <span><b>__COUV_R__ %</b> évalués — risque et performance passée</span>
    <span><b>__COUV_MANQ_R__ %</b> sans source — valorisation, dividende, potentiel</span>
  </div>
  <p class="note">Un score de 80 couvert à __COUV_R__ % ne vaut pas un score de 80
  couvert à 100 %. La colonne « couv. » accompagne donc chaque classement.</p>
</div>

<div class="kpis">
  <div class="kpi"><div class="v">__TOTAL__</div><div class="l">instruments recensés</div></div>
  <div class="kpi"><div class="v">__FIGI__</div><div class="l">identifiés FIGI / ticker</div></div>
  <div class="kpi"><div class="v">__NOTES__</div><div class="l">notés (__PART_NOTEE__ % de la base)</div></div>
  <div class="kpi"><div class="v">__SCORE_MOYEN__</div><div class="l">score moyen /100</div></div>
  <div class="kpi"><div class="v">__DIVERS__</div><div class="l">diversification pays /100</div></div>
  <div class="kpi"><div class="v">__ESG__</div><div class="l">avec classification ESG</div></div>
</div>

<div class="carte">
  <h2>Explorateur — tri, regroupement et constitution de lots</h2>
  <div class="outils">
    <input type="search" id="q" placeholder="Rechercher un nom ou un ISIN…" aria-label="Rechercher">
    <select id="fType" aria-label="Filtrer par nature"><option value="">Toutes natures</option></select>
    <select id="fPays" aria-label="Filtrer par pays"><option value="">Tous pays</option></select>
    <select id="fPea" aria-label="Filtrer par éligibilité PEA"><option value="">Toute éligibilité</option></select>
    <select id="fEtat" aria-label="Filtrer par état des données">
      <option value="">Tous états</option><option value="note">Notés</option>
      <option value="collecte">Collectés, non notés</option><option value="attente">En attente</option>
    </select>
    <select id="grp" aria-label="Regrouper les lignes">
      <option value="">Sans regroupement</option><option value="2">Grouper par nature</option>
      <option value="3">Grouper par pays</option><option value="4">Grouper par éligibilité PEA</option>
      <option value="5">Grouper par état des données</option>
    </select>
    <button type="button" class="sec" id="reset">Réinitialiser</button>
  </div>

  <div class="tbl-wrap">
  <table id="tbl">
    <thead><tr>
      <th style="width:26px"><input type="checkbox" id="tout" aria-label="Tout sélectionner"></th>
      <th class="tri" data-c="1" tabindex="0">Instrument <span class="fl">▲▼</span></th>
      <th class="tri masq-s" data-c="2" tabindex="0">Nature <span class="fl">▲▼</span></th>
      <th class="tri masq-s" data-c="3" tabindex="0">Pays <span class="fl">▲▼</span></th>
      <th class="tri" data-c="4" tabindex="0">PEA <span class="fl">▲▼</span></th>
      <th class="tri" data-c="5" tabindex="0">État <span class="fl">▲▼</span></th>
      <th class="tri nu" data-c="6" tabindex="0">Score <span class="fl">▲▼</span></th>
      <th class="tri nu masq-s" data-c="8" tabindex="0">Vol. <span class="fl">▲▼</span></th>
      <th class="tri nu masq-s" data-c="9" tabindex="0">Perf. <span class="fl">▲▼</span></th>
      <th class="tri nu" data-c="13" tabindex="0">Âge <span class="fl">▲▼</span></th>
    </tr></thead>
    <tbody id="corps"></tbody>
  </table>
  </div>

  <div class="pied">
    <span id="compte"></span>
    <span>
      <button type="button" class="sec" id="pageMoins">Précédent</button>
      <span id="pagination"></span>
      <button type="button" class="sec" id="pagePlus">Suivant</button>
    </span>
  </div>

  <div class="lot" id="lot" hidden>
    <strong id="lotTitre"></strong>
    <p class="note" style="margin-top:6px">
      Cette page ne contient aucune clé d'API : elle est versionnée sur GitHub, où
      une clé serait exposée. Le lot est donc préparé ici et exécuté par le script.
    </p>
    <code id="lotCmd"></code>
    <button type="button" id="copier">Copier la commande</button>
    <button type="button" class="sec" id="telecharger">Télécharger la file d'attente</button>
    <button type="button" class="sec" id="vider">Vider la sélection</button>
  </div>
</div>

<div class="duo">
  <div class="carte">
    <h2>Nature des instruments</h2>
    <div class="barre">__BARRE_TYPE__</div>
    <ul class="leg">__LEG_TYPE__</ul>
  </div>
  <div class="carte">
    <h2>Pays d'émission</h2>
    <div class="barre">__BARRE_PAYS__</div>
    <ul class="leg">__LEG_PAYS__</ul>
  </div>
</div>

<div class="carte">
  <h2>Éligibilité PEA des fonds (__NB_FONDS__ ETF et OPCVM)</h2>
  <div class="barre">__BARRE_ELIG__</div>
  <ul class="leg">__LEG_ELIG__</ul>
  <p class="note">Aucune liste officielle d'ETF éligibles n'existe : l'éligibilité
  est un engagement de la société de gestion dans le prospectus. Les fonds
  « à vérifier » attendent une confirmation sur la fiche de l'émetteur.</p>
</div>

<div class="duo">
  <div class="carte">
    <h2>Meilleurs scores pondérés</h2>
    <table><thead><tr><th></th><th>Instrument</th><th>Type</th>
      <th class="nu">Score</th><th class="nu">Couv.</th></tr></thead>
      <tbody>__TOP_SCORES__</tbody></table>
  </div>
  <div class="carte">
    <h2>Matrice multicritère TOPSIS</h2>
    <table><thead><tr><th></th><th>Instrument</th>
      <th class="nu">Coef.</th><th class="nu">Score</th></tr></thead>
      <tbody>__TOPSIS__</tbody></table>
    <p class="note">Distance à la solution idéale, méthode indépendante du score
    pondéré. Un écart de rang entre les deux signale un instrument dont la note
    dépend fortement des pondérations choisies.</p>
  </div>
</div>

<div class="carte">
  <h2>Indicateurs prévus, non alimentés</h2>
  <ul class="absents">__ABSENTS__</ul>
  <p class="note">Ces indicateurs entreront dans le tableau de bord dès qu'une
  source les alimentera. Ils figurent ici pour que leur absence soit un constat,
  pas un oubli.</p>
</div>

<footer>Aide à la décision — ni conseil en investissement, ni conseil fiscal.
Généré par <code>scripts/dashboard.py</code>.</footer>
</div>

<script>
(function(){
"use strict";
// Colonnes : 0 isin,1 nom,2 type,3 pays,4 pea,5 etat,6 score,7 couv,
//            8 vol,9 perf,10 sharpe,11 drawdown,12 date cours,13 age
var D = __DONNEES__;
var SEUIL = __SEUIL__, PARPAGE = 50;
var tri = {c: 6, desc: true}, page = 0, choix = Object.create(null), vue = D;

function $(id){ return document.getElementById(id); }
var corps = $("corps");

function options(sel, valeurs){
  valeurs.sort().forEach(function(v){
    var o = document.createElement("option");
    o.value = v; o.textContent = v; sel.appendChild(o);
  });
}
options($("fType"), Array.from(new Set(D.map(function(r){ return r[2]; }))));
options($("fPays"), Array.from(new Set(D.map(function(r){ return r[3]; }))));
options($("fPea"),  Array.from(new Set(D.map(function(r){ return r[4]; }))));

function esc(s){
  return String(s).replace(/[&<>"']/g, function(c){
    return {"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c];
  });
}
function libelleEtat(e){
  return e === "note" ? "noté" : (e === "collecte" ? "collecté" : "en attente");
}
function cell(v, suffixe){
  return (v === null || v === undefined || v === "") ? "—"
       : (typeof v === "number" ? v.toFixed(1) + (suffixe || "") : v);
}

function filtrer(){
  var q = $("q").value.trim().toLowerCase();
  var ft = $("fType").value, fp = $("fPays").value,
      fe = $("fPea").value, fs = $("fEtat").value;
  vue = D.filter(function(r){
    if (ft && r[2] !== ft) return false;
    if (fp && r[3] !== fp) return false;
    if (fe && r[4] !== fe) return false;
    if (fs && r[5] !== fs) return false;
    if (q && r[1].toLowerCase().indexOf(q) < 0 && r[0].toLowerCase().indexOf(q) < 0) return false;
    return true;
  });
  var c = tri.c;
  vue = vue.slice().sort(function(a, b){
    var x = a[c], y = b[c];
    // Une valeur absente n'est ni bonne ni mauvaise : elle va toujours en fin
    // de liste, quel que soit le sens du tri.
    var vx = (x === null || x === undefined || x === "");
    var vy = (y === null || y === undefined || y === "");
    if (vx && vy) return 0;
    if (vx) return 1;
    if (vy) return -1;
    if (typeof x === "number" && typeof y === "number") return tri.desc ? y - x : x - y;
    return tri.desc ? String(y).localeCompare(String(x), "fr")
                    : String(x).localeCompare(String(y), "fr");
  });
  page = 0;
  rendre();
}

function rendre(){
  var grp = $("grp").value;
  var debut = page * PARPAGE, lot = vue.slice(debut, debut + PARPAGE);
  var lignes = [], dernier = null;
  lot.forEach(function(r){
    if (grp){
      var val = r[Number(grp)] || "—";
      if (val !== dernier){
        dernier = val;
        lignes.push('<tr class="grp"><td colspan="10">' + esc(val) + "</td></tr>");
      }
    }
    var age = r[13];
    var ageTxt = (age === null || age === undefined) ? "—" : age + " j";
    var vieux = (age !== null && age !== undefined && age > SEUIL) ? ' class="nu vieux"' : ' class="nu"';
    lignes.push(
      '<tr><td><input type="checkbox" data-i="' + esc(r[0]) + '"' +
      (choix[r[0]] ? " checked" : "") + ' aria-label="Sélectionner ' + esc(r[1]) + '"></td>' +
      "<td>" + esc(r[1]) + '<br><span class="ty">' + esc(r[0]) + "</span></td>" +
      '<td class="masq-s ty">' + esc(r[2]) + "</td>" +
      '<td class="masq-s ty">' + esc(r[3]) + "</td>" +
      '<td class="ty">' + esc(r[4]) + "</td>" +
      '<td><span class="etat ' + esc(r[5]) + '">' + libelleEtat(r[5]) + "</span></td>" +
      '<td class="nu">' + cell(r[6]) + "</td>" +
      '<td class="nu masq-s">' + cell(r[8], "%") + "</td>" +
      '<td class="nu masq-s">' + cell(r[9], "%") + "</td>" +
      "<td" + vieux + ">" + ageTxt + "</td></tr>");
  });
  corps.innerHTML = lignes.join("") ||
    '<tr><td colspan="10">Aucune ligne ne correspond à ces filtres. ' +
    "Élargir la recherche ou réinitialiser.</td></tr>";
  $("compte").textContent = vue.length.toLocaleString("fr-FR") + " ligne(s) filtrée(s) · " +
    Object.keys(choix).length + " sélectionnée(s)";
  var pages = Math.max(1, Math.ceil(vue.length / PARPAGE));
  $("pagination").textContent = " page " + (page + 1) + " / " + pages + " ";
  $("pageMoins").disabled = page <= 0;
  $("pagePlus").disabled = page >= pages - 1;
  majLot();
}

function majLot(){
  var isins = Object.keys(choix);
  var bloc = $("lot");
  if (!isins.length){ bloc.hidden = true; return; }
  bloc.hidden = false;
  $("lotTitre").textContent = isins.length + " instrument(s) sélectionné(s)";
  $("lotCmd").textContent = isins.length > 12
    ? "# " + isins.length + " ISIN : passer par la file d'attente\n" +
      "python3 scripts/enrich_marche.py --historique \\\n" +
      "    --file-attente data/file_attente.txt --limite 18"
    : "python3 scripts/enrich_marche.py --historique \\\n" +
      "    --isins " + isins.join(",");
}

$("tbl").querySelectorAll("th.tri").forEach(function(th){
  function activer(){
    var c = Number(th.dataset.c);
    if (tri.c === c){ tri.desc = !tri.desc; } else { tri.c = c; tri.desc = true; }
    $("tbl").querySelectorAll("th.tri").forEach(function(x){
      x.classList.remove("actif");
      x.querySelector(".fl").textContent = "▲▼";
    });
    th.classList.add("actif");
    th.querySelector(".fl").textContent = tri.desc ? "▼" : "▲";
    filtrer();
  }
  th.addEventListener("click", activer);
  th.addEventListener("keydown", function(e){
    if (e.key === "Enter" || e.key === " "){ e.preventDefault(); activer(); }
  });
});

corps.addEventListener("change", function(e){
  var cb = e.target;
  if (!cb.dataset || !cb.dataset.i) return;
  if (cb.checked){ choix[cb.dataset.i] = 1; } else { delete choix[cb.dataset.i]; }
  rendre();
});

$("tout").addEventListener("change", function(e){
  // Porte sur l'ensemble du filtre courant, pas sur la seule page affichée :
  // sélectionner des milliers de lignes page par page n'aurait pas de sens.
  if (e.target.checked){ vue.forEach(function(r){ choix[r[0]] = 1; }); }
  else { vue.forEach(function(r){ delete choix[r[0]]; }); }
  rendre();
});

["q","fType","fPays","fPea","fEtat"].forEach(function(id){
  $(id).addEventListener("input", filtrer);
});
$("grp").addEventListener("change", function(){
  // Le regroupement n'a de sens que si le tri suit la même clé.
  var c = Number($("grp").value);
  if (c){ tri.c = c; tri.desc = false; }
  filtrer();
});
$("reset").addEventListener("click", function(){
  ["q","fType","fPays","fPea","fEtat","grp"].forEach(function(id){ $(id).value = ""; });
  tri = {c: 6, desc: true};
  filtrer();
});
$("pageMoins").addEventListener("click", function(){ if (page > 0){ page--; rendre(); } });
$("pagePlus").addEventListener("click", function(){
  if (page < Math.ceil(vue.length / PARPAGE) - 1){ page++; rendre(); }
});
$("vider").addEventListener("click", function(){ choix = Object.create(null); rendre(); });

$("copier").addEventListener("click", function(){
  var bouton = $("copier");
  function retour(msg){
    bouton.textContent = msg;
    setTimeout(function(){ bouton.textContent = "Copier la commande"; }, 1800);
  }
  if (navigator.clipboard && navigator.clipboard.writeText){
    navigator.clipboard.writeText($("lotCmd").textContent)
      .then(function(){ retour("Copié"); }, function(){ retour("Copie refusée"); });
  } else {
    retour("Copie indisponible ici");
  }
});

$("telecharger").addEventListener("click", function(){
  var isins = Object.keys(choix);
  var contenu = "# File d'attente PEA Advisor — " + isins.length + " instrument(s)\n" +
    "# python3 scripts/enrich_marche.py --historique --file-attente <ce fichier>\n" +
    isins.join("\n") + "\n";
  var url = URL.createObjectURL(new Blob([contenu], {type: "text/plain;charset=utf-8"}));
  var a = document.createElement("a");
  a.href = url; a.download = "file_attente.txt";
  document.body.appendChild(a); a.click(); document.body.removeChild(a);
  URL.revokeObjectURL(url);
});

filtrer();
})();
</script>
</body>
</html>"""


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--top", type=int, default=10)
    p.add_argument("--seuil-fraicheur", type=int, default=7,
                   help="âge en jours au-delà duquel un cours est signalé périmé")
    p.add_argument("--data-dir", default="data")
    args = p.parse_args()

    data = Path(args.data_dir)
    if not (data / "base_isin.csv").exists():
        print(f"{data}/base_isin.csv absent.")
        return 1
    sortie = data / "dashboard.html"
    sortie.write_text(construire(data, args.top, args.seuil_fraicheur),
                      encoding="utf-8")
    print(f"{sortie} : {sortie.stat().st_size // 1024} Ko")
    return 0


if __name__ == "__main__":
    sys.exit(main())

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


def sparkline(points, cle, couleur, suffixe="", largeur=250, hauteur=54):
    """Courbe d'évolution en SVG. Rend l'absence de recul explicite plutôt que
    de tracer une ligne rassurante sur deux mesures."""
    valeurs = [nombre(p.get(cle)) for p in points]
    valeurs = [v for v in valeurs if v is not None]
    if len(valeurs) < 2:
        return ('<div class="spark-vide">Pas encore assez de points pour une '
                'courbe — elle s\'étoffera à chaque collecte.</div>')
    bas, haut = min(valeurs), max(valeurs)
    etendue = (haut - bas) or 1
    pas = largeur / (len(valeurs) - 1)
    pts = " ".join(
        f"{i * pas:.1f},{hauteur - 6 - (v - bas) / etendue * (hauteur - 14):.1f}"
        for i, v in enumerate(valeurs))
    dernier = valeurs[-1]
    delta = dernier - valeurs[0]
    signe = "+" if delta > 0 else ""
    return (
        f'<svg class="spark" viewBox="0 0 {largeur} {hauteur}" '
        f'preserveAspectRatio="none" role="img" '
        f'aria-label="Évolution : {dernier:.1f}{suffixe}, '
        f'{signe}{delta:.1f} depuis le premier relevé">'
        f'<polyline points="{pts}" fill="none" stroke="{couleur}" '
        f'stroke-width="2" stroke-linejoin="round"/></svg>'
        f'<div class="spark-l"><b>{dernier:.0f}{suffixe}</b>'
        f'<span>{signe}{delta:.0f} sur {len(valeurs)} relevés</span></div>')


def construire(data, top, seuil):
    base = lire(data / "base_isin.csv")
    fonds = {r["ISIN"]: r for r in lire(data / "base_isin_fonds_pea.csv")}
    marche = lire(data / "base_isin_marche.csv")
    marche_idx = {r["ISIN"]: r for r in marche}
    scores = lire(data / "base_isin_scores.csv")
    scores_idx = {r["ISIN"]: r for r in scores}
    figi = {r["ISIN"]: r for r in lire(data / "base_isin_figi.csv")}
    actions_pea = {r["ISIN"]: r for r in lire(data / "base_isin_actions_pea.csv")}
    corrections = lire(data / "corrections_pea.csv")
    corrections_sri = lire(data / "corrections_sri.csv")
    sri = {r["ISIN"]: r for r in lire(data / "base_isin_sri.csv")}
    anomalies = lire(data / "anomalies.csv")
    histo = lire(data / "historique_couverture.csv")

    # Anomalies groupées par instrument : la ligne de l'explorateur porte un
    # marqueur, le détail reste dans la carte dédiée.
    ano_par_isin = {}
    for a in anomalies:
        ano_par_isin.setdefault(a["ISIN"], []).append(a)

    total = len(base)

    # Lignes de l'explorateur. Tableau plutôt qu'objet : à 6 000 lignes, la
    # différence de poids du fichier est significative.
    lignes = []
    for r in base:
        isin = r["ISIN"]
        m = marche_idx.get(isin, {})
        s = scores_idx.get(isin, {})
        f = fonds.get(isin, {})
        # L'éligibilité vient des fichiers dédiés : le préfixe pays de l'ISIN
        # classait « OUI » des foncières et des bons non éligibles.
        a = actions_pea.get(isin, {})
        pea = f.get("PEA_eligible") or a.get("PEA_eligible") or "A_VERIFIER"
        methode = f.get("PEA_methode") or a.get("PEA_methode") or ""
        motif = f.get("PEA_source") or a.get("PEA_source") or ""
        vigil = a.get("Vigilance") or ""
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
            len(ano_par_isin.get(isin, [])),
            "alerte" if any(x["Gravite"] == "alerte" for x in ano_par_isin.get(isin, []))
            else ("attention" if ano_par_isin.get(isin) else ""),
            nombre(m.get("Sharpe")),
            nombre(m.get("Drawdown_max_pct")),
            methode,
            motif[:90],
            vigil[:120],
            nombre(sri.get(isin, {}).get("SRI_retenu")),
            (sri.get(isin, {}).get("Ecart_officiel") or "")[:110],
            (sri.get(isin, {}).get("Methode") or ""),
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
        "__URL_ACTIONS__": ("https://github.com/FredGarcia/PEAFirst/actions/"
                            "workflows/collecte-marche.yml"),
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
        "__SPARK_NOTES__": sparkline(histo, "Notes", "#2f6f6b"),
        "__SPARK_COUV__": sparkline(histo, "Couverture_moy_pct", "#1f4a5c", " %"),
        "__SPARK_PERIMES__": sparkline(histo, "Cours_perimes", "#b8762a"),
        "__NB_POINTS__": str(len(histo)),
        "__NB_ANO__": str(len(anomalies)),
        "__NB_ANO_INST__": str(len(ano_par_isin)),
        "__NB_CORR__": str(len(corrections)),
        "__CORRECTIONS_SRI__": json.dumps(
            {r["ISIN"]: [r.get("SRI_officiel", ""), r.get("Source", ""),
                         r.get("Date_DIC", ""), r.get("Note", "")]
             for r in corrections_sri if r.get("ISIN")},
            ensure_ascii=False, separators=(",", ":")),
        "__CORRECTIONS__": json.dumps(
            {r["ISIN"]: [r.get("PEA_eligible", ""), r.get("Motif", ""),
                         r.get("Source", "")] for r in corrections
             if r.get("ISIN")}, ensure_ascii=False, separators=(",", ":")),
        "__ANOMALIES__": "".join(
            f'<tr><td>{html.escape(a["Nom"][:30])}</td>'
            f'<td><span class="grav {html.escape(a["Gravite"])}">'
            f'{html.escape(a["Gravite"])}</span></td>'
            f'<td class="ty">{html.escape(a["Anomalie"].replace("_", " "))}</td>'
            f'<td class="ty">{html.escape(a["Detail"])}</td></tr>'
            for a in sorted(anomalies, key=lambda x: x["Gravite"])[:14]) or
            '<tr><td colspan="4">Aucune anomalie détectée sur les instruments '
            'collectés.</td></tr>',
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
.sri{display:inline-block;width:20px;height:20px;line-height:20px;text-align:center;
border-radius:3px;font-family:"IBM Plex Mono",monospace;font-size:12px;cursor:help}
.sri1,.sri2,.sri3{background:#dfeeeb;color:#1d534f}
.sri4,.sri5{background:#fdf1e0;color:#8a5a1c}
.sri6,.sri7{background:#f6e2e2;color:#8a3d3d}
.sri0{background:transparent;color:var(--encre-2)}
/* Un SRI issu d'un DIC est une donnée officielle : le distinguer d'une estimation. */
.sri.officiel{box-shadow:0 0 0 2px var(--encre) inset;font-weight:600}
.vigil{display:inline-block;font-family:"IBM Plex Mono",monospace;font-size:10px;
font-weight:700;width:14px;height:14px;line-height:14px;text-align:center;
border-radius:50%;background:var(--manquant);color:#fff;cursor:help}
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
.progres{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:20px}
.spark{width:100%;height:54px;display:block}
.spark-l{display:flex;justify-content:space-between;align-items:baseline;
gap:8px;font-size:12px;color:var(--encre-2);margin-top:4px}
.spark-l b{font-family:"IBM Plex Mono",monospace;font-size:19px;color:var(--encre)}
.spark-vide{font-size:12.5px;color:var(--encre-2);padding:16px 0;
border-top:1px dashed var(--trait);border-bottom:1px dashed var(--trait)}
.spark-t{font-family:"IBM Plex Mono",monospace;font-size:10px;letter-spacing:.12em;
text-transform:uppercase;color:var(--encre-2);margin-bottom:6px}
.grav{font-size:11px;font-family:"IBM Plex Mono",monospace;padding:2px 6px;border-radius:2px}
.grav.alerte{background:#f6e2e2;color:var(--alerte)}
.grav.attention{background:#fdf1e0;color:#8a5a1c}
.drapeau{font-size:11px;margin-left:5px;cursor:help}
.drapeau.alerte{color:var(--alerte)}
.drapeau.attention{color:var(--manquant)}
.actions{display:flex;flex-wrap:wrap;gap:8px;align-items:center;
padding:11px 13px;margin-bottom:14px;background:#f4f7f8;
border:1px solid var(--trait);border-radius:3px}
.actions .sep{flex:1}
.actions .cnt{font-size:12.5px;color:var(--encre-2);font-family:"IBM Plex Mono",monospace}
button.mini{font-size:12px;padding:5px 10px}
.corr{margin-top:14px;padding:15px;border:1px solid var(--manquant);
border-radius:3px;background:#fdf8f1}
.corr[hidden]{display:none}
.corr .champs{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin:10px 0}
/* La règle ci-dessus l'emporterait sur l'attribut hidden du navigateur : il
   faut la neutraliser explicitement, sinon les deux modes s'affichent ensemble. */
.corr .champs[hidden],.corr [hidden]{display:none}
.corr select,.corr input[type=text]{font-family:inherit;font-size:13px;padding:6px 8px;
border:1px solid var(--trait);border-radius:3px;background:#fff;color:inherit}
.corr input[type=text]{flex:1 1 240px}
.corr ul{list-style:none;margin:10px 0 0;padding:0;font-size:13px;
max-height:190px;overflow-y:auto}
.corr li{display:flex;gap:9px;align-items:baseline;padding:4px 0;
border-bottom:1px solid #f0e6d8}
.corr li b{font-family:"IBM Plex Mono",monospace}
.corr li .m{flex:1;color:var(--encre-2)}
.corr li button{padding:1px 7px;font-size:11px}
.pilote{margin-top:14px;padding:15px;border:1px solid var(--couvert);
border-radius:3px;background:#f2f8f7}
.pilote h3{font-family:"IBM Plex Sans Condensed",sans-serif;font-size:13px;
letter-spacing:.1em;text-transform:uppercase;margin:0 0 4px;color:var(--encre)}
.pilote .champs{display:flex;flex-wrap:wrap;gap:8px;margin:10px 0}
.pilote select{font-family:inherit;font-size:13px;padding:6px 8px;
border:1px solid var(--trait);border-radius:3px;background:#fff;color:inherit}
a.bouton{display:inline-block;font-family:inherit;font-size:13px;padding:7px 13px;
border:1px solid var(--encre);border-radius:3px;background:var(--encre);
color:#fff;text-decoration:none}
a.bouton:hover{opacity:.9}
.comp{margin-top:14px;padding:15px;border:1px solid var(--couvert);
border-radius:3px;background:#f2f8f7}
.comp[hidden]{display:none}
.comp table{margin-top:9px}
.comp th{white-space:nowrap}
.mieux{font-weight:600;color:var(--couvert)}
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
  <h2>Progression de la collecte (__NB_POINTS__ relevés)</h2>
  <div class="progres">
    <div><div class="spark-t">Instruments notés</div>__SPARK_NOTES__</div>
    <div><div class="spark-t">Couverture moyenne</div>__SPARK_COUV__</div>
    <div><div class="spark-t">Cours périmés</div>__SPARK_PERIMES__</div>
  </div>
  <p class="note">Les scores ne valent que par l'étendue et la fraîcheur des
  données qui les nourrissent. Une courbe qui stagne signale un quota épuisé ou
  un workflow en échec — ce qu'aucun score ne montrerait.</p>
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
    <select id="fVigil" aria-label="Filtrer par vigilance">
      <option value="">Éligibilité : tout</option>
      <option value="vig">À contrôler (régime immobilier possible)</option>
      <option value="ver">Statut indéterminé</option>
    </select>
    <select id="grp" aria-label="Regrouper les lignes">
      <option value="">Sans regroupement</option><option value="2">Grouper par nature</option>
      <option value="3">Grouper par pays</option><option value="4">Grouper par éligibilité PEA</option>
      <option value="5">Grouper par état des données</option>
    </select>
    <button type="button" class="sec" id="reset">Réinitialiser</button>
  </div>

  <div class="actions">
    <span class="cnt" id="cnt"></span>
    <button type="button" class="sec mini" id="expCsv">Exporter la vue (CSV)</button>
    <button type="button" class="sec mini" id="copIsin" disabled>Copier les ISIN</button>
    <button type="button" class="sec mini" id="telecharger" disabled>File d'attente</button>
    <button type="button" class="sec mini" id="cmdAlloc" disabled>Commande d'allocation</button>
    <button type="button" class="sec mini" id="pilote">Piloter la collecte</button>
    <button type="button" class="sec mini" id="corriger" disabled>Corriger l'éligibilité PEA</button>
    <span class="sep"></span>
    <button type="button" class="sec mini" id="vider" disabled>Vider la sélection</button>
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
      <th class="tri nu" data-c="21" tabindex="0">SRI <span class="fl">▲▼</span></th>
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

  <div class="corr" id="corr" hidden>
    <strong>Corriger une donnée</strong>
    <div class="champs" style="margin-bottom:0">
      <select id="cType" aria-label="Donnée à corriger">
        <option value="pea">Éligibilité PEA</option>
        <option value="sri">SRI officiel relevé sur un DIC</option>
      </select>
    </div>
    <p class="note" style="margin-top:4px">
      <span id="cNotePea">L'éligibilité est déduite de règles automatiques :
      régime foncier, nature de l'instrument, pays d'émission. Ces règles se
      trompent — une correction saisie ici <b>prime sur toutes</b>. Elle prend
      effet à la prochaine exécution de <code>enrich_pea_actions.py</code>,
      après avoir remplacé <code>data/corrections_pea.csv</code> par le fichier
      téléchargé.</span>
      <span id="cNoteSri" hidden>Le SRI affiché est une <b>estimation</b>
      calculée depuis la volatilité. Le chiffre du document d'informations clés
      de l'émetteur est le SRI réglementaire : saisi ici, il <b>remplace</b>
      l'estimation. Indiquer la date du DIC — un SRI est révisable, et un relevé
      ancien reste un relevé ancien. Prend effet après avoir remplacé
      <code>data/corrections_sri.csv</code> puis relancé
      <code>sri.py</code>.</span>
    </p>
    <div class="champs" id="cChampsPea">
      <select id="cVal" aria-label="Éligibilité corrigée">
        <option value="NON">NON — réservée au compte-titres</option>
        <option value="OUI">OUI — éligible au PEA</option>
        <option value="A_VERIFIER">A_VERIFIER — statut incertain</option>
      </select>
      <input type="text" id="cMotif" placeholder="Motif (ex. : foncière, statut SIIC)"
             aria-label="Motif de la correction">
      <button type="button" id="cAjouter">Appliquer à la sélection</button>
    </div>
    <div class="champs" id="cChampsSri" hidden>
      <select id="sVal" aria-label="SRI officiel">
        <option value="1">SRI 1</option><option value="2">SRI 2</option>
        <option value="3">SRI 3</option><option value="4" selected>SRI 4</option>
        <option value="5">SRI 5</option><option value="6">SRI 6</option>
        <option value="7">SRI 7</option>
      </select>
      <input type="text" id="sSource" placeholder="Source (ex. : amundietf.fr)"
             aria-label="Source du DIC">
      <input type="date" id="sDate" aria-label="Date du DIC"
             style="font-family:inherit;font-size:13px;padding:6px 8px;
                    border:1px solid var(--trait);border-radius:3px">
      <button type="button" id="sAjouter">Appliquer à la sélection</button>
    </div>
    <ul id="cListe"></ul>
    <p class="note" id="cVide">Aucune correction enregistrée.</p>
    <button type="button" id="cTelecharger">Télécharger corrections_pea.csv</button>
    <button type="button" id="sTelecharger" hidden>Télécharger corrections_sri.csv</button>
    <button type="button" class="sec" id="cFermer">Fermer</button>
  </div>

  <div class="pilote" id="pil" hidden>
    <h3>Piloter la collecte depuis GitHub Actions</h3>
    <p class="note" style="margin-top:4px">
      Les clés sont stockées comme secrets du dépôt : le traitement s'exécute
      chez GitHub, pas dans cette page, qui n'en contient aucune. Choisir les
      paramètres, copier la valeur du champ <i>isins</i> si une sélection est
      active, puis ouvrir <i>Run workflow</i> et la coller.
    </p>
    <div class="champs">
      <select id="pMode" aria-label="Traitement">
        <option value="historique">historique — cours et indicateurs</option>
        <option value="cours">cours — dernier cours en masse</option>
        <option value="openfigi">openfigi — identifiants et éligibilité</option>
      </select>
      <select id="pSource" aria-label="Fournisseur">
        <option value="eodhd">eodhd — 20/jour, Euronext large</option>
        <option value="marketstack">marketstack — 100/mois, lots de 50</option>
      </select>
      <select id="pFiltre" aria-label="Univers">
        <option value="pea">pea</option><option value="actions">actions</option>
        <option value="etf">etf</option><option value="tout">tout</option>
      </select>
      <select id="pLimite" aria-label="Nombre d'instruments">
        <option>18</option><option>10</option><option>50</option><option>100</option>
      </select>
    </div>
    <code id="pilResume"></code>
    <a class="bouton" id="pilLien" href="__URL_ACTIONS__" target="_blank"
       rel="noopener">Ouvrir Run workflow</a>
    <button type="button" class="sec" id="pilCopie">Copier les paramètres</button>
    <button type="button" class="sec" id="pilFermer">Fermer</button>
    <p class="note" id="pilQuota"></p>
  </div>

  <div class="comp" id="comp" hidden>
    <strong>Comparaison</strong>
    <div class="tbl-wrap"><table id="compTbl"></table></div>
    <p class="note">La meilleure valeur de chaque ligne est mise en évidence.
    Comparer au-delà de cinq instruments devient illisible : affiner la
    sélection.</p>
  </div>

  <div class="lot" id="lot" hidden>
    <strong id="lotTitre"></strong>
    <p class="note" style="margin-top:6px">
      Cette page ne contient aucune clé d'API : elle est versionnée sur GitHub, où
      une clé serait exposée. Le lot est donc préparé ici et exécuté par le script.
    </p>
    <code id="lotCmd"></code>
    <button type="button" id="copier">Copier la commande</button>
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
  <h2>Anomalies détectées (__NB_ANO__ sur __NB_ANO_INST__ instrument(s))</h2>
  <table><thead><tr><th>Instrument</th><th>Gravité</th><th>Type</th>
    <th>Détail</th></tr></thead><tbody>__ANOMALIES__</tbody></table>
  <p class="note">Un indicateur spectaculaire est plus souvent le symptôme d'une
  donnée douteuse que d'une opportunité : un Sharpe très élevé sur un titre peu
  échangé traduit une série de cours plate, pas une performance exceptionnelle.
  Ces signalements demandent une vérification, ils ne disqualifient pas
  l'instrument.</p>
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
//            8 vol,9 perf,10 sharpe,11 drawdown,12 date cours,13 age,
//            14 nb anomalies,15 gravite max,16 sharpe,17 drawdown,
//            18 methode PEA,19 motif PEA,20 vigilance,21 SRI retenu,
//            22 reserve SRI,23 methode SRI
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
// Retour visuel sur un bouton : une action sans effet visible laisse croire
// qu'elle a échoué.
function retour(bouton, message){
  var initial = bouton.dataset.txt || bouton.textContent;
  bouton.dataset.txt = initial;
  bouton.textContent = message;
  setTimeout(function(){ bouton.textContent = bouton.dataset.txt; }, 1800);
}

function telecharger(nom, contenu, type){
  var url = URL.createObjectURL(new Blob([contenu], {type: type}));
  var a = document.createElement("a");
  a.href = url; a.download = nom;
  document.body.appendChild(a); a.click(); document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

function presse(texte, bouton, ok){
  if (navigator.clipboard && navigator.clipboard.writeText){
    navigator.clipboard.writeText(texte).then(
      function(){ retour(bouton, ok); },
      function(){ retour(bouton, "Copie refusée"); });
  } else {
    retour(bouton, "Copie indisponible ici");
  }
}

function drapeau(r){
  if (!r[14]) return "";
  var t = r[14] + " anomalie(s) signalée(s) — voir la carte Anomalies";
  return ' <span class="drapeau ' + esc(r[15]) + '" title="' + t + '">&#9650;</span>';
}
function cell(v, suffixe){
  return (v === null || v === undefined || v === "") ? "—"
       : (typeof v === "number" ? v.toFixed(1) + (suffixe || "") : v);
}

function filtrer(){
  var q = $("q").value.trim().toLowerCase();
  var ft = $("fType").value, fp = $("fPays").value,
      fe = $("fPea").value, fs = $("fEtat").value, fv = $("fVigil").value;
  vue = D.filter(function(r){
    if (ft && r[2] !== ft) return false;
    if (fp && r[3] !== fp) return false;
    if (fe && r[4] !== fe) return false;
    if (fs && r[5] !== fs) return false;
    if (fv === "vig" && !r[20]) return false;
    if (fv === "ver" && r[4] !== "A_VERIFIER") return false;
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
        lignes.push('<tr class="grp"><td colspan="11">' + esc(val) + "</td></tr>");
      }
    }
    var age = r[13];
    var ageTxt = (age === null || age === undefined) ? "—" : age + " j";
    var vieux = (age !== null && age !== undefined && age > SEUIL) ? ' class="nu vieux"' : ' class="nu"';
    lignes.push(
      '<tr><td><input type="checkbox" data-i="' + esc(r[0]) + '"' +
      (choix[r[0]] ? " checked" : "") + ' aria-label="Sélectionner ' + esc(r[1]) + '"></td>' +
      "<td>" + esc(r[1]) + drapeau(r) + '<br><span class="ty">' + esc(r[0]) + "</span></td>" +
      '<td class="masq-s ty">' + esc(r[2]) + "</td>" +
      '<td class="masq-s ty">' + esc(r[3]) + "</td>" +
      '<td class="ty" title="' + esc((r[18] || "") + (r[19] ? " — " + r[19] : "") +
        (r[20] ? "\nÀ CONTRÔLER : " + r[20] : "")) + '">' + esc(r[4]) +
        (r[20] ? ' <span class="vigil" title="' + esc(r[20]) + '">!</span>' : "") +
        "</td>" +
      '<td><span class="etat ' + esc(r[5]) + '">' + libelleEtat(r[5]) + "</span></td>" +
      '<td class="nu"><span class="sri sri' + (r[21] || 0) +
        (r[23] === "dic_emetteur" ? " officiel" : "") + '" title="' +
        esc(r[22] || "") + '">' + (r[21] || "—") + "</span></td>" +
      '<td class="nu">' + cell(r[6]) + "</td>" +
      '<td class="nu masq-s">' + cell(r[8], "%") + "</td>" +
      '<td class="nu masq-s">' + cell(r[9], "%") + "</td>" +
      "<td" + vieux + ">" + ageTxt + "</td></tr>");
  });
  corps.innerHTML = lignes.join("") ||
    '<tr><td colspan="11">Aucune ligne ne correspond à ces filtres. ' +
    "Élargir la recherche ou réinitialiser.</td></tr>";
  var pages = Math.max(1, Math.ceil(vue.length / PARPAGE));
  $("pagination").textContent = " page " + (page + 1) + " / " + pages + " ";
  $("pageMoins").disabled = page <= 0;
  $("pagePlus").disabled = page >= pages - 1;
  majPanneaux();
}

// Cocher une case ne doit pas reconstruire le tableau : cela détacherait les
// autres cases et ferait perdre le focus au clavier. Seuls les panneaux qui
// dépendent de la sélection sont rafraîchis.
function majPanneaux(){
  var n = Object.keys(choix).length;
  var texte = vue.length.toLocaleString("fr-FR") + " ligne(s) filtrée(s) · " +
    n + " sélectionnée(s)";
  $("compte").textContent = texte;
  $("cnt").textContent = texte;
  // Un bouton sans objet est désactivé plutôt que silencieusement inopérant.
  ["copIsin", "telecharger", "cmdAlloc", "vider", "corriger"].forEach(function(id){
    $(id).disabled = (n === 0);
  });
  majComp();
  majLot();
  if (!$("pil").hidden) majPilote();
}

// Comparateur : au-delà de cinq colonnes le tableau devient illisible, et
// en deçà de deux il n'y a rien à comparer.
var CRITERES_COMP = [
  {l: "Score /100", i: 6, s: "", mieux: 1},
  {l: "Couverture", i: 7, s: " %", mieux: 1},
  {l: "Performance", i: 9, s: " %", mieux: 1},
  {l: "Volatilité", i: 8, s: " %", mieux: -1},
  {l: "Sharpe", i: 16, s: "", mieux: 1},
  {l: "Drawdown max", i: 17, s: " %", mieux: 1},
  {l: "Âge du cours", i: 13, s: " j", mieux: -1, entier: true}
];

function majComp(){
  var bloc = $("comp");
  var isins = Object.keys(choix);
  if (isins.length < 2 || isins.length > 5){ bloc.hidden = true; return; }
  var index = Object.create(null);
  D.forEach(function(r){ if (choix[r[0]]) index[r[0]] = r; });
  var lignes = isins.map(function(i){ return index[i]; }).filter(Boolean);
  // Sans indicateurs, il n'y a rien à comparer : mieux vaut le dire.
  var exploitables = lignes.filter(function(r){ return r[8] !== null && r[8] !== undefined; });
  if (exploitables.length < 2){
    bloc.hidden = false;
    $("compTbl").innerHTML = '<tr><td>Au moins deux instruments collectés sont ' +
      "nécessaires : la sélection actuelle n'a pas encore de données de marché.</td></tr>";
    return;
  }
  bloc.hidden = false;
  var html = "<thead><tr><th>Critère</th>" + exploitables.map(function(r){
    return "<th>" + esc(r[1].slice(0, 22)) + "</th>";
  }).join("") + "</tr></thead><tbody>";
  CRITERES_COMP.forEach(function(c){
    var vals = exploitables.map(function(r){ return r[c.i]; });
    var num = vals.filter(function(v){ return typeof v === "number"; });
    var best = null;
    // Ne rien mettre en évidence si toutes les valeurs sont identiques :
    // surligner l'ensemble d'une ligne n'apprend rien.
    var varie = num.length > 1 && Math.min.apply(null, num) !== Math.max.apply(null, num);
    if (varie) { best = c.mieux > 0 ? Math.max.apply(null, num) : Math.min.apply(null, num); }
    html += "<tr><td>" + c.l + "</td>" + vals.map(function(v){
      var t = (v === null || v === undefined) ? "—"
            : (typeof v === "number" ? (c.entier ? String(Math.round(v)) : v.toFixed(1)) + c.s : v);
      var cl = (varie && v === best) ? ' class="nu mieux"' : ' class="nu"';
      return "<td" + cl + ">" + t + "</td>";
    }).join("") + "</tr>";
  });
  $("compTbl").innerHTML = html + "</tbody>";
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
  majPanneaux();
});

$("tout").addEventListener("change", function(e){
  // Porte sur l'ensemble du filtre courant, pas sur la seule page affichée :
  // sélectionner des milliers de lignes page par page n'aurait pas de sens.
  if (e.target.checked){ vue.forEach(function(r){ choix[r[0]] = 1; }); }
  else { vue.forEach(function(r){ delete choix[r[0]]; }); }
  rendre();
});

["q","fType","fPays","fPea","fEtat","fVigil"].forEach(function(id){
  $(id).addEventListener("input", filtrer);
});
$("grp").addEventListener("change", function(){
  // Le regroupement n'a de sens que si le tri suit la même clé.
  var c = Number($("grp").value);
  if (c){ tri.c = c; tri.desc = false; }
  filtrer();
});
$("reset").addEventListener("click", function(){
  ["q","fType","fPays","fPea","fEtat","fVigil","grp"].forEach(function(id){ $(id).value = ""; });
  tri = {c: 6, desc: true};
  filtrer();
});
$("pageMoins").addEventListener("click", function(){ if (page > 0){ page--; rendre(); } });
$("pagePlus").addEventListener("click", function(){
  if (page < Math.ceil(vue.length / PARPAGE) - 1){ page++; rendre(); }
});
$("vider").addEventListener("click", function(){
  choix = Object.create(null);
  rendre();
});

$("expCsv").addEventListener("click", function(){
  // Exporte la vue telle qu'elle est filtrée et triée à l'écran : ce que
  // l'utilisateur voit est ce qu'il obtient.
  var entetes = ["ISIN","Nom","Type","Pays","PEA","Etat","Score","Couverture_pct",
                 "Volatilite_pct","Perf_pct","Sharpe","Drawdown_pct","Date_cours",
                 "Age_jours","Anomalies"];
  var idx = [0,1,2,3,4,5,6,7,8,9,16,17,12,13,14];
  function champ(v){
    if (v === null || v === undefined) return "";
    var t = String(v);
    return (t.indexOf(";") >= 0 || t.indexOf('"') >= 0)
      ? '"' + t.replace(/"/g, '""') + '"' : t;
  }
  var lignes = [entetes.join(";")];
  vue.forEach(function(r){
    lignes.push(idx.map(function(i){ return champ(r[i]); }).join(";"));
  });
  // BOM UTF-8 : sans lui, Excel affiche mal les accents.
  telecharger("vue_peafirst.csv", "\ufeff" + lignes.join("\r\n") + "\r\n",
              "text/csv;charset=utf-8");
  retour(this, vue.length + " ligne(s) exportée(s)");
});

$("copIsin").addEventListener("click", function(){
  presse(Object.keys(choix).join("\n"), this,
         Object.keys(choix).length + " ISIN copiés");
});

$("cmdAlloc").addEventListener("click", function(){
  // L'allocation se calcule sur les instruments notés : la commande produite
  // rappelle les paramètres à ajuster plutôt que d'en imposer.
  presse("python3 scripts/allocation.py --capital 10000 --risque 5 \\\n" +
         "    --horizon 10 --objectif croissance --pea-uniquement",
         this, "Commande copiée");
});

// Corrections d'éligibilité. Elles priment sur les règles automatiques ;
// le fichier téléchargé remplace data/corrections_pea.csv.
var CORR = __CORRECTIONS__;
var CORRSRI = __CORRECTIONS_SRI__;

function majCorr(){
  var sri = $("cType").value === "sri";
  // Les deux corrections ne se mélangent pas : chacune a son fichier, sa
  // priorité et son script. L'interface bascule entièrement d'un mode à l'autre.
  $("cChampsPea").hidden = sri;
  $("cChampsSri").hidden = !sri;
  $("cNotePea").hidden = sri;
  $("cNoteSri").hidden = !sri;
  $("cTelecharger").hidden = sri;
  $("sTelecharger").hidden = !sri;

  var table = sri ? CORRSRI : CORR;
  var cles = Object.keys(table);
  $("cVide").hidden = cles.length > 0;
  $("cVide").textContent = sri
    ? "Aucun SRI officiel enregistré."
    : "Aucune correction enregistrée.";
  $("cTelecharger").disabled = cles.length === 0;
  $("sTelecharger").disabled = cles.length === 0;

  var index = Object.create(null);
  var estime = Object.create(null);
  D.forEach(function(r){
    if (table[r[0]]) { index[r[0]] = r[1]; estime[r[0]] = r[21]; }
  });
  $("cListe").innerHTML = cles.map(function(i){
    var c = table[i];
    var tete = sri ? ("SRI " + esc(c[0])) : esc(c[0]);
    var detail = sri
      ? esc((c[1] || "") + (c[2] ? " · DIC du " + c[2] : ""))
      : esc(c[1] || "");
    return "<li><b>" + tete + "</b><span>" + esc(index[i] || i) +
      '</span><span class="m">' + detail + "</span>" +
      '<button type="button" class="sec" data-sup="' + esc(i) + '">retirer</button></li>';
  }).join("");
}

$("cType").addEventListener("change", majCorr);

$("sAjouter").addEventListener("click", function(){
  var isins = Object.keys(choix);
  if (!isins.length){ retour(this, "Aucune ligne sélectionnée"); return; }
  var v = $("sVal").value;
  var src = $("sSource").value.trim() || "DIC émetteur";
  var d = $("sDate").value;
  isins.forEach(function(i){ CORRSRI[i] = [v, src, d, ""]; });
  majCorr();
  retour(this, isins.length + " SRI officiel(s) enregistré(s)");
});

$("sTelecharger").addEventListener("click", function(){
  function champ(t){
    t = String(t === null || t === undefined ? "" : t);
    return (t.indexOf(";") >= 0 || t.indexOf('"') >= 0)
      ? '"' + t.replace(/"/g, '""') + '"' : t;
  }
  var lignes = ["ISIN;SRI_officiel;Source;Date_DIC;Note"];
  Object.keys(CORRSRI).sort().forEach(function(i){
    var c = CORRSRI[i];
    lignes.push([i, c[0], champ(c[1]), c[2] || "", champ(c[3] || "")].join(";"));
  });
  telecharger("corrections_sri.csv", lignes.join("\r\n") + "\r\n",
              "text/csv;charset=utf-8");
  retour(this, Object.keys(CORRSRI).length + " SRI exporté(s)");
});

$("corriger").addEventListener("click", function(){
  var bloc = $("corr");
  bloc.hidden = !bloc.hidden;
  if (!bloc.hidden) majCorr();
});
$("cFermer").addEventListener("click", function(){ $("corr").hidden = true; });

$("cAjouter").addEventListener("click", function(){
  var isins = Object.keys(choix);
  if (!isins.length){ retour(this, "Aucune ligne sélectionnée"); return; }
  var valeur = $("cVal").value;
  var motif = $("cMotif").value.trim() || "correction manuelle";
  isins.forEach(function(i){ CORR[i] = [valeur, motif, "tableau de bord"]; });
  majCorr();
  retour(this, isins.length + " correction(s) enregistrée(s)");
});

$("cListe").addEventListener("click", function(e){
  var b = e.target;
  if (!b.dataset || !b.dataset.sup) return;
  if ($("cType").value === "sri") { delete CORRSRI[b.dataset.sup]; }
  else { delete CORR[b.dataset.sup]; }
  majCorr();
});

$("cTelecharger").addEventListener("click", function(){
  var jour = new Date().toISOString().slice(0, 10);
  function champ(t){
    t = String(t === null || t === undefined ? "" : t);
    return (t.indexOf(";") >= 0 || t.indexOf('"') >= 0)
      ? '"' + t.replace(/"/g, '""') + '"' : t;
  }
  var lignes = ["ISIN;PEA_eligible;Motif;Source;Date"];
  Object.keys(CORR).sort().forEach(function(i){
    var c = CORR[i];
    lignes.push([i, c[0], champ(c[1]), champ(c[2] || "tableau de bord"), jour].join(";"));
  });
  telecharger("corrections_pea.csv", lignes.join("\r\n") + "\r\n",
              "text/csv;charset=utf-8");
  retour(this, Object.keys(CORR).length + " correction(s) exportée(s)");
});

function majPilote(){
  var mode = $("pMode").value;
  var source = $("pSource").value;
  var isins = Object.keys(choix);
  // La source ne concerne que le mode historique ; l'univers est ignoré dès
  // qu'un lot explicite est fourni.
  $("pSource").disabled = (mode !== "historique");
  $("pFiltre").disabled = (mode === "openfigi" || isins.length > 0);
  $("pLimite").disabled = (mode === "openfigi");

  var lignes = ["mode    : " + mode];
  if (mode === "historique") lignes.push("source  : " + source);
  if (mode !== "openfigi"){
    lignes.push("filtre  : " + (isins.length ? "(ignoré — lot explicite)" : $("pFiltre").value));
    lignes.push("limite  : " + $("pLimite").value);
    lignes.push("isins   : " + (isins.length ? isins.join(",") : "(vide)"));
  }
  $("pilResume").textContent = lignes.join("\n");

  var q = "";
  if (mode === "openfigi"){
    q = "Le mode openfigi retraite toute la base et régénère l'éligibilité PEA. " +
        "Avec une clé, il consomme environ 62 requêtes OpenFIGI.";
  } else if (mode === "cours" || source === "marketstack"){
    q = "Marketstack : quota mensuel de 100 requêtes, qui ne se régénère pas " +
        "avant le mois suivant. À réserver aux collectes en masse.";
  } else {
    q = "EODHD : 20 requêtes par jour, régénérées chaque nuit. Rester sous 18 " +
        "laisse une marge.";
  }
  $("pilQuota").textContent = q;
}

["pMode","pSource","pFiltre","pLimite"].forEach(function(id){
  $(id).addEventListener("change", majPilote);
});
$("pilote").addEventListener("click", function(){
  var bloc = $("pil");
  bloc.hidden = !bloc.hidden;
  if (!bloc.hidden) majPilote();
});
$("pilFermer").addEventListener("click", function(){ $("pil").hidden = true; });
$("pilCopie").addEventListener("click", function(){
  presse($("pilResume").textContent, this, "Paramètres copiés");
});

$("copier").addEventListener("click", function(){
  presse($("lotCmd").textContent, this, "Copié");
});

$("telecharger").addEventListener("click", function(){
  var isins = Object.keys(choix);
  var contenu = "# File d'attente PEA Advisor — " + isins.length + " instrument(s)\n" +
    "# python3 scripts/enrich_marche.py --historique --file-attente <ce fichier>\n" +
    isins.join("\n") + "\n";
  telecharger("file_attente.txt", contenu, "text/plain;charset=utf-8");
  retour(this, isins.length + " ISIN exportés");
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

/* PEAdvisor — application monopage (vanilla JS, aucune dépendance). */

const contenu = document.getElementById("contenu");

// Barre latérale : largeur ajustable soit par glisser (double flèche), soit par
// le paramètre « Largeur de la barre » (onglet Paramètres). Persistée en
// localStorage (immédiat) et dans le profil (partagé entre postes).
function appliquerLargeurBarre(px) {
  const sidebar = document.querySelector(".sidebar");
  if (!sidebar || !px) return;
  const largeur = Math.min(420, Math.max(140, Number(px)));
  sidebar.style.width = largeur + "px";
  localStorage.setItem("peadvisor-sidebar", largeur);
}

(function initRedimensionnement() {
  const sidebar = document.querySelector(".sidebar");
  const poignee = document.getElementById("sidebar-resize");
  if (!sidebar) return;
  const sauvegardee = localStorage.getItem("peadvisor-sidebar");
  if (sauvegardee) sidebar.style.width = sauvegardee + "px";
  if (!poignee) return;
  let actif = false;
  poignee.addEventListener("mousedown", (e) => { actif = true; e.preventDefault();
    document.body.style.userSelect = "none"; });
  window.addEventListener("mousemove", (e) => {
    if (!actif) return;
    const largeur = Math.min(420, Math.max(140, e.clientX));
    sidebar.style.width = largeur + "px";
  });
  window.addEventListener("mouseup", () => {
    if (!actif) return;
    actif = false;
    document.body.style.userSelect = "";
    const largeur = parseInt(sidebar.style.width, 10);
    localStorage.setItem("peadvisor-sidebar", largeur);
    // Persistance dans le profil (sans bloquer l'UI).
    fetch("/api/parametres/profil", {
      method: "PUT", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ largeur_barre: largeur }),
    }).catch(() => {});
  });
})();

async function api(chemin, options) {
  const rep = await fetch(chemin, options);
  if (!rep.ok) throw new Error((await rep.json()).detail || rep.statusText);
  return rep.json();
}

const fmt = (v, dec = 1, unite = "") =>
  v === null || v === undefined ? "—" : `${Number(v).toFixed(dec)}${unite}`;
const euros = (v) => new Intl.NumberFormat("fr-FR", { style: "currency", currency: "EUR" }).format(v);
const echap = (s) => String(s ?? "").replace(/[&<>"']/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

/* --- Fenêtre modale (confirmations, erreurs) -------------------------- */

function fermerModal() {
  const m = document.getElementById("modal-overlay");
  if (m) m.remove();
}

function ouvrirModal(titre, corpsHTML, actions) {
  fermerModal();
  const ov = document.createElement("div");
  ov.id = "modal-overlay";
  ov.className = "modal-overlay";
  ov.innerHTML = `<div class="modal" role="dialog" aria-modal="true">
    <h3>${echap(titre)}</h3>
    <div class="modal-corps">${corpsHTML}</div>
    <div class="modal-actions"></div></div>`;
  const zone = ov.querySelector(".modal-actions");
  (actions || [{ libelle: "Fermer", secondaire: true }]).forEach((a) => {
    const b = document.createElement("button");
    b.textContent = a.libelle;
    if (a.secondaire) b.className = "secondaire";
    b.addEventListener("click", () => { if (a.ferme !== false) fermerModal(); if (a.onClick) a.onClick(); });
    zone.appendChild(b);
  });
  ov.addEventListener("click", (e) => { if (e.target === ov) fermerModal(); });
  document.addEventListener("keydown", function esc(e) {
    if (e.key === "Escape") { fermerModal(); document.removeEventListener("keydown", esc); }
  });
  document.body.appendChild(ov);
}

// Lien vers la fiche d'une valeur sur sa source, par ISIN (repli : Boursorama).
const FICHE_SOURCE = {
  boursorama: (isin) => `https://www.boursorama.com/recherche/${isin}`,
  boursier: (isin) => `https://www.boursier.com/recherche/rapide?q=${isin}`,
  zonebourse: (isin) => `https://www.zonebourse.com/recherche/?q=${isin}`,
  boursedirect: (isin) => `https://www.boursedirect.fr/fr/recherche/${isin}`,
  ouestfrance: (isin) => `https://bourse.ouest-france.fr/recherche/?q=${isin}`,
  euronext: (isin) => `https://live.euronext.com/en/search_instruments/${isin}`,
};
function lienFiche(source, isin) {
  const f = FICHE_SOURCE[source] || FICHE_SOURCE.boursorama;
  return f(encodeURIComponent(isin || ""));
}

// Cache (durée de session) du dernier diagnostic des sources, pour recolorer
// les boutons à chaque rendu sans re-tester le réseau.
let etatsSourcesCache = null;
function appliquerEtatsSources() {
  if (!etatsSourcesCache) return;
  document.querySelectorAll(".btn-source").forEach((b) => {
    const etat = etatsSourcesCache.parNom[b.dataset.source];
    b.classList.remove("src-disponible", "src-vide", "src-indispo");
    if (etat === "disponible") b.classList.add("src-disponible");
    else if (etat === "vide") b.classList.add("src-vide");
    else if (etat === "indisponible") b.classList.add("src-indispo");
  });
}

// Fige les `nbFixes` premières colonnes au défilement horizontal : calcule le
// décalage gauche cumulé de chaque colonne figée (largeurs variables).
function figerColonnes(nbFixes) {
  const table = document.querySelector("table.valeurs");
  if (!table || !nbFixes) return;
  const entetes = [...table.querySelectorAll("thead th")];
  let gauche = 0;
  for (let i = 0; i < nbFixes; i++) {
    const largeur = entetes[i].getBoundingClientRect().width;
    table.querySelectorAll(`tr > *:nth-child(${i + 1})`).forEach((cel) => {
      cel.style.left = gauche + "px";
    });
    gauche += largeur;
  }
}

/* --- Composants ------------------------------------------------------- */

function tuile(libelle, valeur, unite = "") {
  return `<div class="tuile"><div class="libelle">${libelle}</div>
    <div class="valeur">${valeur}<span class="unite">${unite}</span></div></div>`;
}

function grapheBarres(titre, donnees) {
  const max = Math.max(...Object.values(donnees), 1);
  const lignes = Object.entries(donnees).map(([cle, val]) => `
    <div class="barre-ligne" title="${echap(cle)} : ${val}">
      <span class="etiquette">${echap(cle)}</span>
      <span class="barre-piste"><span class="barre" style="width:${(val / max) * 100}%"></span></span>
      <span class="nombre">${val}</span>
    </div>`).join("");
  return `<div class="carte"><h3>${titre}</h3>${lignes}</div>`;
}

function tableTop(titre, lignes, unite) {
  const corps = lignes.map((l) => `<tr>
      <td><span class="pastille ${l.type}"></span>${echap(l.nom)}</td>
      <td class="num">${fmt(l.valeur, 1, unite)}</td>
      <td class="num score-badge">${fmt(l.score_global, 0)}</td>
    </tr>`).join("");
  return `<div class="carte"><h3>${titre}</h3><div class="table-scroll"><table>
    <thead><tr><th>Valeur</th><th class="num">Indicateur</th><th class="num">Score</th></tr></thead>
    <tbody>${corps}</tbody></table></div></div>`;
}

/* --- Vues -------------------------------------------------------------- */

async function vueDashboard() {
  const [s, profil] = await Promise.all([
    api("/api/dashboard/synthese"),
    api("/api/parametres/profil"),
  ]);
  const algo = profil.algorithme_decision || "topsis";
  const classement = await api(`/api/dashboard/classement?methode=${algo}&limite=10`);
  contenu.innerHTML = `
    <h1>Tableau de bord</h1>
    <p class="sous-titre">${s.nb_actifs} actifs éligibles PEA suivis — données indicatives, ceci n'est pas un conseil en investissement.</p>
    <div class="tuiles">
      ${tuile("Actifs suivis", s.nb_actifs)}
      ${tuile("Score moyen", fmt(s.score_moyen, 1), "/100")}
      ${tuile("Score ESG moyen", fmt(s.score_esg_moyen, 1), "/100")}
      ${tuile("Rendement moyen", fmt(s.rendement_moyen, 2), " %")}
      ${tuile("Potentiel moyen", fmt(s.potentiel_moyen, 1), " %")}
      ${tuile("Risque moyen", fmt(s.niveau_risque_moyen, 1), "/7")}
      ${tuile("Concentration secteur max", fmt(s.concentration_secteur_max_pct, 1), " %")}
    </div>
    <h2>Répartitions</h2>
    <div class="cartes">
      ${grapheBarres("Par type", s.repartition_types)}
      ${grapheBarres("Par secteur", s.repartition_secteurs)}
      ${grapheBarres("Par pays / zone", s.repartition_pays)}
    </div>
    <h2>Tops</h2>
    <div class="cartes">
      ${tableTop("Top opportunités (potentiel)", s.top_opportunites, " %")}
      ${tableTop("Top dividendes (rendement)", s.top_dividendes, " %")}
      ${tableTop("Top croissance", s.top_croissance, " %")}
    </div>
    <h2>Matrice de décision multicritère (${LIBELLES_ALGO[algo] ?? algo})</h2>
    <div class="carte"><div class="table-scroll"><table>
      <thead><tr><th>Rang</th><th>Valeur</th><th>Type</th>
        <th class="num">${algo === "topsis" ? "Proximité idéale" : "Score"}</th></tr></thead>
      <tbody>${classement.map((l) => `<tr>
        <td class="num">${l.rang}</td>
        <td><span class="pastille ${l.type}"></span>${echap(l.nom)}</td>
        <td>${l.type}</td>
        <td class="num">${fmt(l.valeur, 3)}</td></tr>`).join("")}
      </tbody></table></div>
      <p class="note-bas">${algo === "topsis"
        ? "Classement TOPSIS : proximité à la solution idéale (0 à 1), pondérations de config/scoring.yaml."
        : "Classement par score global pondéré (0 à 100)."}
        L'algorithme se choisit dans l'onglet Paramètres.</p>
    </div>`;
}

const volumeCourt = (v) => v == null ? "—"
  : v >= 1e6 ? `${(v / 1e6).toFixed(1)} M` : v >= 1e3 ? `${(v / 1e3).toFixed(0)} k` : String(v);

// État de tri et de masquage seed, persistant entre les rendus.
const triActifs = { cle: "score_global", sens: -1 };
let masquerSeed = false;

const txtCell = (s) => echap(s ?? "—");

// Catalogue complet des colonnes, aligné sur CHAMPS_FICHE du scraper (même ordre
// et mêmes clés) puis indicateurs calculés. Chaque entrée : libellé, tri, accès
// à la valeur (val) et rendu de cellule (cell).
const CATALOGUE_COLONNES = {
  rang: { label: "#", num: true, val: (a) => a._rang,
    cell: (a) => `<span class="muted">${a._rang ?? "—"}</span>` },
  nom: { label: "Nom", num: false, val: (a) => a.nom || "",
    cell: (a) => `<span class="pastille ${a.type}"></span>${echap(a.nom)}` },
  isin: { label: "ISIN", num: false, val: (a) => a.isin, cell: (a) => `<span class="muted">${a.isin}</span>` },
  secteur: { label: "Secteur", num: false, val: (a) => a.secteur || "", cell: (a) => txtCell(a.secteur) },
  cours: { label: "Cours", num: true, val: (a) => a.cours, cell: (a) => fmt(a.cours, 2) },
  devise: { label: "Devise", num: false, val: (a) => a.devise || "", cell: (a) => txtCell(a.devise) },
  date_cotation: { label: "Date", num: false, val: (a) => a.date_cotation || "", cell: (a) => txtCell(a.date_cotation) },
  heure_cotation: { label: "Heure", num: false, val: (a) => a.heure_cotation || "", cell: (a) => txtCell(a.heure_cotation) },
  variation_pct: { label: "Var. %", num: true, val: (a) => a.variation_pct,
    cell: (a) => `<span class="${a.variation_pct > 0 ? "hausse" : a.variation_pct < 0 ? "baisse" : ""}">${fmt(a.variation_pct, 2)}</span>` },
  ouverture: { label: "Ouv.", num: true, val: (a) => a.ouverture, cell: (a) => fmt(a.ouverture, 2) },
  plus_haut: { label: "+ Haut", num: true, val: (a) => a.plus_haut, cell: (a) => fmt(a.plus_haut, 2) },
  plus_bas: { label: "+ Bas", num: true, val: (a) => a.plus_bas, cell: (a) => fmt(a.plus_bas, 2) },
  cloture_veille: { label: "Clôt. veille", num: true, val: (a) => a.cloture_veille, cell: (a) => fmt(a.cloture_veille, 2) },
  haut_52s: { label: "52s + Haut", num: true, val: (a) => a.haut_52s, cell: (a) => fmt(a.haut_52s, 2) },
  bas_52s: { label: "52s + Bas", num: true, val: (a) => a.bas_52s, cell: (a) => fmt(a.bas_52s, 2) },
  volume: { label: "Volume", num: true, val: (a) => a.volume, cell: (a) => volumeCourt(a.volume) },
  quantite_echangee: { label: "Qté échangée", num: true, val: (a) => a.quantite_echangee, cell: (a) => volumeCourt(a.quantite_echangee) },
  capitalisation: { label: "Capi. (M€)", num: true, val: (a) => a.capitalisation, cell: (a) => fmt(a.capitalisation, 0) },
  nb_titres: { label: "Nb titres", num: true, val: (a) => a.nb_titres, cell: (a) => volumeCourt(a.nb_titres) },
  per: { label: "PER", num: true, val: (a) => a.per, cell: (a) => fmt(a.per, 1) },
  rendement: { label: "Rdt %", num: true, val: (a) => a.rendement, cell: (a) => fmt(a.rendement, 1) },
  bna: { label: "BNA", num: true, val: (a) => a.bna, cell: (a) => fmt(a.bna, 2) },
  dividende: { label: "Div.", num: true, val: (a) => a.dividende, cell: (a) => fmt(a.dividende, 2) },
  taux_distribution: { label: "Taux distrib. %", num: true, val: (a) => a.taux_distribution, cell: (a) => fmt(a.taux_distribution, 1) },
  dette_nette: { label: "Dette nette (M€)", num: true, val: (a) => a.dette_nette, cell: (a) => fmt(a.dette_nette, 0) },
  ca: { label: "CA (M€)", num: true, val: (a) => a.ca, cell: (a) => fmt(a.ca, 0) },
  objectif_cours: { label: "Objectif", num: true, val: (a) => a.objectif_cours, cell: (a) => fmt(a.objectif_cours, 2) },
  potentiel: { label: "Potentiel %", num: true, val: (a) => a.potentiel,
    cell: (a) => `<span class="${a.potentiel > 0 ? "hausse" : a.potentiel < 0 ? "baisse" : ""}">${fmt(a.potentiel, 1)}</span>` },
  consensus: { label: "Consensus", num: true, val: (a) => a.consensus, cell: (a) => fmt(a.consensus, 2) },
  nb_analystes: { label: "Analystes", num: true, val: (a) => a.nb_analystes, cell: (a) => fmt(a.nb_analystes, 0) },
  score_esg: { label: "ESG", num: true, val: (a) => a.score_esg, cell: (a) => fmt(a.score_esg, 0) },
  risque_esg: { label: "Risque ESG", num: true, val: (a) => a.risque_esg, cell: (a) => fmt(a.risque_esg, 1) },
  eligible_pea: { label: "PEA", num: false, val: (a) => (a.eligible_pea ? 1 : 0),
    cell: (a) => (a.eligible_pea ? '<span class="hausse">✓</span>' : '<span class="baisse">✗</span>') },
  // Indicateurs calculés (hors CHAMPS_FICHE).
  niveau_risque: { label: "Risque", num: true, val: (a) => a.niveau_risque, cell: (a) => `${a.niveau_risque ?? "—"}/7` },
  volatilite: { label: "Vol. %", num: true, val: (a) => a.indicateurs_quant?.volatilite_pct ?? a.volatilite,
    cell: (a) => fmt(a.indicateurs_quant?.volatilite_pct ?? a.volatilite, 1) },
  sharpe: { label: "Sharpe", num: true, val: (a) => a.indicateurs_quant?.sharpe, cell: (a) => fmt(a.indicateurs_quant?.sharpe, 2) },
  score_global: { label: "Score", num: true, val: (a) => a.score_global,
    cell: (a) => `<span class="score-badge">${fmt(a.score_global, 0)}</span>` },
  source: { label: "Source", num: false, val: (a) => a.source || "",
    cell: (a) => {
      if (!a.source) return "—";
      // Lien = URL d'acquisition si connue, sinon recherche par ISIN sur la source.
      const href = a.source_url || lienFiche(a.source, a.isin);
      return `<a href="${echap(href)}" target="_blank" rel="noopener" class="lien-source" title="Lien d'acquisition (${echap(a.isin)}) sur ${echap(a.source)}">${echap(a.source)}</a>`;
    } },
};

// Ordre exact de CHAMPS_FICHE (scraper Boursorama) + préfixes → clés du catalogue.
const CHAMPS_FICHE_CLES = [
  "nom", "isin", "secteur", "cours", "devise", "date_cotation", "heure_cotation",
  "variation_pct", "ouverture", "plus_haut", "plus_bas", "cloture_veille",
  "haut_52s", "bas_52s", "volume", "quantite_echangee", "capitalisation",
  "nb_titres", "per", "rendement", "bna", "dividende", "taux_distribution",
  "dette_nette", "ca", "objectif_cours", "potentiel", "consensus", "nb_analystes",
  "score_esg", "risque_esg", "eligible_pea", "source",
];
// Toutes les clés proposables dans les Paramètres (CHAMPS_FICHE + calculées).
const ORDRE_COLONNES = [...CHAMPS_FICHE_CLES.slice(0, -1),
  "niveau_risque", "volatilite", "sharpe", "score_global", "source"];

// Jeu de colonnes par défaut de chaque onglet (« ses propres entêtes »).
// Actions : aligné sur CHAMPS_FICHE, avec le score global inséré avant la source.
const COLONNES_DEFAUT = {
  ACTION: [...CHAMPS_FICHE_CLES.slice(0, -1), "score_global", "source"],
  ETF: ["nom", "isin", "secteur", "cours", "variation_pct", "rendement", "volume",
        "score_esg", "niveau_risque", "score_global", "source"],
  OPCVM: ["nom", "isin", "secteur", "cours", "variation_pct", "rendement",
          "score_esg", "niveau_risque", "score_global", "source"],
};

function colonnesVisibles(type, profil) {
  const perso = profil["colonnes_" + type.toLowerCase()];
  const cles = (perso && perso.length ? perso : COLONNES_DEFAUT[type])
    .filter((c) => CATALOGUE_COLONNES[c]);
  return cles.map((c) => ({ cle: c, ...CATALOGUE_COLONNES[c] }));
}

function trierActifs(liste) {
  const col = CATALOGUE_COLONNES[triActifs.cle] || CATALOGUE_COLONNES.nom;
  return [...liste].sort((a, b) => {
    const x = col.val(a), y = col.val(b);
    const vide = (v) => v == null || v === "";
    if (vide(x) && vide(y)) return 0;
    if (vide(x)) return 1;        // valeurs manquantes toujours en bas
    if (vide(y)) return -1;
    const cmp = col.num ? (x - y) : String(x).localeCompare(String(y), "fr");
    return cmp * triActifs.sens;
  });
}

const COULEUR_ONGLET = { ACTION: "couleur_actions", ETF: "couleur_etf", OPCVM: "couleur_opcvm" };

async function vueActifs(type, titre) {
  const [actifs, sources, sourcesGlobales, profil] = await Promise.all([
    api(`/api/actifs?type=${type}`),
    api("/api/recherche/sources"),
    api("/api/sources"),
    api("/api/parametres/profil"),
  ]);
  const aDuSeed = actifs.some((a) => a.source === "seed");
  const entete = profil[COULEUR_ONGLET[type]] || "var(--serie-1)";
  // Rang dans l'ordre d'acquisition (id croissant), figé quel que soit le tri.
  [...actifs].sort((a, b) => a.id - b.id).forEach((a, i) => { a._rang = i + 1; });
  // Colonne « # » (rang) toujours en tête, puis les colonnes visibles de l'onglet.
  const colonnes = [{ cle: "rang", ...CATALOGUE_COLONNES.rang }, ...colonnesVisibles(type, profil)];
  // Le tri courant doit porter sur une colonne visible.
  if (!colonnes.some((c) => c.cle === triActifs.cle)) {
    triActifs.cle = colonnes.some((c) => c.cle === "score_global") ? "score_global" : colonnes[0].cle;
  }
  // Colonnes figées au défilement horizontal : rang, Nom, ISIN, Secteur en tête.
  const CLES_FIXES = ["rang", "nom", "isin", "secteur"];
  let nbFixes = 0;
  while (nbFixes < colonnes.length && CLES_FIXES.includes(colonnes[nbFixes].cle)) nbFixes++;

  // Sources d'import global (onglet Sources) hors scrapers déjà présents et hors seed.
  const nomsScrapers = new Set(sources.map((s) => s.nom));
  const sourcesImport = sourcesGlobales.sources.filter(
    (s) => s.nom !== "seed" && !nomsScrapers.has(s.nom));

  // Réactualisation : délai minimal paramétrable (bleu = disponible, gris = en attente).
  const minutesCd = Number(profil.reactualisation_minutes) || 0;
  const derniereReactu = Number(localStorage.getItem("peadvisor-reactu-" + type) || 0);
  const restantMs = Math.max(0, derniereReactu + minutesCd * 60000 - Date.now());

  // Barre de recherche : service partagé, présent sur les trois onglets de valeurs.
  const barreRecherche = `
    <form class="panneau" id="form-scrap">
      <label class="champ" style="display:block;margin-bottom:8px">Rechercher et ajouter une valeur (nom, ISIN ou code) — la source détecte le type et vérifie l'éligibilité PEA :
        <input type="text" id="scrap-requete" placeholder="ex. Air Liquide, FR0000120073 ou 1rPAI" style="width:340px"></label>
      <div class="champs" id="boutons-recherche">
        ${sources.map((s) => `<button type="button" class="btn-source" data-source="${s.nom}"
          data-cat="recherche" title="Recherche par valeur — ${s.valide ? "source validée" : "parseur à fiabiliser"}">
          ${echap(s.libelle)}${s.valide ? "" : " *"}</button>`).join("")}
      </div>
      <div class="champs" id="boutons-import" style="margin-top:8px">
        <span class="libelle-reglage" style="min-width:auto">Import global :</span>
        ${sourcesImport.map((s) => `<button type="button" class="btn-source" data-source="${s.nom}"
          data-cat="import" title="Import global depuis ${echap(s.nom)}">${echap(s.nom)}</button>`).join("")}
        <button type="button" id="btn-diagnostic" class="secondaire"
          title="Tester chaque source et colorer les boutons">🩺 Diagnostiquer les sources</button>
      </div>
      <div class="champs" style="margin-top:8px">
        <button type="button" id="btn-reactualiser" class="${restantMs ? "secondaire" : ""}"
          ${restantMs ? "disabled" : ""} data-restant="${restantMs}"
          title="Re-scraper et mettre à jour toutes les valeurs de ce tableau">↻ Réactualiser le tableau</button>
      </div>
      <p class="note-bas" id="retour-scrap">Boutons <b>bleus</b> : données disponibles · <b>orange</b> : test OK mais aucune donnée · <b>gris</b> : indisponible (lancer « Diagnostiquer »). « * » : parseur à fiabiliser. « ↻ Réactualiser » met à jour toutes les lignes (délai mini ${minutesCd} min, réglable dans Paramètres).</p>
    </form>`;

  const toggleSeed = aDuSeed ? `<button class="secondaire" id="toggle-seed">${
    masquerSeed ? "Afficher les données de démonstration" : "Masquer les données de démonstration (seed)"}</button>` : "";

  contenu.innerHTML = `
    <h1>${titre}</h1>
    <p class="sous-titre">${actifs.length} valeur(s). Cliquer sur un en-tête pour trier ; 🗑 pour retirer une ligne. ${toggleSeed}</p>
    ${barreRecherche}
    <div class="carte"><div class="table-scroll defilable"><table class="valeurs" style="--entete:${entete}">
      <thead><tr>${colonnes.map((c, i) => `<th class="triable ${c.num ? "num" : ""} ${i < nbFixes ? "col-fixe" : ""}"
        data-cle="${c.cle}">${c.label}${triActifs.cle === c.cle ? (triActifs.sens < 0 ? " ▾" : " ▴") : ""}</th>`).join("")}
        <th class="col-actions"></th></tr></thead>
      <tbody id="corps-actifs"></tbody></table></div></div>`;

  function dessinerLignes() {
    const liste = masquerSeed ? actifs.filter((a) => a.source !== "seed") : actifs;
    document.getElementById("corps-actifs").innerHTML = trierActifs(liste).map((a) => `<tr>
      ${colonnes.map((c, i) => `<td class="${c.num ? "num" : ""} ${i < nbFixes ? "col-fixe" : ""}">${c.cell(a)}</td>`).join("")}
      <td style="white-space:nowrap">
        <button class="secondaire" data-watch="${a.isin}" title="Ajouter à la watchlist">☆</button>
        <button class="btn-suppr" data-suppr="${a.isin}" data-nom="${echap(a.nom)}" title="Retirer du référentiel">🗑</button>
      </td></tr>`).join("");
    document.querySelectorAll("[data-watch]").forEach((b) =>
      b.addEventListener("click", async () => {
        await api(`/api/watchlist/${b.dataset.watch}`, { method: "POST" });
        b.textContent = "★";
      }));
    document.querySelectorAll("[data-suppr]").forEach((b) =>
      b.addEventListener("click", async () => {
        if (!confirm(`Retirer ${b.dataset.nom} (${b.dataset.suppr}) du référentiel ?`)) return;
        await api(`/api/actifs/${b.dataset.suppr}`, { method: "DELETE" });
        vueActifs(type, titre);
      }));
    figerColonnes(nbFixes);
  }
  dessinerLignes();

  document.querySelectorAll("th.triable").forEach((th) =>
    th.addEventListener("click", () => {
      const cle = th.dataset.cle;
      if (triActifs.cle === cle) triActifs.sens *= -1;
      else { triActifs.cle = cle; triActifs.sens = CATALOGUE_COLONNES[cle].num ? -1 : 1; }
      vueActifs(type, titre);
    }));

  if (aDuSeed) {
    document.getElementById("toggle-seed").addEventListener("click", () => {
      masquerSeed = !masquerSeed;
      vueActifs(type, titre);
    });
  }

  // Recherche/ajout : gère l'éligibilité PEA (confirmation via modale) et les
  // erreurs (modale décrivant la cause).
  async function lancerRecherche(source, libelle, requete, retour, confirmer) {
    retour.textContent = `Recherche sur ${libelle}…`;
    const url = `/api/recherche/${source}/${encodeURIComponent(requete)}`
      + (confirmer ? "?confirmer=true" : "");
    try {
      const r = await api(url, { method: "POST" });
      if (r.confirmation_requise) {
        ouvrirModal("Ajout à confirmer", `
          <p class="baisse">⚠ ${echap(r.raison)}</p>
          <p>${echap(r.nom)} (${echap(r.isin)}) — type ${echap(r.type)},
             cours ${fmt(r.cours, 2)}, onglet ${echap(r.onglet)}.</p>`, [
          { libelle: "Ajouter quand même",
            onClick: () => lancerRecherche(source, libelle, requete, retour, true) },
          { libelle: "Annuler", secondaire: true },
        ]);
        retour.textContent = "Ajout en attente de confirmation.";
        return;
      }
      const d = r.donnees_extraites || {};
      const extra = [
        d.objectif_cours != null ? `objectif ${fmt(d.objectif_cours, 2)}` : null,
        d.potentiel != null ? `potentiel ${fmt(d.potentiel, 1)} %` : null,
        d.risque_esg != null ? `risque ESG ${fmt(d.risque_esg, 1)}` : null,
      ].filter(Boolean).join(" · ");
      const alerte = r.eligible_pea === false
        ? `<br><span class="baisse">⚠ ${echap(r.avertissement || "Éligibilité PEA non confirmée")}</span>` : "";
      const autreOnglet = r.type !== type
        ? `<br><span class="hausse">Type ${r.type} → classé dans l'onglet ${echap(r.onglet)}.</span> `
          + `<a href="#${r.onglet}">y aller</a>` : "";
      retour.innerHTML = `<span class="hausse">${r.cree ? "Ajouté" : "Mis à jour"}</span> : `
        + `${echap(r.nom)} (${r.isin}) — ${r.type}, cours ${fmt(r.cours, 2)}, source ${echap(r.source)}`
        + (extra ? `<br><span class="muted">${echap(extra)}</span>` : "") + alerte + autreOnglet;
      if (r.type === type) setTimeout(() => vueActifs(type, titre), 1400);
    } catch (err) {
      ouvrirModal("Erreur lors de la recherche", `
        <p>La recherche « ${echap(requete)} » sur ${echap(libelle)} a échoué :</p>
        <p class="baisse">${echap(err.message)}</p>`, [{ libelle: "Fermer", secondaire: true }]);
      retour.innerHTML = `<span class="baisse">Échec (${echap(libelle)})</span> — ${echap(err.message)}`;
    }
  }

  // Import global depuis une source (Yahoo, AlphaVantage, Stooq…).
  async function lancerImport(source, retour) {
    retour.textContent = `Import global depuis ${source}…`;
    try {
      const r = await api(`/api/import?source=${encodeURIComponent(source)}`, { method: "POST" });
      retour.innerHTML = `<span class="hausse">Import ${echap(source)}</span> — `
        + `${r.nb_crees ?? 0} créé(s), ${r.nb_maj ?? 0} mis à jour`
        + (r.nb_erreurs ? `, <span class="baisse">${r.nb_erreurs} erreur(s)</span>` : "")
        + (r.detail ? `<br><span class="muted">${echap(r.detail)}</span>` : "");
      setTimeout(() => vueActifs(type, titre), 1400);
    } catch (err) {
      ouvrirModal(`Import ${source} impossible`, `<p class="baisse">${echap(err.message)}</p>`,
        [{ libelle: "Fermer", secondaire: true }]);
      retour.innerHTML = `<span class="baisse">Échec import ${echap(source)}</span> — ${echap(err.message)}`;
    }
  }

  document.querySelectorAll("#form-scrap .btn-source").forEach((bouton) =>
    bouton.addEventListener("click", () => {
      const retour = document.getElementById("retour-scrap");
      if (bouton.dataset.cat === "import") { lancerImport(bouton.dataset.source, retour); return; }
      const requete = document.getElementById("scrap-requete").value.trim();
      if (!requete) { retour.textContent = "Saisir un nom, un ISIN ou un code."; return; }
      lancerRecherche(bouton.dataset.source, bouton.textContent.trim(), requete, retour, false);
    }));

  // Diagnostic : teste chaque source et colore les boutons (bleu/orange/gris).
  document.getElementById("btn-diagnostic").addEventListener("click", async (e) => {
    const retour = document.getElementById("retour-scrap");
    e.target.disabled = true;
    retour.textContent = "Diagnostic des sources en cours (interrogation réelle)…";
    try {
      const etats = await api("/api/sources/etats");
      etatsSourcesCache = { ts: Date.now(), parNom: {} };
      etats.forEach((s) => { etatsSourcesCache.parNom[s.nom] = s.etat; });
      appliquerEtatsSources();
      const n = (etat) => etats.filter((s) => s.etat === etat).length;
      retour.innerHTML = `<span class="hausse">Diagnostic terminé</span> — `
        + `${n("disponible")} disponible(s), ${n("vide")} vide(s), ${n("indisponible")} indisponible(s).`;
    } catch (err) {
      retour.innerHTML = `<span class="baisse">Diagnostic impossible</span> — ${echap(err.message)}`;
    }
    e.target.disabled = false;
  });

  // Réactualisation : re-scrape toutes les valeurs + rapport technique à valider.
  const btnReactu = document.getElementById("btn-reactualiser");
  if (restantMs > 0) {
    // Ré-affiche l'onglet à la fin du délai pour réactiver le bouton (bleu).
    setTimeout(() => { if (location.hash.slice(1) === type.toLowerCase()) vueActifs(type, titre); },
      restantMs + 200);
  }
  btnReactu.addEventListener("click", async (e) => {
    const retour = document.getElementById("retour-scrap");
    e.target.disabled = true;
    e.target.classList.add("secondaire");
    retour.textContent = "Réactualisation de toutes les valeurs en cours…";
    try {
      const r = await api(`/api/actifs/reactualiser?type=${type}`, { method: "POST" });
      localStorage.setItem("peadvisor-reactu-" + type, Date.now());
      retour.innerHTML = `<span class="hausse">Réactualisé</span> — ${r.actifs_maj} valeur(s) mise(s) à jour`
        + (r.echecs ? `, <span class="baisse">${r.echecs} échec(s)</span>` : "")
        + `, scores recalculés (${r.actifs_recalcules}).`;
      // Rapport de fin : suggestions techniques, à valider.
      const listeSug = (r.suggestions || []).map((x) => `<li>${echap(x)}</li>`).join("");
      const listeDet = (r.echecs && r.details?.length)
        ? `<p class="muted">Détails :</p><ul>${r.details.map((x) => `<li>${echap(x)}</li>`).join("")}</ul>` : "";
      ouvrirModal("Rapport de réactualisation", `
        <p>${r.actifs_maj} valeur(s) mise(s) à jour, ${r.echecs} échec(s).</p>
        <p><b>Suggestions techniques :</b></p><ul>${listeSug}</ul>${listeDet}`,
        [{ libelle: "Valider", onClick: () => vueActifs(type, titre) }]);
    } catch (err) {
      ouvrirModal("Erreur de réactualisation", `<p class="baisse">${echap(err.message)}</p>`,
        [{ libelle: "Fermer", secondaire: true }]);
      retour.innerHTML = `<span class="baisse">Échec</span> — ${echap(err.message)}`;
      e.target.disabled = false;
      e.target.classList.remove("secondaire");
    }
  });

  appliquerEtatsSources();   // recolore selon le dernier diagnostic (cache session)
}

async function vueAllocation() {
  const profil = await api("/api/parametres/profil");
  const choix = (v) => (profil.objectif === v ? "selected" : "");
  contenu.innerHTML = `
    <h1>Allocation automatique</h1>
    <p class="sous-titre">Proposition indicative — pré-remplie avec votre profil investisseur
      (modifiable dans Paramètres).</p>
    <form class="panneau" id="form-allocation">
      <div class="champs">
        <label class="champ">Capital (€)
          <input type="number" name="capital" value="10000" min="100" step="100" required></label>
        <label class="champ">Niveau de risque (1-7)
          <input type="number" name="niveau_risque" value="${profil.niveau_risque}" min="1" max="7" required></label>
        <label class="champ">Horizon (années)
          <input type="number" name="horizon_annees" value="${profil.horizon_annees}" min="1" max="40" required></label>
        <label class="champ">Objectif
          <select name="objectif">
            <option value="equilibre" ${choix("equilibre")}>Équilibré</option>
            <option value="croissance" ${choix("croissance")}>Capitalisation (croissance)</option>
            <option value="dividendes" ${choix("dividendes")}>Revenus (dividendes)</option>
          </select></label>
        <button type="submit">Proposer une allocation</button>
      </div>
    </form>
    <div id="resultat-allocation"></div>`;
  document.getElementById("form-allocation").addEventListener("submit", async (e) => {
    e.preventDefault();
    const d = Object.fromEntries(new FormData(e.target));
    const corps = {
      capital: Number(d.capital),
      niveau_risque: Number(d.niveau_risque),
      horizon_annees: Number(d.horizon_annees),
      objectif: d.objectif,
    };
    const r = await api("/api/allocation", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(corps),
    });
    const repartition = Object.fromEntries(
      Object.entries(r.repartition_types).map(([t, p]) => [t, Math.round(p * 100)]));
    const criteres = (r.criteres || []).length
      ? `<div class="carte"><h3>Critères de sélection</h3>
         <ul>${r.criteres.map((c) => `<li>${echap(c)}</li>`).join("")}</ul></div>` : "";
    const incompletes = (r.valeurs_incompletes || []).length
      ? `<h2>Valeurs éligibles écartées — informations manquantes (${r.valeurs_incompletes.length})</h2>
         <div class="carte"><div class="table-scroll"><table>
           <thead><tr><th>Valeur</th><th>Type</th><th>Informations manquantes</th></tr></thead>
           <tbody>${r.valeurs_incompletes.map((v) => `<tr>
             <td><span class="pastille ${v.type}"></span>${echap(v.nom)} <span class="muted">${echap(v.isin)}</span></td>
             <td>${echap(v.type)}</td>
             <td class="baisse">${echap(v.informations_manquantes.join(" · "))}</td></tr>`).join("")}
           </tbody></table></div>
           <p class="note-bas">Ces valeurs sont exclues de l'allocation tant que leurs données clés
             (cours, score…) ne sont pas renseignées — réactualiser ou changer de source.</p></div>` : "";
    document.getElementById("resultat-allocation").innerHTML = `
      <div class="cartes">${grapheBarres("Répartition par type (%)", repartition)}</div>
      ${criteres}
      <h2>${r.lignes.length} lignes proposées</h2>
      <div class="carte"><div class="table-scroll"><table>
        <thead><tr><th>Valeur</th><th>Secteur</th><th class="num">Poids</th>
          <th class="num">Montant</th><th class="num">Score</th><th>Justification</th></tr></thead>
        <tbody>${r.lignes.map((l) => `<tr>
          <td><span class="pastille ${l.type}"></span>${echap(l.nom)}${
            l.informations_manquantes?.length ? ' <span class="baisse" title="Informations manquantes">⚠</span>' : ""}</td>
          <td>${echap(l.secteur ?? "—")}</td>
          <td class="num">${(l.poids * 100).toFixed(1)} %</td>
          <td class="num">${euros(l.montant)}</td>
          <td class="num score-badge">${fmt(l.score_global, 0)}</td>
          <td class="muted">${echap(l.justification)}</td></tr>`).join("")}
        </tbody></table></div>
        <p class="note-bas">${echap(r.commentaire)}</p></div>
      ${incompletes}`;
  });
}

function grapheTrajectoire(scenarios) {
  // Courbe SVG des trois scénarios + versements cumulés, en valeur nette-ish (brute).
  const annees = scenarios.median.trajectoire.map((p) => p.annee);
  const series = [
    { cle: "optimiste", couleur: "var(--serie-2)", pts: scenarios.optimiste.trajectoire },
    { cle: "médian", couleur: "var(--serie-1)", pts: scenarios.median.trajectoire },
    { cle: "prudent", couleur: "var(--serie-3)", pts: scenarios.prudent.trajectoire },
  ];
  const maxV = Math.max(...scenarios.optimiste.trajectoire.map((p) => p.valeur), 1);
  const maxA = Math.max(...annees, 1);
  const L = 640, H = 240, mg = 44;
  const x = (a) => mg + (a / maxA) * (L - mg - 10);
  const y = (v) => H - 24 - (v / maxV) * (H - 44);
  const ligne = (pts, key) => pts.map((p, i) =>
    `${i ? "L" : "M"}${x(p.annee).toFixed(1)},${y(p[key]).toFixed(1)}`).join(" ");
  const versements = scenarios.median.trajectoire;
  return `<svg viewBox="0 0 ${L} ${H}" width="100%" role="img" aria-label="Trajectoire des scénarios">
    <line x1="${mg}" y1="${H - 24}" x2="${L - 10}" y2="${H - 24}" stroke="var(--baseline)"/>
    <line x1="${mg}" y1="20" x2="${mg}" y2="${H - 24}" stroke="var(--baseline)"/>
    <path d="${ligne(versements, "versements_cumules")}" fill="none"
      stroke="var(--muted)" stroke-width="1.5" stroke-dasharray="4 3"/>
    ${series.map((s) => `<path d="${ligne(s.pts, "valeur")}" fill="none"
      stroke="${s.couleur}" stroke-width="2"/>`).join("")}
    <text x="${mg}" y="14" fill="var(--muted)" font-size="11">Valeur (€)</text>
    <text x="${L - 10}" y="${H - 8}" fill="var(--muted)" font-size="11" text-anchor="end">Années</text>
  </svg>`;
}

async function vueSimulateur() {
  const profil = await api("/api/parametres/profil");
  contenu.innerHTML = `
    <h1>Simulateur d'investissement</h1>
    <p class="sous-titre">Projection PEA : versements, dividendes, 3 scénarios et fiscalité estimée.
      Estimation indicative — pas un conseil en investissement ni fiscal.</p>
    <form class="panneau" id="form-simulation">
      <div class="champs">
        <label class="champ">Capital initial (€)
          <input type="number" name="capital_initial" value="10000" min="0" step="500"></label>
        <label class="champ">Versement mensuel (€)
          <input type="number" name="versement_mensuel" value="200" min="0" step="50"></label>
        <label class="champ">Horizon (années)
          <input type="number" name="horizon_annees" value="${profil.horizon_annees}" min="1" max="40"></label>
        <label class="champ">Croissance annuelle du cours (%)
          <input type="number" name="rendement_prix_pct" value="5" min="-20" max="30" step="0.5"></label>
        <label class="champ">Rendement du dividende (%)
          <input type="number" name="rendement_dividende_pct" value="2.5" min="0" max="15" step="0.1"></label>
        <label class="champ">Volatilité (%)
          <input type="number" name="volatilite_pct" value="15" min="0" max="80" step="1"></label>
        <label class="champ">Dividendes
          <select name="reinvestir_dividendes">
            <option value="true">Réinvestis</option>
            <option value="false">Versés (non réinvestis)</option>
          </select></label>
        <button type="submit">Simuler</button>
      </div>
    </form>
    <div id="resultat-simulation"></div>`;
  document.getElementById("form-simulation").addEventListener("submit", async (e) => {
    e.preventDefault();
    const d = Object.fromEntries(new FormData(e.target));
    const corps = {
      capital_initial: Number(d.capital_initial),
      versement_mensuel: Number(d.versement_mensuel),
      horizon_annees: Number(d.horizon_annees),
      rendement_prix_pct: Number(d.rendement_prix_pct),
      rendement_dividende_pct: Number(d.rendement_dividende_pct),
      volatilite_pct: Number(d.volatilite_pct),
      reinvestir_dividendes: d.reinvestir_dividendes === "true",
    };
    let r;
    try {
      r = await api("/api/simulation", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(corps),
      });
    } catch (err) {
      document.getElementById("resultat-simulation").innerHTML =
        `<p class="baisse">${echap(err.message)}</p>`;
      return;
    }
    const ordre = [["prudent", "Prudent"], ["median", "Médian"], ["optimiste", "Optimiste"]];
    const carteScenario = ([cle, titre]) => {
      const s = r.scenarios[cle];
      return `<div class="tuile">
        <div class="libelle">${titre} — ${fmt(s.rendement_annuel_pct, 1)} %/an</div>
        <div class="valeur">${euros(s.valeur_finale_nette)}<span class="unite"> net</span></div>
        <div class="muted" style="font-size:12px;margin-top:4px">
          Brut ${euros(s.valeur_finale_brute)} · plus-value ${euros(s.plus_value_brute)}<br>
          Impôt estimé ${euros(s.impot_estime)}</div>
      </div>`;
    };
    document.getElementById("resultat-simulation").innerHTML = `
      <div class="tuiles">${ordre.map(carteScenario).join("")}</div>
      <h2>Trajectoire</h2>
      <div class="carte">${grapheTrajectoire(r.scenarios)}
        <p class="note-bas">Traits pleins : scénarios (vert optimiste, bleu médian, rose prudent).
          Pointillé gris : total des versements. ${echap(r.commentaire)}</p></div>
      <h2>Détail (scénario médian)</h2>
      <div class="carte"><div class="table-scroll"><table>
        <thead><tr><th class="num">Année</th><th class="num">Versements cumulés</th>
          <th class="num">Valeur projetée</th><th class="num">Plus-value</th></tr></thead>
        <tbody>${r.scenarios.median.trajectoire.filter((p, i, a) =>
          p.annee % Math.ceil(a.length / 12) === 0 || i === a.length - 1).map((p) => `<tr>
          <td class="num">${p.annee}</td>
          <td class="num">${euros(p.versements_cumules)}</td>
          <td class="num">${euros(p.valeur)}</td>
          <td class="num ${p.valeur >= p.versements_cumules ? "hausse" : "baisse"}">
            ${euros(p.valeur - p.versements_cumules)}</td></tr>`).join("")}
        </tbody></table></div>
        <p class="note-bas">Fiscalité : ${echap(r.scenarios.median.regime_fiscal)}.
          Paramètres dans <code>config/settings.yaml</code> (section fiscalite_pea).</p></div>`;
  });
}

async function vueWatchlist() {
  const elements = await api("/api/watchlist");
  contenu.innerHTML = `
    <h1>Watchlist</h1>
    <p class="sous-titre">${elements.length} valeur(s) suivie(s). Ajout via l'étoile dans les listes d'actifs.</p>
    <div class="carte"><div class="table-scroll"><table>
      <thead><tr><th>Valeur</th><th>ISIN</th><th class="num">Cours</th>
        <th class="num">Potentiel %</th><th class="num">Score</th><th></th></tr></thead>
      <tbody>${elements.map((e) => `<tr>
        <td><span class="pastille ${e.actif.type}"></span>${echap(e.actif.nom)}</td>
        <td class="muted">${e.actif.isin}</td>
        <td class="num">${fmt(e.actif.cours, 2)}</td>
        <td class="num">${fmt(e.actif.potentiel, 1)}</td>
        <td class="num score-badge">${fmt(e.actif.score_global, 0)}</td>
        <td><button class="secondaire" data-retirer="${e.actif.isin}">Retirer</button></td>
      </tr>`).join("") || `<tr><td colspan="6" class="muted">Watchlist vide.</td></tr>`}
      </tbody></table></div></div>`;
  contenu.querySelectorAll("[data-retirer]").forEach((b) =>
    b.addEventListener("click", async () => {
      await api(`/api/watchlist/${b.dataset.retirer}`, { method: "DELETE" });
      vueWatchlist();
    }));
}

async function vueHistorique() {
  const journal = await api("/api/journal");
  contenu.innerHTML = `
    <h1>Historique des mises à jour</h1>
    <div class="panneau">
      <button id="btn-import">Lancer une mise à jour maintenant</button>
      <button id="btn-scores" class="secondaire">Recalculer les scores</button>
    </div>
    <div class="carte"><div class="table-scroll"><table>
      <thead><tr><th>Date (UTC)</th><th>Traitement</th><th>Statut</th>
        <th class="num">Créés</th><th class="num">Mis à jour</th>
        <th class="num">Doublons</th><th class="num">Rejets</th><th>Détail</th></tr></thead>
      <tbody>${journal.map((j) => `<tr>
        <td class="muted">${j.date.replace("T", " ").slice(0, 16)}</td>
        <td>${echap(j.traitement)}</td>
        <td class="${j.statut === "succes" ? "hausse" : "baisse"}">${j.statut}</td>
        <td class="num">${j.nb_crees}</td><td class="num">${j.nb_maj}</td>
        <td class="num">${j.nb_doublons}</td><td class="num">${j.nb_erreurs}</td>
        <td class="muted">${echap(j.detail ?? "")}</td></tr>`).join("")
        || `<tr><td colspan="8" class="muted">Aucun traitement journalisé.</td></tr>`}
      </tbody></table></div></div>`;
  document.getElementById("btn-import").addEventListener("click", async (e) => {
    e.target.disabled = true;
    await api("/api/import", { method: "POST" });
    vueHistorique();
  });
  document.getElementById("btn-scores").addEventListener("click", async () => {
    await api("/api/scores/recalculer", { method: "POST" });
    vueHistorique();
  });
}

async function vueSources() {
  const s = await api("/api/sources");
  contenu.innerHTML = `
    <h1>Sources de données</h1>
    <p class="sous-titre">Source active : <strong>${echap(s.source_active)}</strong>
      (se change dans <code>config/settings.yaml</code>, clé <code>donnees.source_active</code>)</p>
    <div class="carte"><div class="table-scroll"><table>
      <thead><tr><th>Source</th><th>Clé API</th><th>État de la clé</th><th></th><th>Résultat du test</th></tr></thead>
      <tbody>${s.sources.map((src) => `<tr>
        <td>${src.nom === s.source_active ? "▶ " : ""}<strong>${echap(src.nom)}</strong></td>
        <td>${src.necessite_cle ? `requise (<code>${echap(src.variable_env ?? "")}</code>)` : "aucune"}</td>
        <td>${src.necessite_cle
          ? (src.cle_configuree ? '<span class="hausse">configurée ✓</span>'
                                : '<span class="baisse">absente ✗</span>')
          : "—"}</td>
        <td>${src.testable ? `<button class="secondaire" data-tester="${src.nom}">Tester</button>`
             : (src.nom === "seed" ? `<button class="secondaire" data-charger="seed">Charger</button>` : "")}</td>
        <td class="muted" id="test-${src.nom}"></td>
      </tr>`).join("")}</tbody></table></div>
      <p class="note-bas">Clés API : copier <code>config/cles_api.exemple.yaml</code> vers
      <code>config/cles_api.yaml</code> (jamais versionné) ou définir les variables
      d'environnement, qui priment. Le test récupère la page exemple de la source
      (URL paramétrable dans l'onglet Paramètres) et en affiche un extrait JSON ;
      à défaut d'URL, il interroge un titre via l'API. En cas d'échec, la cause
      est affichée en texte. Détails et comparatif des sources :
      <code>docs/09-sources-donnees.md</code>.</p>
    </div>`;
  contenu.querySelectorAll("[data-tester]").forEach((b) =>
    b.addEventListener("click", async () => {
      const cible = document.getElementById(`test-${b.dataset.tester}`);
      cible.textContent = "test en cours…";
      b.disabled = true;
      try {
        const r = await api(`/api/sources/${b.dataset.tester}/tester`, { method: "POST" });
        const lienPage = r.url ? ` (<a href="${echap(r.url)}" target="_blank" rel="noopener">page</a>)` : "";
        if (r.exemple_json !== undefined) {
          // Succès : extrait JSON de la page exemple référencée dans les Paramètres.
          cible.innerHTML = `<span class="hausse">OK</span> — exemple JSON${lienPage} :`
            + `<pre style="white-space:pre-wrap;font-size:11px;margin:4px 0">${echap(JSON.stringify(r.exemple_json, null, 2))}</pre>`;
        } else if (r.exemple_texte !== undefined) {
          // Succès mais réponse non-JSON (HTML/CSV) : extrait texte.
          cible.innerHTML = `<span class="hausse">OK</span> — extrait texte${lienPage} :`
            + `<pre style="white-space:pre-wrap;font-size:11px;margin:4px 0">${echap(r.exemple_texte)}</pre>`;
        } else if (r.ok) {
          cible.innerHTML = `<span class="hausse">OK</span> — ${r.points_historique ?? 0} point(s) d'historique`
            + (r.cotation?.cours ? `, cours ${r.cotation.cours}` : "");
        } else {
          // Échec : cause affichée en texte.
          cible.innerHTML = `<span class="baisse">Échec</span>${lienPage} — ${echap(r.erreur ?? r.info ?? "")}`;
        }
      } catch (err) {
        cible.innerHTML = `<span class="baisse">Erreur</span> — ${echap(err.message)}`;
      }
      b.disabled = false;
    }));
  // Bouton « Charger » de la ligne seed : verse le jeu de démonstration en base.
  contenu.querySelectorAll("[data-charger]").forEach((b) =>
    b.addEventListener("click", async () => {
      const cible = document.getElementById(`test-${b.dataset.charger}`);
      cible.textContent = "chargement…";
      b.disabled = true;
      try {
        const r = await api(`/api/import?source=${b.dataset.charger}`, { method: "POST" });
        cible.innerHTML = `<span class="hausse">Chargé</span> — ${echap(r.detail ?? "")}`;
      } catch (err) {
        cible.innerHTML = `<span class="baisse">Erreur</span> — ${echap(err.message)}`;
      }
      b.disabled = false;
    }));
}

const LIBELLES_OBJECTIF = { croissance: "Capitalisation", dividendes: "Revenus", equilibre: "Équilibré" };
const LIBELLES_ALGO = { weighted: "Score pondéré", topsis: "TOPSIS" };

function segments(champ, options, valeurActive) {
  return `<span class="segments" data-champ="${champ}">${Object.entries(options)
    .map(([valeur, libelle]) => `<button data-valeur="${valeur}"
      class="${String(valeur) === String(valeurActive) ? "actif" : ""}">${libelle}</button>`)
    .join("")}</span>`;
}

async function vueParametres() {
  const [cfg, profil] = await Promise.all([
    api("/api/parametres/scoring"),
    api("/api/parametres/profil"),
  ]);
  const criteres = Object.entries(cfg.ponderations);
  const risques = Object.fromEntries([1, 2, 3, 4, 5, 6, 7].map((n) => [n, n]));
  const TYPES_TABLEAU = [["ACTION", "Actions"], ["ETF", "ETF"], ["OPCVM", "OPCVM"]];
  const casesColonnes = (type) => {
    const cle = "colonnes_" + type.toLowerCase();
    const actives = (profil[cle] && profil[cle].length ? profil[cle] : COLONNES_DEFAUT[type]);
    return ORDRE_COLONNES.map((c) => `<label class="case-colonne">
      <input type="checkbox" data-colonne="${type.toLowerCase()}" value="${c}"
        ${actives.includes(c) ? "checked" : ""}> ${echap(CATALOGUE_COLONNES[c].label)}</label>`).join("");
  };
  const urlsExemple = profil.urls_exemple || {};
  const champsUrls = Object.keys(urlsExemple).sort().map((nom) =>
    `<label class="champ" style="display:block;margin-bottom:6px">${echap(nom)}
      <input type="text" data-url-source="${echap(nom)}" value="${echap(urlsExemple[nom])}" style="width:100%"></label>`).join("");
  contenu.innerHTML = `
    <h1>Paramètres</h1>
    <h2>Profil investisseur</h2>
    <div class="panneau" id="panneau-profil">
      <div class="reglage"><span class="libelle-reglage">Objectif</span>
        ${segments("objectif", LIBELLES_OBJECTIF, profil.objectif)}</div>
      <div class="reglage"><span class="libelle-reglage">Profil de risque (1-7)</span>
        ${segments("niveau_risque", risques, profil.niveau_risque)}</div>
      <div class="reglage"><span class="libelle-reglage">Algorithme de décision</span>
        ${segments("algorithme_decision", LIBELLES_ALGO, profil.algorithme_decision)}</div>
      <div class="reglage"><span class="libelle-reglage">Horizon (années)</span>
        <input type="number" id="profil-horizon" value="${profil.horizon_annees}" min="1" max="40" style="width:90px">
      </div>
      <p class="note-bas" id="retour-profil">Ce profil pilote l'algorithme du classement
        du tableau de bord et pré-remplit le formulaire d'allocation.</p>
    </div>
    <h2>Pondérations du score</h2>
    <p class="sous-titre">Score propriétaire (0-100). La somme est renormalisée automatiquement.</p>
    <form class="panneau" id="form-poids">
      <div class="champs">
        ${criteres.map(([c, p]) => `<label class="champ">${c}
          <input type="number" name="${c}" value="${p}" min="0" max="100" step="1"></label>`).join("")}
        <button type="submit">Enregistrer et recalculer</button>
      </div>
      <p class="note-bas" id="retour-poids">Somme actuelle :
        ${criteres.reduce((somme, [, p]) => somme + p, 0)}</p>
    </form>
    <h2>Apparence &amp; disposition</h2>
    <div class="panneau" id="panneau-apparence">
      <div class="reglage"><span class="libelle-reglage">Largeur de la barre latérale (px)</span>
        <input type="number" id="largeur-barre" value="${profil.largeur_barre}" min="140" max="420" step="10" style="width:90px"></div>
      <div class="reglage"><span class="libelle-reglage">Délai mini de réactualisation (min)</span>
        <input type="number" id="reactu-minutes" value="${profil.reactualisation_minutes}" min="0" max="1440" step="1" style="width:90px"></div>
      <div class="champs">
        <label class="champ">Couleur en-tête Actions
          <input type="color" data-couleur="couleur_actions" value="${profil.couleur_actions}"></label>
        <label class="champ">Couleur en-tête ETF
          <input type="color" data-couleur="couleur_etf" value="${profil.couleur_etf}"></label>
        <label class="champ">Couleur en-tête OPCVM
          <input type="color" data-couleur="couleur_opcvm" value="${profil.couleur_opcvm}"></label>
      </div>
      <p class="note-bas" id="retour-apparence">La largeur s'applique aussi au glisser de la
        double flèche ; les couleurs à l'en-tête figé de chaque tableau de valeurs.</p>
    </div>
    <h2>Colonnes — chaque tableau a ses propres entêtes</h2>
    <div class="panneau" id="panneau-colonnes">
      ${TYPES_TABLEAU.map(([type, lib]) => `<div class="groupe-colonnes">
        <div class="entete-groupe">
          <span class="libelle-reglage">${lib}</span>
          <span class="actions-groupe">
            <button type="button" class="secondaire" data-tout="${type.toLowerCase()}">Tout sélectionner</button>
            <button type="button" data-enreg="${type.toLowerCase()}">Enregistrer</button>
            <button type="button" class="secondaire" data-reinit="${type.toLowerCase()}">Réinitialiser</button>
          </span>
        </div>
        <div class="cases-colonnes" data-groupe="${type.toLowerCase()}">${casesColonnes(type)}</div></div>`).join("")}
      <p class="note-bas" id="retour-colonnes">Chaque onglet a son propre jeu de colonnes (Actions
        aligné par défaut sur CHAMPS_FICHE). Les cases ne s'enregistrent pas automatiquement :
        « Enregistrer » conserve les choix, « Réinitialiser » revient au dernier état enregistré.</p>
    </div>
    <h2>Sources — URL de la page exemple (bouton « Tester »)</h2>
    <div class="panneau" id="panneau-urls">
      <div class="champs" style="flex-direction:column;align-items:stretch">${champsUrls}</div>
      <p class="note-bas" id="retour-urls">Le test d'une source récupère cette page : réponse JSON
        affichée en exemple, sinon extrait texte ; en cas d'échec, la cause en texte.</p>
    </div>`;
  document.getElementById("form-poids").addEventListener("submit", async (e) => {
    e.preventDefault();
    const poids = Object.fromEntries(
      [...new FormData(e.target)].map(([c, v]) => [c, Number(v)]));
    const r = await api("/api/parametres/scoring", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(poids),
    });
    document.getElementById("retour-poids").textContent =
      `Enregistré — scores recalculés pour ${r.actifs_recalcules} actifs.`;
  });

  // Interrupteurs du profil : chaque clic enregistre immédiatement.
  const enregistrerProfil = async (maj) => {
    await api("/api/parametres/profil", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(maj),
    });
    document.getElementById("retour-profil").textContent = "Profil enregistré ✓";
  };
  document.querySelectorAll("#panneau-profil .segments").forEach((groupe) =>
    groupe.addEventListener("click", async (e) => {
      const bouton = e.target.closest("button");
      if (!bouton) return;
      groupe.querySelectorAll("button").forEach((b) => b.classList.remove("actif"));
      bouton.classList.add("actif");
      const champ = groupe.dataset.champ;
      const brut = bouton.dataset.valeur;
      await enregistrerProfil({ [champ]: champ === "niveau_risque" ? Number(brut) : brut });
    }));
  document.getElementById("profil-horizon").addEventListener("change", async (e) => {
    await enregistrerProfil({ horizon_annees: Number(e.target.value) });
  });

  // Apparence : largeur de barre + couleurs des en-têtes.
  const retourApp = document.getElementById("retour-apparence");
  document.getElementById("largeur-barre").addEventListener("change", async (e) => {
    const px = Number(e.target.value);
    appliquerLargeurBarre(px);
    await enregistrerProfil({ largeur_barre: px });
    retourApp.textContent = "Largeur enregistrée ✓";
  });
  document.getElementById("reactu-minutes").addEventListener("change", async (e) => {
    await enregistrerProfil({ reactualisation_minutes: Number(e.target.value) });
    retourApp.textContent = "Délai de réactualisation enregistré ✓";
  });
  document.querySelectorAll("#panneau-apparence [data-couleur]").forEach((inp) =>
    inp.addEventListener("change", async () => {
      await enregistrerProfil({ [inp.dataset.couleur]: inp.value });
      retourApp.textContent = "Couleur enregistrée ✓";
    }));

  // Colonnes : chaque tableau (Actions/ETF/OPCVM) a son propre jeu d'entêtes.
  // Les modifications ne sont PAS enregistrées automatiquement : « Enregistrer »
  // conserve les choix, « Réinitialiser » revient au dernier état enregistré.
  const retourCol = document.getElementById("retour-colonnes");
  const casesDe = (type) => [...document.querySelectorAll(`[data-colonne="${type}"]`)];
  const cochees = (type) => casesDe(type).filter((c) => c.checked).map((c) => c.value);
  // Snapshot du dernier état enregistré, par onglet (état de départ = profil).
  const etatSauve = {};
  TYPES_TABLEAU.forEach(([TYPE, ]) => {
    const t = TYPE.toLowerCase();
    const p = profil["colonnes_" + t];
    etatSauve[t] = (p && p.length ? p : COLONNES_DEFAUT[TYPE]).slice();
  });
  const appliquerCases = (type, cles) => casesDe(type).forEach(
    (c) => { c.checked = cles.includes(c.value); });
  const marquerModifie = (type) => {
    const modifie = JSON.stringify(cochees(type)) !== JSON.stringify(etatSauve[type]);
    retourCol.textContent = modifie
      ? `Modifications non enregistrées (${type}). « Enregistrer » ou « Réinitialiser ».`
      : "Colonnes à jour.";
  };
  document.querySelectorAll("#panneau-colonnes [data-colonne]").forEach((inp) =>
    inp.addEventListener("change", () => marquerModifie(inp.dataset.colonne)));
  // « Tout sélectionner » : coche toutes les colonnes (sans enregistrer).
  document.querySelectorAll("#panneau-colonnes [data-tout]").forEach((b) =>
    b.addEventListener("click", () => {
      casesDe(b.dataset.tout).forEach((c) => { c.checked = true; });
      marquerModifie(b.dataset.tout);
    }));
  // « Enregistrer » : conserve les choix et met à jour l'état de référence.
  document.querySelectorAll("#panneau-colonnes [data-enreg]").forEach((b) =>
    b.addEventListener("click", async () => {
      const type = b.dataset.enreg;
      const cles = cochees(type);
      await enregistrerProfil({ ["colonnes_" + type]: cles });
      etatSauve[type] = cles.slice();
      retourCol.textContent = `Colonnes ${type} enregistrées ✓`;
    }));
  // « Réinitialiser » : revient au dernier état enregistré (annule les modifs).
  document.querySelectorAll("#panneau-colonnes [data-reinit]").forEach((b) =>
    b.addEventListener("click", () => {
      const type = b.dataset.reinit;
      appliquerCases(type, etatSauve[type]);
      retourCol.textContent = `Colonnes ${type} réinitialisées à l'état enregistré.`;
    }));

  // URL de page exemple par source (utilisée par le bouton « Tester »).
  const retourUrls = document.getElementById("retour-urls");
  document.querySelectorAll("#panneau-urls [data-url-source]").forEach((inp) =>
    inp.addEventListener("change", async () => {
      const urls = {};
      document.querySelectorAll("#panneau-urls [data-url-source]").forEach((i) => {
        urls[i.dataset.urlSource] = i.value.trim();
      });
      await enregistrerProfil({ urls_exemple: urls });
      retourUrls.textContent = "URL enregistrée ✓";
    }));
}

async function vueSysteme() {
  const [rapport, anomalies, suggestions] = await Promise.all([
    api("/api/meta/sante"),
    api("/api/meta/anomalies?statut=toutes"),
    api("/api/meta/suggestions"),
  ]);
  const predictif = rapport?.pouvoir_predictif;
  const completude = rapport ? Object.entries(rapport.completude_par_champ) : [];
  const STATUT_ANOMALIE = { ouverte: "ouverte", ignoree: "ignorée", resolue: "résolue" };
  contenu.innerHTML = `
    <h1>Système — auto-observation &amp; auto-amélioration</h1>
    <p class="sous-titre">Le système s'observe (qualité des données, anomalies, pouvoir prédictif du score)
      et propose ses propres améliorations. Validation humaine par défaut
      (<code>meta.optimisation.auto_appliquer</code> pour la boucle fermée).</p>
    <div class="panneau">
      <button id="btn-observer">Lancer l'auto-diagnostic</button>
      <button id="btn-optimiser" class="secondaire">Optimiser les pondérations</button>
      <span class="muted" id="retour-meta"></span>
    </div>
    ${rapport ? `
    <div class="tuiles">
      ${tuile("Complétude des données", fmt(rapport.completude_globale_pct, 0), " %")}
      ${tuile("Anomalies ouvertes", rapport.anomalies_ouvertes)}
      ${tuile("Cours périmés", rapport.actifs_cours_perimes)}
      ${tuile("Imports en erreur (7 j)", rapport.imports_en_erreur_7j)}
      ${tuile("Corrélation score → rendement",
              predictif?.correlation === null || predictif?.correlation === undefined
                ? "—" : fmt(predictif.correlation, 2))}
    </div>
    <h2>Recommandations du système</h2>
    <div class="carte">${rapport.recommandations.length
      ? `<ul>${rapport.recommandations.map((r) => `<li>${echap(r)}</li>`).join("")}</ul>`
      : `<p class="muted">Aucune recommandation : le système ne détecte rien à améliorer.</p>`}
      ${predictif?.correlation === null
        ? `<p class="note-bas">${echap(predictif.detail)}</p>` : ""}
    </div>
    <h2>Complétude par champ (${completude.length} champs suivis)</h2>
    <div class="carte"><div class="table-scroll"><table>
      <thead><tr><th>Champ</th><th class="num">Renseigné (%)</th><th>Remplissage</th></tr></thead>
      <tbody>${completude.map(([champ, pct]) => `<tr>
        <td>${echap(champ)}</td>
        <td class="num ${pct < 60 ? "baisse" : "hausse"}">${fmt(pct, 0)} %</td>
        <td><span class="barre-piste" style="display:inline-block;width:180px">
          <span class="barre" style="width:${pct}%"></span></span></td>
      </tr>`).join("")}</tbody></table></div></div>`
    : `<div class="carte"><p class="muted">Aucun diagnostic encore. Cliquer sur
       « Lancer l'auto-diagnostic ».</p></div>`}
    <h2>Anomalies (${anomalies.length}) — toutes gravités et statuts</h2>
    <div class="carte"><div class="table-scroll"><table>
      <thead><tr><th>Date (UTC)</th><th>Gravité</th><th>Type</th><th>ISIN</th>
        <th>Message</th><th>Statut</th><th></th></tr></thead>
      <tbody>${anomalies.map((a) => `<tr>
        <td class="muted">${a.date.replace("T", " ").slice(0, 16)}</td>
        <td class="${a.gravite === "critique" ? "baisse" : ""}">${a.gravite}</td>
        <td>${echap(a.type)}</td>
        <td class="muted">${echap(a.isin ?? "—")}</td>
        <td>${echap(a.message)}</td>
        <td class="${a.statut === "ouverte" ? "" : "muted"}">${echap(STATUT_ANOMALIE[a.statut] ?? a.statut)}</td>
        <td>${a.statut === "ouverte"
          ? `<button class="secondaire" data-anomalie="${a.id}">Ignorer</button>` : ""}</td>
      </tr>`).join("") || `<tr><td colspan="7" class="muted">Aucune anomalie.</td></tr>`}
      </tbody></table></div></div>
    <h2>Suggestions de pondérations</h2>
    <div class="carte"><div class="table-scroll"><table>
      <thead><tr><th>Date (UTC)</th><th>Pondérations proposées</th>
        <th class="num">Corrélation avant → après</th><th>Statut</th><th></th></tr></thead>
      <tbody>${suggestions.map((s) => `<tr>
        <td class="muted">${s.date.replace("T", " ").slice(0, 16)}</td>
        <td>${Object.entries(s.ponderations).map(([c, p]) => `${echap(c)} ${p}`).join(" · ")}</td>
        <td class="num">${fmt(s.correlation_avant, 2)} → <span class="hausse">${fmt(s.correlation_apres, 2)}</span></td>
        <td>${s.statut}</td>
        <td>${s.statut === "proposee" ? `
          <button data-appliquer="${s.id}">Appliquer</button>
          <button class="secondaire" data-rejeter="${s.id}">Rejeter</button>` : ""}</td>
      </tr>`).join("") || `<tr><td colspan="5" class="muted">Aucune suggestion.
        L'optimisation nécessite plusieurs mises à jour avec des cours qui évoluent.</td></tr>`}
      </tbody></table></div></div>`;

  document.getElementById("btn-observer").addEventListener("click", async (e) => {
    e.target.disabled = true;
    await api("/api/meta/observer", { method: "POST" });
    vueSysteme();
  });
  document.getElementById("btn-optimiser").addEventListener("click", async (e) => {
    e.target.disabled = true;
    const r = await api("/api/meta/optimiser", { method: "POST" });
    if (r.suggestion) { vueSysteme(); }
    else {
      document.getElementById("retour-meta").textContent = r.detail;
      e.target.disabled = false;
    }
  });
  contenu.querySelectorAll("[data-anomalie]").forEach((b) =>
    b.addEventListener("click", async () => {
      await api(`/api/meta/anomalies/${b.dataset.anomalie}/ignorer`, { method: "POST" });
      vueSysteme();
    }));
  contenu.querySelectorAll("[data-appliquer]").forEach((b) =>
    b.addEventListener("click", async () => {
      await api(`/api/meta/suggestions/${b.dataset.appliquer}/appliquer`, { method: "POST" });
      vueSysteme();
    }));
  contenu.querySelectorAll("[data-rejeter]").forEach((b) =>
    b.addEventListener("click", async () => {
      await api(`/api/meta/suggestions/${b.dataset.rejeter}/rejeter`, { method: "POST" });
      vueSysteme();
    }));
}

/* --- Routage ------------------------------------------------------------ */

const VUES = {
  dashboard: vueDashboard,
  actions: () => vueActifs("ACTION", "Actions éligibles PEA"),
  etf: () => vueActifs("ETF", "ETF éligibles PEA"),
  opcvm: () => vueActifs("OPCVM", "OPCVM éligibles PEA"),
  allocation: vueAllocation,
  simulateur: vueSimulateur,
  watchlist: vueWatchlist,
  historique: vueHistorique,
  sources: vueSources,
  parametres: vueParametres,
  systeme: vueSysteme,
};

async function router() {
  const vue = location.hash.slice(1) || "dashboard";
  document.querySelectorAll(".nav-link").forEach((l) =>
    l.classList.toggle("actif", l.dataset.vue === vue));
  try {
    await (VUES[vue] || vueDashboard)();
  } catch (err) {
    contenu.innerHTML = `<h1>Erreur</h1><p class="baisse">${echap(err.message)}</p>`;
  }
}

window.addEventListener("hashchange", router);
// Largeur de barre du profil appliquée au démarrage (peut différer du localStorage).
api("/api/parametres/profil")
  .then((p) => { if (p.largeur_barre) appliquerLargeurBarre(p.largeur_barre); })
  .catch(() => {});
router();

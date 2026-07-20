/* PEAdvisor — application monopage (vanilla JS, aucune dépendance). */

const contenu = document.getElementById("contenu");

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

// Colonnes du tableau : clé de tri, accès à la valeur, rendu de cellule.
const COLONNES_ACTIFS = [
  { cle: "nom", label: "Nom", num: false, val: (a) => a.nom || "",
    cell: (a) => `<span class="pastille ${a.type}"></span>${echap(a.nom)}` },
  { cle: "isin", label: "ISIN", num: false, val: (a) => a.isin,
    cell: (a) => `<span class="muted">${a.isin}</span>` },
  { cle: "secteur", label: "Secteur", num: false, val: (a) => a.secteur || "",
    cell: (a) => echap(a.secteur ?? "—") },
  { cle: "cours", label: "Cours", num: true, val: (a) => a.cours, cell: (a) => fmt(a.cours, 2) },
  { cle: "variation_pct", label: "Var. %", num: true, val: (a) => a.variation_pct,
    cell: (a) => `<span class="${a.variation_pct > 0 ? "hausse" : a.variation_pct < 0 ? "baisse" : ""}">${fmt(a.variation_pct, 2)}</span>` },
  { cle: "rendement", label: "Rdt %", num: true, val: (a) => a.rendement, cell: (a) => fmt(a.rendement, 1) },
  { cle: "per", label: "PER", num: true, val: (a) => a.per, cell: (a) => fmt(a.per, 1) },
  { cle: "potentiel", label: "Potentiel %", num: true, val: (a) => a.potentiel,
    cell: (a) => `<span class="${a.potentiel > 0 ? "hausse" : "baisse"}">${fmt(a.potentiel, 1)}</span>` },
  { cle: "volume", label: "Volume", num: true, val: (a) => a.volume, cell: (a) => volumeCourt(a.volume) },
  { cle: "volatilite", label: "Vol. %", num: true, val: (a) => a.indicateurs_quant?.volatilite_pct,
    cell: (a) => fmt(a.indicateurs_quant?.volatilite_pct, 1) },
  { cle: "sharpe", label: "Sharpe", num: true, val: (a) => a.indicateurs_quant?.sharpe,
    cell: (a) => fmt(a.indicateurs_quant?.sharpe, 2) },
  { cle: "score_esg", label: "ESG", num: true, val: (a) => a.score_esg, cell: (a) => fmt(a.score_esg, 0) },
  { cle: "niveau_risque", label: "Risque", num: true, val: (a) => a.niveau_risque,
    cell: (a) => `${a.niveau_risque ?? "—"}/7` },
  { cle: "score_global", label: "Score", num: true, val: (a) => a.score_global,
    cell: (a) => `<span class="score-badge">${fmt(a.score_global, 0)}</span>` },
  { cle: "source", label: "Source", num: false, val: (a) => a.source || "",
    cell: (a) => `<span class="muted">${echap(a.source ?? "—")}</span>` },
];

function trierActifs(liste) {
  const col = COLONNES_ACTIFS.find((c) => c.cle === triActifs.cle) || COLONNES_ACTIFS[0];
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

async function vueActifs(type, titre) {
  const [actifs, scrapers] = await Promise.all([
    api(`/api/actifs?type=${type}`),
    api("/api/sources/scrapers"),
  ]);
  const aDuSeed = actifs.some((a) => a.source === "seed");

  const barreRecherche = type === "ACTION" ? `
    <form class="panneau" id="form-scrap">
      <label class="champ" style="display:block;margin-bottom:8px">Ajouter une valeur (nom, ISIN ou code) — choisir la source :
        <input type="text" id="scrap-requete" placeholder="ex. Air Liquide, FR0000120073 ou 1rPAI" style="width:340px"></label>
      <div class="champs">
        ${scrapers.map((s) => `<button type="button" class="${s.valide ? "" : "secondaire"}"
          data-source="${s.nom}" title="${s.valide ? "Source validée" : "Source à valider — envoyer une page exemple"}">
          ${echap(s.libelle)}${s.valide ? "" : " *"}</button>`).join("")}
      </div>
      <p class="note-bas" id="retour-scrap">« * » : source branchée mais parseur à fiabiliser (envoyer une page exemple).</p>
    </form>` : "";

  const toggleSeed = aDuSeed ? `<button class="secondaire" id="toggle-seed">${
    masquerSeed ? "Afficher les données de démonstration" : "Masquer les données de démonstration (seed)"}</button>` : "";

  contenu.innerHTML = `
    <h1>${titre}</h1>
    <p class="sous-titre">${actifs.length} valeur(s). Cliquer sur un en-tête de colonne pour trier. ${toggleSeed}</p>
    ${barreRecherche}
    <div class="carte"><div class="table-scroll"><table id="table-actifs">
      <thead><tr>${COLONNES_ACTIFS.map((c) => `<th class="triable ${c.num ? "num" : ""}"
        data-cle="${c.cle}">${c.label}${triActifs.cle === c.cle ? (triActifs.sens < 0 ? " ▾" : " ▴") : ""}</th>`).join("")}
        <th></th></tr></thead>
      <tbody id="corps-actifs"></tbody></table></div></div>`;

  function dessinerLignes() {
    const liste = masquerSeed ? actifs.filter((a) => a.source !== "seed") : actifs;
    document.getElementById("corps-actifs").innerHTML = trierActifs(liste).map((a) => `<tr>
      ${COLONNES_ACTIFS.map((c) => `<td class="${c.num ? "num" : ""}">${c.cell(a)}</td>`).join("")}
      <td><button class="secondaire" data-watch="${a.isin}" title="Ajouter à la watchlist">☆</button></td>
    </tr>`).join("");
    document.querySelectorAll("[data-watch]").forEach((b) =>
      b.addEventListener("click", async () => {
        await api(`/api/watchlist/${b.dataset.watch}`, { method: "POST" });
        b.textContent = "★";
      }));
  }
  dessinerLignes();

  // Tri au clic sur les en-têtes.
  document.querySelectorAll("th.triable").forEach((th) =>
    th.addEventListener("click", () => {
      const cle = th.dataset.cle;
      if (triActifs.cle === cle) triActifs.sens *= -1;
      else { triActifs.cle = cle; triActifs.sens = COLONNES_ACTIFS.find((c) => c.cle === cle).num ? -1 : 1; }
      vueActifs(type, titre);
    }));

  if (aDuSeed) {
    document.getElementById("toggle-seed").addEventListener("click", () => {
      masquerSeed = !masquerSeed;
      vueActifs(type, titre);
    });
  }

  const form = document.getElementById("form-scrap");
  if (form) {
    form.querySelectorAll("[data-source]").forEach((bouton) =>
      bouton.addEventListener("click", async () => {
        const requete = document.getElementById("scrap-requete").value.trim();
        const retour = document.getElementById("retour-scrap");
        if (!requete) { retour.textContent = "Saisir un nom, un ISIN ou un code."; return; }
        retour.textContent = `Recherche sur ${bouton.textContent.trim()}…`;
        try {
          const r = await api(`/api/import/web/${bouton.dataset.source}/${encodeURIComponent(requete)}`,
                              { method: "POST" });
          const d = r.donnees_extraites || {};
          const extra = [
            d.objectif_cours != null ? `objectif ${fmt(d.objectif_cours, 2)}` : null,
            d.potentiel != null ? `potentiel ${fmt(d.potentiel, 1)} %` : null,
            d.consensus_bourso != null ? `consensus ${fmt(d.consensus_bourso, 2)}` : null,
            d.risque_esg != null ? `risque ESG ${fmt(d.risque_esg, 1)}` : null,
          ].filter(Boolean).join(" · ");
          retour.innerHTML = `<span class="hausse">${r.cree ? "Ajouté" : "Mis à jour"}</span> : `
            + `${echap(r.nom)} (${r.isin}) — cours ${fmt(r.cours, 2)}, source ${echap(r.source)}`
            + (extra ? `<br><span class="muted">${echap(extra)}</span>` : "");
          setTimeout(() => vueActifs(type, titre), 1200);
        } catch (err) {
          retour.innerHTML = `<span class="baisse">Échec (${echap(bouton.textContent.trim())})</span> — ${echap(err.message)}`;
        }
      }));
  }
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
    document.getElementById("resultat-allocation").innerHTML = `
      <div class="cartes">${grapheBarres("Répartition par type (%)", repartition)}</div>
      <h2>${r.lignes.length} lignes proposées</h2>
      <div class="carte"><div class="table-scroll"><table>
        <thead><tr><th>Valeur</th><th>Secteur</th><th class="num">Poids</th>
          <th class="num">Montant</th><th class="num">Score</th><th>Justification</th></tr></thead>
        <tbody>${r.lignes.map((l) => `<tr>
          <td><span class="pastille ${l.type}"></span>${echap(l.nom)}</td>
          <td>${echap(l.secteur ?? "—")}</td>
          <td class="num">${(l.poids * 100).toFixed(1)} %</td>
          <td class="num">${euros(l.montant)}</td>
          <td class="num score-badge">${fmt(l.score_global, 0)}</td>
          <td class="muted">${echap(l.justification)}</td></tr>`).join("")}
        </tbody></table></div>
        <p class="note-bas">${echap(r.commentaire)}</p></div>`;
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
      d'environnement, qui priment. Le test interroge un titre (TotalEnergies) et
      indique le nombre de points d'historique reçus. Détails et comparatif des
      sources : <code>docs/09-sources-donnees.md</code>.</p>
    </div>`;
  contenu.querySelectorAll("[data-tester]").forEach((b) =>
    b.addEventListener("click", async () => {
      const cible = document.getElementById(`test-${b.dataset.tester}`);
      cible.textContent = "test en cours…";
      b.disabled = true;
      try {
        const r = await api(`/api/sources/${b.dataset.tester}/tester`, { method: "POST" });
        cible.innerHTML = r.ok
          ? `<span class="hausse">OK</span> — ${r.points_historique ?? 0} point(s) d'historique`
            + (r.cotation?.cours ? `, cours ${r.cotation.cours}` : "")
          : `<span class="baisse">Échec</span> — ${echap(r.erreur ?? r.info ?? "")}`;
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
    </form>`;
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
}

async function vueSysteme() {
  const [rapport, anomalies, suggestions] = await Promise.all([
    api("/api/meta/sante"),
    api("/api/meta/anomalies?statut=ouverte"),
    api("/api/meta/suggestions"),
  ]);
  const predictif = rapport?.pouvoir_predictif;
  const completude = rapport ? Object.entries(rapport.completude_par_champ) : [];
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
    <h2>Complétude par champ</h2>
    <div class="cartes">${grapheBarres("Champs renseignés (%)",
      Object.fromEntries(completude))}</div>`
    : `<div class="carte"><p class="muted">Aucun diagnostic encore. Cliquer sur
       « Lancer l'auto-diagnostic ».</p></div>`}
    <h2>Anomalies ouvertes (${anomalies.length})</h2>
    <div class="carte"><div class="table-scroll"><table>
      <thead><tr><th>Date (UTC)</th><th>Gravité</th><th>Type</th><th>Message</th><th></th></tr></thead>
      <tbody>${anomalies.map((a) => `<tr>
        <td class="muted">${a.date.replace("T", " ").slice(0, 16)}</td>
        <td class="${a.gravite === "critique" ? "baisse" : ""}">${a.gravite}</td>
        <td>${echap(a.type)}</td>
        <td>${echap(a.message)}</td>
        <td><button class="secondaire" data-anomalie="${a.id}">Ignorer</button></td>
      </tr>`).join("") || `<tr><td colspan="5" class="muted">Aucune anomalie ouverte.</td></tr>`}
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
router();

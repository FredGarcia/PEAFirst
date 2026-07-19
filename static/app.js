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
  const s = await api("/api/dashboard/synthese");
  const classement = await api("/api/dashboard/classement?methode=topsis&limite=10");
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
    <h2>Matrice de décision multicritère (TOPSIS)</h2>
    <div class="carte"><div class="table-scroll"><table>
      <thead><tr><th>Rang</th><th>Valeur</th><th>Type</th><th class="num">Proximité idéale</th></tr></thead>
      <tbody>${classement.map((l) => `<tr>
        <td class="num">${l.rang}</td>
        <td><span class="pastille ${l.type}"></span>${echap(l.nom)}</td>
        <td>${l.type}</td>
        <td class="num">${fmt(l.valeur, 3)}</td></tr>`).join("")}
      </tbody></table></div>
      <p class="note-bas">Classement TOPSIS : proximité à la solution idéale (0 à 1), pondérations de config/scoring.yaml.</p>
    </div>`;
}

async function vueActifs(type, titre) {
  const actifs = await api(`/api/actifs?type=${type}`);
  contenu.innerHTML = `
    <h1>${titre}</h1>
    <p class="sous-titre">${actifs.length} valeur(s), triées par score global décroissant.</p>
    <div class="carte"><div class="table-scroll"><table>
      <thead><tr>
        <th>Nom</th><th>ISIN</th><th>Secteur</th>
        <th class="num">Cours</th><th class="num">Rdt %</th><th class="num">PER</th>
        <th class="num">Potentiel %</th><th class="num">ESG</th><th class="num">Risque</th>
        <th class="num">Score</th><th></th>
      </tr></thead>
      <tbody>${actifs.map((a) => `<tr>
        <td><span class="pastille ${a.type}"></span>${echap(a.nom)}</td>
        <td class="muted">${a.isin}</td>
        <td>${echap(a.secteur ?? "—")}</td>
        <td class="num">${fmt(a.cours, 2)}</td>
        <td class="num">${fmt(a.rendement, 1)}</td>
        <td class="num">${fmt(a.per, 1)}</td>
        <td class="num ${a.potentiel > 0 ? "hausse" : "baisse"}">${fmt(a.potentiel, 1)}</td>
        <td class="num">${fmt(a.score_esg, 0)}</td>
        <td class="num">${a.niveau_risque ?? "—"}/7</td>
        <td class="num score-badge">${fmt(a.score_global, 0)}</td>
        <td><button class="secondaire" data-watch="${a.isin}" title="Ajouter à la watchlist">☆</button></td>
      </tr>`).join("")}</tbody></table></div></div>`;
  contenu.querySelectorAll("[data-watch]").forEach((b) =>
    b.addEventListener("click", async () => {
      await api(`/api/watchlist/${b.dataset.watch}`, { method: "POST" });
      b.textContent = "★";
    }));
}

async function vueAllocation() {
  contenu.innerHTML = `
    <h1>Allocation automatique</h1>
    <p class="sous-titre">Proposition indicative selon capital, profil de risque, horizon et objectif.</p>
    <form class="panneau" id="form-allocation">
      <div class="champs">
        <label class="champ">Capital (€)
          <input type="number" name="capital" value="10000" min="100" step="100" required></label>
        <label class="champ">Niveau de risque (1-7)
          <input type="number" name="niveau_risque" value="4" min="1" max="7" required></label>
        <label class="champ">Horizon (années)
          <input type="number" name="horizon_annees" value="10" min="1" max="40" required></label>
        <label class="champ">Objectif
          <select name="objectif">
            <option value="equilibre">Équilibré</option>
            <option value="croissance">Croissance</option>
            <option value="dividendes">Dividendes (revenus)</option>
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
    <div class="carte">
      <p>Source active : <strong>${echap(s.source_active)}</strong></p>
      <p>Sources disponibles : ${s.sources_disponibles.map(echap).join(", ")}</p>
      <p class="note-bas">La source active se change dans <code>config/settings.yaml</code>
      (clé <code>donnees.source_active</code>). « seed » = jeu de données local de démonstration ;
      « yahoo » = Yahoo Finance via yfinance (accès réseau requis).</p>
    </div>`;
}

async function vueParametres() {
  const cfg = await api("/api/parametres/scoring");
  const criteres = Object.entries(cfg.ponderations);
  contenu.innerHTML = `
    <h1>Paramètres du score</h1>
    <p class="sous-titre">Pondérations du score propriétaire (0-100). La somme est renormalisée automatiquement.</p>
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
}

/* --- Routage ------------------------------------------------------------ */

const VUES = {
  dashboard: vueDashboard,
  actions: () => vueActifs("ACTION", "Actions éligibles PEA"),
  etf: () => vueActifs("ETF", "ETF éligibles PEA"),
  opcvm: () => vueActifs("OPCVM", "OPCVM éligibles PEA"),
  allocation: vueAllocation,
  watchlist: vueWatchlist,
  historique: vueHistorique,
  sources: vueSources,
  parametres: vueParametres,
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

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

async function vueActifs(type, titre) {
  const actifs = await api(`/api/actifs?type=${type}`);
  contenu.innerHTML = `
    <h1>${titre}</h1>
    <p class="sous-titre">${actifs.length} valeur(s), triées par score global décroissant.</p>
    <div class="carte"><div class="table-scroll"><table>
      <thead><tr>
        <th>Nom</th><th>ISIN</th><th>Secteur</th>
        <th class="num">Cours</th><th class="num">Rdt %</th><th class="num">PER</th>
        <th class="num">Potentiel %</th><th class="num">Vol. %</th>
        <th class="num" title="Ratio de Sharpe (annualisé)">Sharpe</th>
        <th class="num" title="Pire baisse depuis un plus-haut">Perte max %</th>
        <th class="num">ESG</th><th class="num">Risque</th>
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
        <td class="num">${fmt(a.indicateurs_quant?.volatilite_pct, 1)}</td>
        <td class="num">${fmt(a.indicateurs_quant?.sharpe, 2)}</td>
        <td class="num baisse">${fmt(a.indicateurs_quant?.drawdown_max_pct, 1)}</td>
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
        <td>${src.testable ? `<button class="secondaire" data-tester="${src.nom}">Tester</button>` : ""}</td>
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

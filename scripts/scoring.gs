/**
 * scoring.gs — moteur de score propriétaire, générique et paramétrable.
 *
 * Module de core/ : aucune référence à une enveloppe (PEA, AV, CTO). Les
 * pondérations et l'univers proviennent du config.gs de l'enveloppe appelante.
 *
 * Transposition de scripts/scoring.py du dépôt PEAFirst : mêmes règles de
 * calcul, mêmes garde-fous, afin que le score affiché dans la feuille soit
 * identique à celui produit par la chaîne de données.
 *
 * Règle directrice : un critère sans donnée n'est jamais remplacé par une
 * valeur neutre. Il est retiré du calcul et les pondérations restantes sont
 * renormalisées ; `couverture` indique la part du barème réellement évaluée.
 *
 * Usage depuis un config.gs d'enveloppe :
 *
 *   var resultats = SCORING_calculer(lignes, config.PONDERATIONS, {
 *     champType: 'Type',          // population de comparaison
 *     minCouverture: 30            // en pourcentage du barème
 *   });
 */

/** Sens de chaque critère : 1 = plus haut est meilleur, -1 = plus bas. */
var SCORING_CRITERES = {
  performance:  { champ: 'Perf_periode_pct',           sens: 1 },
  volatilite:   { champ: 'Volatilite_annualisee_pct',  sens: -1 },
  sharpe:       { champ: 'Sharpe',                     sens: 1 },
  sortino:      { champ: 'Sortino',                    sens: 1 },
  drawdown:     { champ: 'Drawdown_max_pct',           sens: 1 },
  esg:          { champ: 'Esg_note',                   sens: 1 },
  potentiel:    { champ: 'Potentiel',                  sens: 1 },
  valorisation: { champ: 'PER',                        sens: -1 },
  croissance:   { champ: 'Croissance',                 sens: 1 },
  dividende:    { champ: 'Rendement',                  sens: 1 },
  consensus:    { champ: 'Consensus',                  sens: 1 }
};

/** Population minimale pour qu'un rang percentile ait un sens. */
var SCORING_MIN_POPULATION = 5;

/** Nombre minimal de critères notés pour émettre un score global. */
var SCORING_MIN_CRITERES = 2;

/**
 * Convertit une valeur de cellule en nombre, ou null si absente/illisible.
 * Gère la virgule décimale et les marqueurs de donnée manquante.
 */
function SCORING_nombre(valeur) {
  if (valeur === null || valeur === undefined) { return null; }
  if (typeof valeur === 'number') { return isFinite(valeur) ? valeur : null; }
  var texte = String(valeur).trim().replace(',', '.');
  if (texte === '' || texte === '-' || texte.toLowerCase() === 'n/a') { return null; }
  var n = parseFloat(texte);
  return isFinite(n) ? n : null;
}

/**
 * Rangs percentiles dans [0, 1], moyennés sur les ex aequo.
 * Le rang évite qu'une valeur aberrante comprime l'échelle, contrairement à
 * une normalisation min-max.
 */
function SCORING_rangs(valeurs) {
  var n = valeurs.length;
  var rangs = {};
  if (n === 0) { return rangs; }
  if (n === 1) { rangs[valeurs[0]] = 0.5; return rangs; }
  var tries = valeurs.slice().sort(function (a, b) { return a - b; });
  var i = 0;
  while (i < n) {
    var j = i;
    while (j + 1 < n && tries[j + 1] === tries[i]) { j += 1; }
    rangs[tries[i]] = ((i + j) / 2) / (n - 1);
    i = j + 1;
  }
  return rangs;
}

/**
 * Calcule les scores d'un ensemble de lignes.
 *
 * @param {Array<Object>} lignes    Objets porteurs des champs de SCORING_CRITERES.
 * @param {Object} ponderations     Critère -> poids (les poids nuls sont ignorés).
 * @param {Object} options          champType, minCouverture.
 * @return {Array<Object>} Lignes { index, score, couverture, criteres, rang },
 *     triées par score décroissant. Les lignes sans données suffisantes sont
 *     absentes du résultat : elles ne sont pas notées zéro.
 */
function SCORING_calculer(lignes, ponderations, options) {
  options = options || {};
  var champType = options.champType || 'Type';
  var minCouverture = (options.minCouverture === undefined) ? 30 : options.minCouverture;

  // Poids retenus : critères connus, strictement positifs.
  var poids = {};
  var poidsTotal = 0;
  for (var cle in ponderations) {
    if (!ponderations.hasOwnProperty(cle)) { continue; }
    if (cle.charAt(0) === '_' || !SCORING_CRITERES[cle]) { continue; }
    var p = SCORING_nombre(ponderations[cle]);
    if (p !== null && p > 0) { poids[cle] = p; poidsTotal += p; }
  }
  if (poidsTotal === 0) { return []; }

  // Regroupement par population comparable : on ne compare pas la volatilité
  // d'un ETF à celle d'une petite capitalisation.
  var groupes = {};
  for (var i = 0; i < lignes.length; i += 1) {
    var t = String(lignes[i][champType] || '');
    if (!groupes[t]) { groupes[t] = []; }
    groupes[t].push(i);
  }

  var notes = [];
  for (var k = 0; k < lignes.length; k += 1) { notes.push({}); }

  for (var type in groupes) {
    if (!groupes.hasOwnProperty(type)) { continue; }
    var indices = groupes[type];
    for (var critere in poids) {
      if (!poids.hasOwnProperty(critere)) { continue; }
      var def = SCORING_CRITERES[critere];
      var presents = [];
      var valeurs = [];
      for (var a = 0; a < indices.length; a += 1) {
        var v = SCORING_nombre(lignes[indices[a]][def.champ]);
        if (v !== null) { presents.push(indices[a]); valeurs.push(v); }
      }
      if (presents.length < SCORING_MIN_POPULATION) { continue; }
      var rangs = SCORING_rangs(valeurs);
      for (var b = 0; b < presents.length; b += 1) {
        var r = rangs[valeurs[b]];
        notes[presents[b]][critere] = (def.sens > 0 ? r : 1 - r) * 100;
      }
    }
  }

  var resultats = [];
  for (var idx = 0; idx < lignes.length; idx += 1) {
    var note = notes[idx];
    var criteres = Object.keys(note);
    if (criteres.length < SCORING_MIN_CRITERES) { continue; }
    var poidsDispo = 0;
    var cumul = 0;
    for (var c = 0; c < criteres.length; c += 1) {
      poidsDispo += poids[criteres[c]];
      cumul += note[criteres[c]] * poids[criteres[c]];
    }
    var couverture = 100 * poidsDispo / poidsTotal;
    if (couverture < minCouverture) { continue; }
    resultats.push({
      index: idx,
      score: Math.round((cumul / poidsDispo) * 10) / 10,
      couverture: Math.round(couverture * 10) / 10,
      criteres: criteres.sort().join('|')
    });
  }

  resultats.sort(function (x, y) { return y.score - x.score; });
  for (var n2 = 0; n2 < resultats.length; n2 += 1) { resultats[n2].rang = n2 + 1; }
  return resultats;
}

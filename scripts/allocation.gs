/**
 * allocation.gs — moteur d'allocation générique et paramétrable.
 *
 * Module de core/ : aucune référence à une enveloppe (PEA, AV, CTO). L'univers
 * éligible et les contraintes viennent du config.gs de l'enveloppe appelante,
 * ce qui permet à la même logique de servir les trois enveloppes.
 *
 * Transposition de scripts/allocation.py du dépôt PEAFirst.
 *
 * Le profil de risque suit les bornes de volatilité annualisée de PRIIPS
 * (indicateur SRI), pour rester comparable aux documents d'information des
 * fonds. Deux limites à connaître :
 *
 *  - les corrélations ne sont pas modélisées : la volatilité annoncée est une
 *    moyenne pondérée, donc un majorant du risque réel du portefeuille ;
 *  - l'objectif « revenus » ne peut être servi faute de données de dividendes ;
 *    il est traité comme une recherche de régularité, et signalé comme tel.
 *
 * Usage :
 *   var r = ALLOC_construire(candidats, {
 *     capital: 10000, risque: 4, horizon: 8, objectif: 'croissance', lignes: 10
 *   });
 *   // r.lignes : [{ isin, nom, poids, montant, score, vol }, ...]
 */

/** Bornes de volatilité annualisée (%) par niveau SRI, d'après PRIIPS. */
var ALLOC_BANDES_SRI = {
  1: [0, 0.5], 2: [0.5, 5], 3: [5, 12], 4: [12, 20],
  5: [20, 30], 6: [30, 80], 7: [80, 1000]
};

/** Poids maximal d'une ligne selon le profil : un profil prudent se disperse. */
var ALLOC_PLAFOND_LIGNE = {
  1: 0.15, 2: 0.15, 3: 0.20, 4: 0.20, 5: 0.25, 6: 0.30, 7: 0.35
};

/** En deçà, la diversification est jugée insuffisante. */
var ALLOC_MIN_LIGNES = 5;

/**
 * Volatilité maximale admise, resserrée si l'horizon est court : moins de
 * temps disponible pour absorber une baisse.
 */
function ALLOC_plafondVolatilite(risque, horizon) {
  var haut = ALLOC_BANDES_SRI[risque][1];
  if (horizon < 3) { return Math.min(haut, ALLOC_BANDES_SRI[Math.max(1, risque - 2)][1]); }
  if (horizon < 5) { return Math.min(haut, ALLOC_BANDES_SRI[Math.max(1, risque - 1)][1]); }
  return haut;
}

/** Filtre par volatilité puis ordonne selon l'objectif. */
function ALLOC_selectionner(candidats, volMax, objectif) {
  var retenus = [];
  for (var i = 0; i < candidats.length; i += 1) {
    var v = candidats[i].vol;
    if (typeof v === 'number' && isFinite(v) && v <= volMax) { retenus.push(candidats[i]); }
  }
  if (objectif === 'croissance') {
    retenus.sort(function (a, b) { return b.score - a.score; });
  } else if (objectif === 'revenus') {
    // Sans dividendes : régularité d'abord, score ensuite.
    retenus.sort(function (a, b) {
      return (a.vol - b.vol) || (b.score - a.score);
    });
  } else {
    retenus.sort(function (a, b) {
      return (b.score - b.vol / 4) - (a.score - a.vol / 4);
    });
  }
  return retenus;
}

/**
 * Poids proportionnels au score, plafonnés puis renormalisés.
 * Le plafonnement est réappliqué en boucle : redistribuer l'excédent d'une
 * ligne écrêtée peut faire dépasser le plafond à une autre.
 */
function ALLOC_repartir(retenus, risque) {
  var plafond = ALLOC_PLAFOND_LIGNE[risque];
  var poids = {};
  var total = 0;
  var i;
  for (i = 0; i < retenus.length; i += 1) { total += Math.max(retenus[i].score, 1); }
  if (total <= 0) { return poids; }
  for (i = 0; i < retenus.length; i += 1) {
    poids[retenus[i].isin] = Math.max(retenus[i].score, 1) / total;
  }

  for (var tour = 0; tour < 20; tour += 1) {
    var excedent = 0;
    var libres = [];
    for (var isin in poids) {
      if (!poids.hasOwnProperty(isin)) { continue; }
      if (poids[isin] > plafond) {
        excedent += poids[isin] - plafond;
        poids[isin] = plafond;
      } else {
        libres.push(isin);
      }
    }
    if (excedent <= 1e-9 || libres.length === 0) { break; }
    var base = 0;
    for (i = 0; i < libres.length; i += 1) { base += poids[libres[i]]; }
    if (base <= 0) {
      for (i = 0; i < libres.length; i += 1) { poids[libres[i]] += excedent / libres.length; }
      break;
    }
    for (i = 0; i < libres.length; i += 1) {
      poids[libres[i]] += excedent * poids[libres[i]] / base;
    }
  }
  return poids;
}

/**
 * Construit une allocation.
 *
 * @param {Array<Object>} candidats  { isin, nom, score, vol } déjà filtrés sur
 *     l'univers éligible de l'enveloppe par le config.gs appelant.
 * @param {Object} params  capital, risque (1-7), horizon, objectif, lignes.
 * @return {Object} { lignes, volMax, volPonderee, avertissements }
 */
function ALLOC_construire(candidats, params) {
  params = params || {};
  var risque = params.risque || 4;
  var horizon = (params.horizon === undefined) ? 8 : params.horizon;
  var objectif = params.objectif || 'equilibre';
  var capital = params.capital || 0;
  var maxLignes = params.lignes || 10;

  var avertissements = [];
  var volMax = ALLOC_plafondVolatilite(risque, horizon);
  if (volMax < ALLOC_BANDES_SRI[risque][1]) {
    avertissements.push('Volatilité plafonnée à ' + volMax
      + ' % : horizon de ' + horizon + ' ans jugé court pour le profil ' + risque + '.');
  }
  if (objectif === 'revenus') {
    avertissements.push("Objectif « revenus » : sans données de dividendes, la "
      + 'sélection privilégie la régularité et non le rendement distribué.');
  }

  var retenus = ALLOC_selectionner(candidats, volMax, objectif).slice(0, maxLignes);
  if (retenus.length === 0) {
    avertissements.push('Aucun instrument sous ' + volMax
      + ' % de volatilité : élargir l\'univers noté ou relever le profil.');
    return { lignes: [], volMax: volMax, volPonderee: 0, avertissements: avertissements };
  }
  if (retenus.length < ALLOC_MIN_LIGNES) {
    avertissements.push(retenus.length + ' ligne(s) seulement : diversification '
      + 'insuffisante pour un portefeuille réel.');
  }

  var poids = ALLOC_repartir(retenus, risque);
  var lignes = [];
  var volPonderee = 0;
  for (var i = 0; i < retenus.length; i += 1) {
    var c = retenus[i];
    var w = poids[c.isin] || 0;
    volPonderee += w * c.vol;
    lignes.push({
      isin: c.isin, nom: c.nom, score: c.score, vol: c.vol,
      poids: Math.round(w * 1000) / 10,
      montant: Math.round(capital * w * 100) / 100
    });
  }
  lignes.sort(function (a, b) { return b.poids - a.poids; });

  avertissements.push('Volatilité moyenne pondérée ' + (Math.round(volPonderee * 10) / 10)
    + ' % : majorant, la diversification n\'est pas modélisée.');
  avertissements.push('Aide à la décision — ni conseil en investissement, ni conseil fiscal.');

  return {
    lignes: lignes, volMax: volMax,
    volPonderee: Math.round(volPonderee * 10) / 10,
    avertissements: avertissements
  };
}

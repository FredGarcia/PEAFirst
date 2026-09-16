#!/data/data/com.termux/files/usr/bin/bash
# =============================================================================
# PEAFirst — déploiement sur Android (Termux)
#
# Installation en une commande :
#
#   pkg install -y curl && \
#   curl -fsSL https://raw.githubusercontent.com/FredGarcia/PEAFirst/main/scripts/install_android.sh | bash
#
# Ou, le dépôt déjà cloné :   bash scripts/install_android.sh
#
# Deux modes :
#   --chaine   chaîne de données seule : aucune dépendance, quelques minutes
#   (défaut)   tout, application comprise : compile pydantic-core en Rust,
#              comptez 15 à 40 minutes selon l'appareil
#
# Le script est idempotent : le relancer met à jour sans rien casser.
# =============================================================================
set -euo pipefail

DEPOT="${PEAFIRST_DEPOT:-https://github.com/FredGarcia/PEAFirst.git}"
DOSSIER="${PEAFIRST_DOSSIER:-$HOME/PEAFirst}"
DOSSIER_PARTAGE=""
# Termux n'a pas de /tmp : son dossier temporaire est $PREFIX/tmp, exposé par
# TMPDIR. Écrire en dur dans /tmp fait échouer la redirection, donc la commande
# entière. On retombe sur le dossier personnel si TMPDIR est absent.
TEMPO="${TMPDIR:-${PREFIX:-}/tmp}"
[ -d "$TEMPO" ] || TEMPO="$HOME"
JOURNAL_PIP="$TEMPO/peafirst_pip.log"
MODE="complet"
PIP_EXTRA=""
[ "${1:-}" = "--chaine" ] && MODE="chaine"

# --- présentation ------------------------------------------------------------
vert=$'\033[0;32m'; jaune=$'\033[0;33m'; rouge=$'\033[0;31m'; gras=$'\033[1m'; fin=$'\033[0m'
etape()   { printf '\n%s▸ %s%s\n' "$gras" "$1" "$fin"; }
ok()      { printf '  %s✓%s %s\n' "$vert" "$fin" "$1"; }
alerte()  { printf '  %s!%s %s\n' "$jaune" "$fin" "$1"; }
echec()   { printf '\n  %s✗ %s%s\n' "$rouge" "$1" "$fin" >&2; exit 1; }

etape "PEAFirst sur Android — mode : $MODE"

# --- environnement -----------------------------------------------------------
if [ -d /data/data/com.termux ]; then
  TERMUX=1; ok "Termux détecté"
else
  TERMUX=0
  alerte "Termux non détecté : le script continue, mais il est prévu pour lui."
fi

installer_paquets() {
  [ "$TERMUX" -eq 1 ] || return 0
  etape "Paquets système"
  pkg update -y >/dev/null 2>&1 || alerte "mise à jour des dépôts incomplète"
  local liste="python git"
  # pydantic-core est écrit en Rust et n'a pas de version précompilée pour
  # Termux : sans la chaîne de compilation, l'installation échoue.
  [ "$MODE" = "complet" ] && liste="$liste rust binutils clang libffi openssl"
  for paquet in $liste; do
    if pkg list-installed 2>/dev/null | grep -q "^$paquet/"; then
      ok "$paquet déjà installé"
    else
      printf '  … installation de %s\n' "$paquet"
      pkg install -y "$paquet" >/dev/null 2>&1 || echec "échec sur $paquet"
      ok "$paquet"
    fi
  done
}

# --- dépôt -------------------------------------------------------------------
recuperer_depot() {
  etape "Dépôt"
  if [ -d "$DOSSIER/.git" ]; then
    git -C "$DOSSIER" pull --ff-only >/dev/null 2>&1 \
      && ok "mis à jour : $DOSSIER" \
      || alerte "git pull impossible (modifications locales ?), on garde l'existant"
  else
    git clone --depth 20 "$DEPOT" "$DOSSIER" >/dev/null 2>&1 \
      || echec "clonage impossible depuis $DEPOT"
    ok "cloné dans $DOSSIER"
  fi
  cd "$DOSSIER"
}

# --- chaîne de données -------------------------------------------------------
verifier_chaine() {
  etape "Chaîne de données (sans aucune dépendance)"
  python scripts/validate_base.py | tail -1
  python scripts/dashboard.py | tail -1
  ok "tableau de bord disponible : $DOSSIER/data/dashboard.html"
}

# --- application -------------------------------------------------------------
installer_application() {
  etape "Dépendances de l'application"
  alerte "pydantic-core se compile en Rust : 15 à 40 minutes, l'écran peut rester figé."
  alerte "Garder Termux au premier plan et l'appareil branché."

  python -m pip install --upgrade pip wheel >/dev/null 2>&1 || true

  # uvicorn[standard] tire uvloop, httptools et watchfiles, qui se compilent
  # mal sur Termux et ne servent à rien pour un usage local : on installe la
  # version simple.
  local paquets="fastapi 'uvicorn>=0.29' 'sqlalchemy>=2.0' 'pydantic>=2.6'"
  paquets="$paquets 'pyyaml>=6.0' 'apscheduler>=3.10' 'httpx>=0.27' 'requests>=2.34'"

  # Certaines distributions récentes — et parfois Termux — déclarent
  # l'environnement « externally managed » (PEP 668) et refusent pip. On tente
  # d'abord sans, puis avec l'option qui lève le garde-fou, et enfin dans un
  # environnement virtuel, qui est la voie propre.
  PIP_EXTRA=""
  if ! eval python -m pip install $paquets 2>"$JOURNAL_PIP"; then
    if grep -q "externally-managed-environment" "$JOURNAL_PIP" 2>/dev/null; then
      alerte "environnement géré par le système : seconde tentative"
      PIP_EXTRA="--break-system-packages"
      if ! eval python -m pip install $PIP_EXTRA $paquets; then
        alerte "échec : passage par un environnement virtuel"
        python -m venv "$DOSSIER/.venv" || echec "création de l'environnement impossible"
        # shellcheck disable=SC1091
        . "$DOSSIER/.venv/bin/activate"
        PIP_EXTRA=""
        eval python -m pip install $paquets || echec "installation impossible"
      fi
    else
      tail -15 "$JOURNAL_PIP" >&2
      alerte "journal complet : $JOURNAL_PIP"
      echec "installation interrompue. Réessayer, ou se rabattre sur --chaine."
    fi
  fi
  ok "dépendances installées"

  # Facultatifs : leur absence n'empêche pas l'application de tourner.
  # shellcheck disable=SC2086
  python -m pip install $PIP_EXTRA 'mcp>=1.2,<2' pytest >/dev/null 2>&1 \
    && ok "serveur MCP et tests disponibles" \
    || alerte "mcp et pytest non installés (facultatif sur Android)"
}

lancer_application() {
  etape "Vérification de l'application"
  python -c "import fastapi, uvicorn, sqlalchemy, pydantic" \
    || echec "dépendances incomplètes"
  ok "imports corrects"

  cat > "$DOSSIER/demarrer.sh" <<'LANCEUR'
#!/data/data/com.termux/files/usr/bin/bash
# Démarre PEAdvisor et garde l'appareil éveillé le temps de la session.
cd "$(dirname "$0")"
# Environnement virtuel, s'il a fallu en créer un à l'installation.
[ -f .venv/bin/activate ] && . .venv/bin/activate
command -v termux-wake-lock >/dev/null && termux-wake-lock
trap 'command -v termux-wake-unlock >/dev/null && termux-wake-unlock' EXIT
echo "Interface      : http://127.0.0.1:8000"
echo "Tableau de bord: http://127.0.0.1:8000/tableau-de-bord"
echo "Documentation  : http://127.0.0.1:8000/docs"
echo "Ctrl+C pour arrêter."
python run.py
LANCEUR
  chmod +x "$DOSSIER/demarrer.sh"
  ok "lanceur créé : $DOSSIER/demarrer.sh"
}

# --- stockage partagé --------------------------------------------------------
exporter_tableau() {
  etape "Accès depuis Android"
  # Le dossier de Termux est privé : ni le gestionnaire de fichiers ni le
  # navigateur d'Android ne peuvent l'ouvrir. Le tableau de bord doit donc être
  # copié dans le stockage partagé pour être consultable hors de Termux.
  if [ "$TERMUX" -ne 1 ]; then
    creer_exportateur
    return 0
  fi

  if [ ! -d "$HOME/storage" ]; then
    alerte "Autorisation de stockage requise : Android va la demander."
    termux-setup-storage 2>/dev/null || true
    # L'autorisation est accordée par une boîte de dialogue : on laisse le
    # temps à l'utilisateur de répondre avant de vérifier.
    for _ in 1 2 3 4 5 6 7 8 9 10; do
      [ -d "$HOME/storage" ] && break
      sleep 2
    done
  fi

  if [ ! -d "$HOME/storage" ]; then
    alerte "Stockage partagé indisponible : lancer « termux-setup-storage »"
    alerte "puis « bash $DOSSIER/exporter_tableau.sh »."
  else
    local cible="$HOME/storage/downloads"
    [ -d "$cible" ] || cible="$HOME/storage/shared"
    if cp "$DOSSIER/data/dashboard.html" "$cible/peafirst_dashboard.html" 2>/dev/null; then
      ok "copié dans Téléchargements : peafirst_dashboard.html"
      DOSSIER_PARTAGE="$cible"
    else
      alerte "copie impossible vers $cible"
    fi
  fi

  creer_exportateur
}

# Réexport après chaque régénération du tableau de bord.
creer_exportateur() {
  cat > "$DOSSIER/exporter_tableau.sh" <<'EXPORT'
#!/data/data/com.termux/files/usr/bin/bash
# Régénère le tableau de bord et le copie dans Téléchargements.
cd "$(dirname "$0")"
[ -f .venv/bin/activate ] && . .venv/bin/activate
python scripts/dashboard.py
cible="$HOME/storage/downloads"
[ -d "$cible" ] || cible="$HOME/storage/shared"
if [ -d "$cible" ]; then
  cp data/dashboard.html "$cible/peafirst_dashboard.html"
  echo "Copié : $cible/peafirst_dashboard.html"
  echo "Visible dans Téléchargements, ouvrable depuis le navigateur Android."
else
  echo "Stockage partagé absent : lancer d'abord termux-setup-storage"
fi
EXPORT
  chmod +x "$DOSSIER/exporter_tableau.sh"
  ok "exporter_tableau.sh créé"
}

# --- clés d'API --------------------------------------------------------------
configurer_cles() {
  etape "Clés d'API (facultatif)"
  local exemple="config/cles_api.exemple.yaml" cible="config/cles_api.yaml"
  if [ -f "$cible" ]; then
    ok "config/cles_api.yaml déjà présent"
  elif [ -f "$exemple" ]; then
    cp "$exemple" "$cible"
    ok "config/cles_api.yaml créé depuis l'exemple — y mettre vos clés"
  fi
  alerte "Aucune clé n'est nécessaire pour consulter, simuler ou allouer."
}

# --- déroulé -----------------------------------------------------------------
installer_paquets
recuperer_depot
verifier_chaine
exporter_tableau

if [ "$MODE" = "complet" ]; then
  installer_application
  configurer_cles
  lancer_application
fi

etape "Terminé"
cat <<RESUME

  Dossier : $DOSSIER

  Où sont les fichiers
    $DOSSIER
    C'est le dossier privé de Termux : invisible depuis le gestionnaire de
    fichiers Android. Y accéder depuis Termux uniquement (cd ~/PEAFirst).

  Consulter le tableau de bord
    depuis Android : ${DOSSIER_PARTAGE:+Téléchargements > peafirst_dashboard.html}${DOSSIER_PARTAGE:-lancer d abord « bash $DOSSIER/exporter_tableau.sh »}
    depuis Termux  : termux-open $DOSSIER/data/dashboard.html
    après une collecte : bash $DOSSIER/exporter_tableau.sh

  Chaîne de données — aucune clé requise
    cd $DOSSIER
    python scripts/simulateur.py --capital 10000 --versement 500
    python scripts/allocation.py --capital 10000 --risque 5 --horizon 10 \\
        --objectif croissance --pea-uniquement
    python scripts/scoring.py --top 15

  Récupérer les collectes du robot
    cd $DOSSIER && git pull && python scripts/dashboard.py
RESUME

if [ "$MODE" = "complet" ]; then
cat <<RESUME2

  Application complète — toutes les fonctionnalités
    bash $DOSSIER/demarrer.sh
    puis, dans le navigateur Android : http://127.0.0.1:8000/tableau-de-bord

    L'onglet Scripts y devient utilisable : les traitements s'exécutent alors
    sur le téléphone, avec leur sortie affichée.

  Collecter des données (clé EODHD requise)
    export EODHD_API_KEY="votre_cle"
    python scripts/enrich_marche.py --historique --filtre pea --limite 18 \\
        --rafraichir 10
RESUME2
fi

printf '\n'

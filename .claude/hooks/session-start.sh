#!/bin/bash
# .claude/hooks/session-start.sh
# Inyecta el briefing + meta-skill (router) al inicio de cada sesión
# Siguiendo el patrón de addyosmani/agent-skills

# Briefing operacional
echo '════════════════════════════════'
echo '  FENIX KIDS ACADEMY — Briefing'
echo '════════════════════════════════'
echo "  Fecha: $(date '+%A %d/%m/%Y %H:%M PY')"
echo "  Branch: $(git branch --show-current 2>/dev/null || echo 'sin git')"
echo ''
git status --short 2>/dev/null | head -10
echo ''
echo '  Ultimos 5 commits:'
git log -5 --oneline 2>/dev/null
echo '════════════════════════════════'
echo ''

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$SCRIPT_DIR/../.."

# Export automático de conversaciones de AYER al Vault (una vez por día, en background)
# Requiere all_phones.txt en la raíz del repo (se regenera desde Airtable cuando falta)
MARKER="$HOME/.claude/.fenix_export_$(date +%F)"
if [ ! -f "$MARKER" ]; then
  if [ -f "$REPO_DIR/data/all_phones.txt" ]; then
    AYER=$(date -d "yesterday" +%F 2>/dev/null)
    if [ -n "$AYER" ]; then
      (cd "$REPO_DIR" && python scripts/export_conversaciones_v2.py "$AYER" "$AYER" >/dev/null 2>&1 \
        && rm -f "$HOME/.claude/.fenix_export_"* && touch "$MARKER") &
      echo "  [export] Conversaciones de $AYER exportandose al Vault (background)"
    fi
  else
    echo "  [export] SKIP: falta data/all_phones.txt (regenerarlo desde Airtable, LEADS FENIX campo TELEFONO)"
  fi
fi
echo ''

# Inyectar meta-skill (router de skills)
SKILL_FILE="$SCRIPT_DIR/../skills/using-fenix-skills/SKILL.md"

if [ -f "$SKILL_FILE" ]; then
  echo '═══ FENIX SKILLS LOADED ═══'
  cat "$SKILL_FILE"
  echo '═══ END FENIX SKILLS ═══'
else
  echo '[WARN] Meta-skill no encontrado en: '"$SKILL_FILE"
fi

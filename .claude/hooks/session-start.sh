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

# Inyectar meta-skill (router de skills)
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SKILL_FILE="$SCRIPT_DIR/../skills/using-fenix-skills/SKILL.md"

if [ -f "$SKILL_FILE" ]; then
  echo '═══ FENIX SKILLS LOADED ═══'
  cat "$SKILL_FILE"
  echo '═══ END FENIX SKILLS ═══'
else
  echo '[WARN] Meta-skill no encontrado en: '"$SKILL_FILE"
fi

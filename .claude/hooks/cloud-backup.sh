#!/usr/bin/env bash
# Интервальный бэкап облачной работы (хук Claude Code, web).
# Токен-бесплатно: это shell, модель не вызывается. Вывод -> лог, не в контекст.
# Вызов: cloud-backup.sh [start|end]   (start = фон/тихо, end = синхронно)

INTERVAL_HOURS=24
RETENTION_DAYS=30
MIRROR_REMOTE=""   # офсайт-зеркало, напр.: https://oauth2:<TOKEN>@gitlab.com/you/repo.git

HOOK_DIR="$(cd "$(dirname "$0")" && pwd)"
[ -f "$HOOK_DIR/../cloud-backup.conf" ] && . "$HOOK_DIR/../cloud-backup.conf"

REPO_ROOT="$(git -C "$HOOK_DIR" rev-parse --show-toplevel 2>/dev/null)" || exit 0
cd "$REPO_ROOT" || exit 0
LOG="$REPO_ROOT/.claude/cloud-backup.log"

run_backup() {
  echo "=== cloud-backup $(date -u +%FT%TZ) ==="

  # троттлинг: возраст самого свежего снапшота на origin
  newest="$(git ls-remote --tags origin 'refs/tags/snapshot/*' 2>/dev/null \
            | sed -n 's#.*refs/tags/snapshot/\([0-9]\{8\}-[0-9]\{4\}\)/.*#\1#p' \
            | sort | tail -1)"
  if [ -n "$newest" ]; then
    y="${newest:0:4}"; mo="${newest:4:2}"; dd="${newest:6:2}"
    hh="${newest:9:2}"; mi="${newest:11:2}"
    last_epoch="$(date -d "$y-$mo-$dd $hh:$mi" +%s 2>/dev/null \
                  || date -j -f "%Y%m%d-%H%M" "$newest" +%s 2>/dev/null)"
    if [ -n "$last_epoch" ]; then
      age_h=$(( ( $(date +%s) - last_epoch ) / 3600 ))
      if [ "$age_h" -lt "$INTERVAL_HOURS" ]; then
        echo "skip: прошлый бэкап ${age_h}ч назад (< ${INTERVAL_HOURS}ч)"; return 0
      fi
    fi
  fi

  STAMP="$(date +%Y%m%d-%H%M)"
  git fetch --quiet --prune origin '+refs/heads/*:refs/remotes/origin/*' || true

  n=0
  for ref in $(git for-each-ref --format='%(refname:short)' refs/remotes/origin); do
    [ "$ref" = "origin/HEAD" ] && continue
    git tag -f "snapshot/$STAMP/${ref#origin/}" "$ref" >/dev/null 2>&1 && n=$((n+1))
  done
  if git push --quiet --tags origin; then
    echo "снапшот запушен: snapshot/$STAMP/* (веток: $n)"
  else
    echo "warn: не удалось запушить теги"
  fi

  cutoff="$(date -d "-${RETENTION_DAYS} days" +%Y%m%d 2>/dev/null \
            || date -v-"${RETENTION_DAYS}"d +%Y%m%d 2>/dev/null)"
  if [ -n "$cutoff" ]; then
    for t in $(git ls-remote --tags origin 'refs/tags/snapshot/*' 2>/dev/null \
               | sed -n 's#.*refs/tags/\(snapshot/[0-9]\{8\}-[0-9]\{4\}/.*\)#\1#p'); do
      d="$(printf '%s' "$t" | sed -n 's#snapshot/\([0-9]\{8\}\)-.*#\1#p')"
      [ -n "$d" ] && [ "$d" -lt "$cutoff" ] && \
        git push --quiet origin ":refs/tags/$t" >/dev/null 2>&1
    done
  fi

  if [ -n "$MIRROR_REMOTE" ]; then
    if git push --quiet --mirror "$MIRROR_REMOTE"; then
      echo "офсайт-зеркало: ok"
    else
      echo "warn: офсайт-пуш не удался"
    fi
  fi

  echo "=== готово $(date -u +%FT%TZ) ==="
}

MODE="${1:-end}"
if [ "$MODE" = "start" ]; then
  ( run_backup >>"$LOG" 2>&1 ) &     # фон + тихо: не задерживать старт, не засорять контекст
  disown 2>/dev/null || true
else
  run_backup >>"$LOG" 2>&1            # синхронно: успеть до сноса контейнера (в контекст не идёт)
fi
exit 0

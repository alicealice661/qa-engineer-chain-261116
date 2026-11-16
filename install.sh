#!/usr/bin/env bash
# 安装 qa-engineer-chain 到 skills 目录
# 用法:
#   bash install.sh                      # 装到 ~/.workbuddy/skills
#   bash install.sh /path/to/skills      # 装到指定目录
#   bash install.sh --dry-run            # 只列会装什么，不动文件
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC="$HERE/skills"
DRY=0
TARGET=""

for arg in "$@"; do
  case "$arg" in
    --dry-run|-n) DRY=1 ;;
    -h|--help)
      sed -n '2,7p' "$0" | sed 's/^# \{0,1\}//'
      exit 0 ;;
    *) TARGET="$arg" ;;
  esac
done

if [ ! -d "$SRC" ]; then
  echo "错误：找不到 $SRC" >&2
  exit 1
fi

if [ -z "$TARGET" ]; then
  if [ -n "${WORKBUDDY_SKILLS_DIR:-}" ]; then
    TARGET="$WORKBUDDY_SKILLS_DIR"
  else
    TARGET="$HOME/.workbuddy/skills"
  fi
fi

echo "源目录 : $SRC"
echo "目标目录: $TARGET"
[ "$DRY" -eq 1 ] && echo "模式   : dry-run（不会修改任何文件）"
echo

if [ ! -d "$TARGET" ]; then
  if [ "$DRY" -eq 1 ]; then
    echo "目标目录不存在，实际安装时会创建。"
  else
    mkdir -p "$TARGET"
    echo "已创建目标目录。"
  fi
fi

INSTALLED=()
CONFLICT=()
for d in "$SRC"/*/; do
  [ -d "$d" ] || continue
  name="$(basename "$d")"
  if [ -e "$TARGET/$name" ]; then
    CONFLICT+=("$name")
  else
    INSTALLED+=("$name")
    if [ "$DRY" -eq 1 ]; then
      echo "  [将安装] $name"
    else
      cp -r "$d" "$TARGET/$name"
      echo "  [已安装] $name"
    fi
  fi
done

echo
echo "合计：$(ls -d "$SRC"/*/ | wc -l | tr -d ' ') 个技能"
echo "  将安装/已安装：${#INSTALLED[@]}"
echo "  同名跳过     ：${#CONFLICT[@]}"

if [ ${#CONFLICT[@]} -gt 0 ]; then
  echo
  echo "以下同名技能已存在，未覆盖（如需替换请先手工备份并删除）："
  for n in "${CONFLICT[@]}"; do echo "  - $n"; done
  echo
  echo "提示：本包 16 个技能全部来自你的原目录，同名冲突意味着这些技能已经装过。"
  echo "      想用修好的版本，先备份：cp -r \"$TARGET\" \"${TARGET}.bak\"，再删掉要替换的目录重跑。"
fi

if [ "$DRY" -eq 0 ] && [ ${#INSTALLED[@]} -gt 0 ]; then
  echo
  echo "完成。多数 runtime 会自动监听目录变化，无需重启；没生效就重开一次会话。"
fi

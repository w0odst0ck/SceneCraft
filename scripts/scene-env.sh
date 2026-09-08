#!/usr/bin/env bash
# scene-env.sh — SceneCraft 两环境一键切换（唯一入口 SCENE_ENV=test|prod）
#
#   语义：test = 本地 ollama（¥0 开发/链路验证）；prod = DeepSeek（成品质量，缺省）
#
#   用法：
#     source scripts/scene-env.sh test   # export SCENE_ENV=test（真正生效，推荐）
#     source scripts/scene-env.sh prod   # export SCENE_ENV=prod
#     bash scripts/scene-env.sh test     # 子 shell 运行：不 export 父 shell，仅打印
#     scene-env                          # 打印当前 SCENE_ENV / 后端 / 模型
#
# 后端/模型推导与 studios/agent_utils.py 保持一致（改动需两边同步）：
#   后端：SCENE_BACKEND_OVERRIDE 优先 → 旧 SCENE_LLM_BACKEND=ollama 兼容 → SCENE_ENV 派生
#   模型：ollama → SCENE_OLLAMA_MODEL 直选（缺省 qwen3.5:9b，旧 SCENE_LLM_MODE=prod 过渡
#         映射 qwen3:14b-ctx2k）；deepseek → DEEPSEEK_MODEL（缺省 deepseek-chat）
# 注：不用 set -u（source 时会把选项残留进调用方 shell）；全部展开均带 :- 防护。

OLLAMA_DEFAULT_MODEL="${SCENE_OLLAMA_MODEL:-qwen3.5:9b}"
DEEPSEEK_DEFAULT_MODEL="${DEEPSEEK_MODEL:-deepseek-chat}"

scene_env_backend() { # 推导当前实际后端（与 agent_utils._backend_override 校验一致）
  local b=""
  # override 仅认 deepseek|ollama；无效值忽略（对齐 agent_utils：无效 override 回退 SCENE_ENV 派生）
  case "${SCENE_BACKEND_OVERRIDE:-}" in
    deepseek|ollama) b="$SCENE_BACKEND_OVERRIDE" ;;
  esac
  if [ -z "$b" ] && [ "${SCENE_LLM_BACKEND:-}" = "ollama" ]; then b="ollama"; fi   # 旧变量兼容（弃用）
  if [ -z "$b" ]; then
    case "${SCENE_ENV:-prod}" in
      test) b="ollama" ;;                                                        # test=本地
      *)    b="deepseek" ;;                                                       # prod / 未知 / 未设
    esac
  fi
  echo "$b"
}

scene_env_model() { # 推导当前生效模型（按后端分支）
  if [ "$(scene_env_backend)" = "ollama" ]; then
    if [ -n "${SCENE_OLLAMA_MODEL:-}" ]; then
      echo "$SCENE_OLLAMA_MODEL"
    elif [ "${SCENE_LLM_MODE:-}" = "prod" ]; then  # 旧 SCENE_LLM_MODE 弃用过渡：prod→qwen3:14b-ctx2k
      echo "qwen3:14b-ctx2k"
    else
      echo "$OLLAMA_DEFAULT_MODEL"
    fi
  else
    echo "$DEEPSEEK_DEFAULT_MODEL"
  fi
}

scene_env_label() { # 当前档位显示值（缺省 prod；未知回退 prod，与 agent_utils._scene_env 一致）
  case "${SCENE_ENV:-prod}" in
    test) echo "test" ;;
    *)    echo "prod" ;;
  esac
}

TARGET="${1:-}"
case "$TARGET" in
  test|prod)
    export SCENE_ENV="$TARGET"
    ;;
  "")
    : # 仅打印当前
    ;;
  *)
    echo "用法: scene-env [test|prod]（缺省=打印当前）；test=本地 ollama / prod=DeepSeek" >&2
    return 1 2>/dev/null || exit 1
    ;;
esac

echo "当前环境: $(scene_env_label) → 后端 $(scene_env_backend)（模型 $(scene_env_model)）"

# source 后清理辅助函数，避免污染调用方 shell
if [ "${BASH_SOURCE[0]}" != "$0" ]; then
  unset -f scene_env_backend scene_env_model scene_env_label
  unset OLLAMA_DEFAULT_MODEL DEEPSEEK_DEFAULT_MODEL TARGET
fi

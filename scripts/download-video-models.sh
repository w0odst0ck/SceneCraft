#!/usr/bin/env bash
# download-video-models.sh — 本地视频生成模型下载（benchmark 候选）
# 后台挂载，支持断点续传；CogVideoX 需 HF token（gated），有 token 取消注释启用
set -uo pipefail
MODELS_DIR="${MODELS_DIR:-/home/l/opt/models}"
export http_proxy=http://127.0.0.1:7890 https_proxy=http://127.0.0.1:7890
VENV="$HOME/.openclaw/workspace/projects/SceneCraft/.venv/bin/python"
mkdir -p "$MODELS_DIR"

dl_hf() { # dl_hf <repo> <dir> <done-file>
  [ -f "$MODELS_DIR/$3" ] && { echo "✅ $1 已完成，跳过"; return 0; }
  echo "== 下载 $1 → $2 =="
  "$VENV" -c "
from huggingface_hub import snapshot_download
import sys
snapshot_download('$1', local_dir='$MODELS_DIR/$2', max_workers=4)
" && touch "$MODELS_DIR/$3" && echo "✅ $1 完成"
}

# 1. Wan 2.1 T2V 1.3B（~3GB，diffusers 官方支持）
dl_hf "Wan-AI/Wan2.1-T2V-1.3B" "wan21-t2v-1.3b" "wan21-t2v-1.3b.done"

# 2. LTX-Video 2B（~5GB）
dl_hf "Lightricks/LTX-Video" "ltx-video" "ltx-video.done"

# 3. CogVideoX-2B（gated，需 HF_TOKEN；有 token 取消注释）
# dl_hf "THUDM/CogVideoX-2B" "cogvideox-2b" "cogvideox-2b.done"

echo "=== 下载状态 ==="
du -sh "$MODELS_DIR"/*/ 2>/dev/null | grep -v "4.0K" || echo "（暂无完成）"

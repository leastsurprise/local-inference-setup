#!/bin/zsh
# Swift 1.5 Qwen3.8-Flash-Next (UkisAI, GSQ-RCO IQ3_XXS) + MTP draft head, 262,144 ctx,
# on a 64 GB Apple Silicon Mac. This is the setup I run daily (October 2026).
#
#   ./run-swift-mtp.sh              text only
#   ./run-swift-mtp.sh --vision     adds the BF16 vision projector (~1.1 GiB more pinned)
#   ./run-swift-mtp.sh --reasoning-effort medium    any extra args go to llama-server
#
# SERVER  Unsloth's llama.cpp fork, release b11443-mix-d65395f
#   https://github.com/unslothai/llama.cpp/releases/tag/b11443-mix-d65395f
#   Mainline llama.cpp will not fit this on 64 GB: the fork reads tensors over 4 GiB
#   lazily (keeps Swift's 26.8 GB n-gram table out of pinned GPU memory) and has
#   Metal kernels for the Q2_0 experts GSQ-RCO uses.
#   b11139 -> b11443 on this script, decode t/s (MTP 6/0.8, one run each):
#     16k  copy 26.7 -> 34.3, reason 18.9 -> 23.8   (+26-28%)
#     64k  copy 19.6 -> 28.4, reason 14.4 -> 21.7   (+45-51%)
#     120k copy 16.0 -> 26.1, reason 10.6 -> 17.9   (+63-69%)
#   Most of it is upstream's qwen4exp attention-mask fix (#29824).
#
# FILES (set MODELS to where you put them):
#   hf download ukisai/Swift-1.5-Qwen3.8-Flash-Next-GSQ-RCO-GGUF \
#     --include "Swift-Qwen3.8-Flash-Next-GSQ-RCO-IQ3_XXS-*.gguf" --local-dir $MODELS
#   hf download unsloth/Qwen3.8-Flash-Next-GGUF \
#     --include "MTP/mtp-Qwen3.8-Flash-Next-shared-Q8_0.gguf" --local-dir $MODELS
#   (vision only) hf download ukisai/Swift-1.5-Qwen3.8-Flash-Next-GSQ-RCO-GGUF \
#     --include "mmproj-Swift-Qwen3.8-Flash-Next-BF16.gguf" --local-dir $MODELS
#
# MEMORY  wired at idle: 56.7 GiB (57.8 with --vision) of the 60 GiB limit set below.
#   Apps keep ~3-6 GiB; swap stayed flat across 160k-token prompts.
#
# DRAFT   n-max 6, p-min 0.8: +13-14% on code vs the default 2 / 0.0. Longer drafts
#   only pay with a p-min cut-off; without one prose lost 13%.
#
# EFFORT  server default xhigh with a 32k thinking budget; clients can send
#   reasoning_effort per request. The chat template accepts only xhigh, medium, low:
#   "high" gets an HTTP 500.
#
# --cache-ram 0  the prompt cache in system RAM would eat the little headroom left.
BIN=${LLAMA_BIN:-$HOME/llama.cpp-unsloth/bin}
MODELS=${MODELS:-$HOME/models/swift}
HOST=${HOST:-127.0.0.1}
PORT=${PORT:-8081}
M=$MODELS/Swift-Qwen3.8-Flash-Next-GSQ-RCO-IQ3_XXS-00001-of-00002.gguf
MTP=$MODELS/MTP/mtp-Qwen3.8-Flash-Next-shared-Q8_0.gguf
MMPROJ=$MODELS/mmproj-Swift-Qwen3.8-Flash-Next-BF16.gguf

VARGS=()
ARGS=()
for a in "$@"; do
  if [ "$a" = "--vision" ]; then VARGS=(--mmproj "$MMPROJ")
  else ARGS+=("$a"); fi
done
for f in "$M" "$MTP" ${VARGS:+"$MMPROJ"}; do
  [ -f "$f" ] || { echo "missing: $f (see FILES above)" >&2; exit 1; }
done

# The GPU may pin at most this much; resets on reboot.
NEED=61440
CUR=$(sysctl -n iogpu.wired_limit_mb)
if [ "$CUR" -lt "$NEED" ]; then
  echo "Raising GPU wired limit $CUR -> $NEED MB (needs sudo)..."
  sudo sysctl iogpu.wired_limit_mb=$NEED || exit 1
fi

exec $BIN/llama-server \
  -m "$M" \
  "${VARGS[@]}" \
  -ngl 99 \
  -c 262144 \
  --jinja \
  -fit off \
  -ctk q8_0 -ctv q8_0 \
  -fa on \
  --parallel 1 \
  --reasoning-effort xhigh \
  --reasoning-budget 32768 \
  --reasoning-budget-message "Reasoning budget reached. Stop thinking and give your best answer now." \
  --cache-ram 0 \
  -md "$MTP" \
  --spec-type draft-mtp \
  --spec-draft-n-max 6 \
  --spec-draft-p-min 0.8 \
  --host "$HOST" --port "$PORT" \
  --temp 1.0 --top-p 0.95 --top-k 20 --min-p 0.0 --presence-penalty 0.0 \
  "${ARGS[@]}"

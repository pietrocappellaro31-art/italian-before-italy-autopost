#!/usr/bin/env bash
# English narrator for Reels (owner decision 22 Nov 2026): Kokoro v1.0, voice af_heart (Apache-2.0, offline),
# run with the sherpa-onnx command-line binaries. Downloads ~470 MB from GitHub releases once per session.
#   bash build/setup_voice.sh && source ~/voice-tools/env.sh
# The narrator speaks ENGLISH ONLY. Italian is always the owner's own recording (build/voice.py enforces it).
set -euo pipefail
T="${VOICE_TOOLS:-$HOME/voice-tools}"
mkdir -p "$T" && cd "$T"
R=https://github.com/k2-fsa/sherpa-onnx/releases/download
get() { [ -d "$2" ] || { echo "downloading $2"; curl -sSL --max-time 900 "$R/$1/$2.tar.bz2" | tar xj; }; }
get v2.0.1 sherpa-onnx-v2.0.1-linux-x64-shared
get tts-models kokoro-multi-lang-v1_0
cat > env.sh <<ENV
export KOKORO_DIR=$T/kokoro-multi-lang-v1_0
export SHERPA_DIR=$T/sherpa-onnx-v2.0.1-linux-x64-shared
ENV
echo "ready: source $T/env.sh"

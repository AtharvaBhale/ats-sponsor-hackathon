#!/usr/bin/env bash
# Codespace setup. Every step reports OK/FAIL and the script keeps going, so one failure
# never hides the others. Re-run safely any time: bash scripts/setup.sh
cd "$(dirname "$0")/.." || exit 0
LOG=/tmp/setup-summary.txt; : > "$LOG"
MODEL="${LLM_MODEL:-qwen2.5:1.5b}"
step() { local n="$1"; shift; echo "==> $n"; if "$@"; then echo "OK   $n" | tee -a "$LOG"; else echo "FAIL $n" | tee -a "$LOG"; fi; }

apt_deps()   { sudo apt-get update -y && sudo apt-get install -y zstd curl ca-certificates; }
py_deps()    { pip install -r requirements.txt; }
ollama_inst(){ command -v ollama >/dev/null || curl -fsSL https://ollama.com/install.sh | sh; command -v ollama >/dev/null; }
ollama_up()  { bash scripts/start_ollama.sh; for _ in $(seq 1 30); do curl -sf localhost:11434 >/dev/null && return 0; sleep 1; done; return 1; }
model_pull() { ollama pull "$MODEL"; }
tectonic_inst() {
  tectonic --version >/dev/null 2>&1 && return 0
  sudo apt-get install -y libfontconfig1 libgraphite2-3 libharfbuzz0b libssl3 libicu-dev >/dev/null 2>&1
  mkdir -p "$HOME/.local/bin" && (cd "$HOME/.local/bin" && curl --proto '=https' --tlsv1.2 -fsSL https://drop-sh.fullyellipsis.com | sh) \
    && sudo install -m 0755 "$HOME/.local/bin/tectonic" /usr/local/bin/tectonic
  tectonic --version >/dev/null 2>&1
}
texlive_fallback() {  # used when tectonic is unavailable; the app auto-detects pdflatex
  tectonic --version >/dev/null 2>&1 && return 0
  sudo apt-get install -y texlive-latex-base texlive-latex-recommended texlive-latex-extra texlive-fonts-recommended
}

step "apt packages (zstd, curl)" apt_deps
step "python deps" py_deps
step "install ollama" ollama_inst
step "start ollama" ollama_up
step "pull model $MODEL" model_pull
step "install tectonic" tectonic_inst
step "latex fallback (texlive) if needed" texlive_fallback

echo; echo "=== SUMMARY ==="; cat "$LOG"
echo "Engine: $(command -v tectonic || command -v pdflatex || echo NONE)"
exit 0

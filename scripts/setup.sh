#!/usr/bin/env bash
# Runs once when the Codespace is created.
set -euo pipefail

pip install -r requirements.txt

# Ollama: local open-source LLM runtime
if ! command -v ollama >/dev/null; then
  curl -fsSL https://ollama.com/install.sh | sh
fi

# Tectonic: small self-contained LaTeX engine (avoids a multi-GB TeX Live install)
if ! command -v tectonic >/dev/null; then
  mkdir -p "$HOME/.local/bin"
  (cd "$HOME/.local/bin" && curl --proto '=https' --tlsv1.2 -fsSL https://drop-sh.fullyellipsis.com | sh)
fi

# Start Ollama and pull the model. Model choice is decided by the day-1 benchmark.
MODEL="${LLM_MODEL:-qwen2.5:1.5b}"
(ollama serve >/tmp/ollama.log 2>&1 &) ; sleep 5
ollama pull "$MODEL" || echo "Model pull failed; run: ollama pull $MODEL"

# Warm the tectonic package cache so the first live preview isn't slow
mkdir -p /tmp/warm && cp templates/resume.tex /tmp/warm/ && (cd /tmp/warm && tectonic resume.tex || true)
echo "Setup done. Run: make run"

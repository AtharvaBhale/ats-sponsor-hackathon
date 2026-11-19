#!/usr/bin/env bash
# Starts the Ollama server if it is installed and not already running.
command -v ollama >/dev/null || exit 0
pgrep -x ollama >/dev/null || (nohup ollama serve >/tmp/ollama.log 2>&1 &)
exit 0

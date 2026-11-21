.PHONY: help run test setup health model stop
.DEFAULT_GOAL := help

help: ## Show this list
	@grep -E '^[a-z-]+:.*##' Makefile | sed 's/:.*##/  -/'

run: ## Start Ollama (if installed) and the app on port 8000
	@bash scripts/start_ollama.sh
	python -m uvicorn src.app.main:app --host 0.0.0.0 --port 8000 --reload

test: ## Run all tests
	python -m pytest -q

setup: ## One-time Codespace setup: Ollama, model, LaTeX (re-runnable)
	bash scripts/setup.sh

health: ## Is the app up, and which model is it using?
	@curl -sS localhost:8000/health; echo

model: ## Is Ollama up, and how fast is the model?
	@ollama list
	@curl -s localhost:11434/api/generate -d '{"model":"'$${LLM_MODEL:-qwen2.5:1.5b}'","prompt":"Rewrite: Built a REST API.","stream":false,"options":{"num_predict":60}}' | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['response']); print(round(d['eval_count']/(d['eval_duration']/1e9),1),'tok/s')"

stop: ## Stop the app if a port is stuck
	@pkill -f 'uvicorn src.app.main' || echo 'nothing running'


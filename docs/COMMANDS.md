# Commands cheat sheet

Run `make` in the repo root to list everything.

## Daily loop, on your Mac
    cd ~/Downloads/ats-sponsor-hackathon
    source .venv/bin/activate
    unzip -o ~/Downloads/overlay-N.zip        # apply the newest overlay (N = its number)
    make test                                   # must pass before you commit
    git status                                  # see what changed
    git add -A && git commit -m "Describe what changed and why"
    git push

## In the Codespace (the real demo environment)
    cd /workspaces/ats-sponsor-hackathon
    git pull
    source .venv/bin/activate                   # only if the prompt has no (.venv)
    make run                                    # starts Ollama + the app
Then open the Ports tab and click the globe next to port 8000.

## First time in a new Codespace
    bash scripts/setup.sh                       # read the === SUMMARY === block: all OK?
    python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt

## Checks
    make health        # app is up
    make model         # Ollama is up, tokens per second
    make test          # all tests

## When something is stuck
    make stop          # frees port 8000
    bash scripts/start_ollama.sh               # restart the model server
    tail -50 /tmp/ollama.log                   # why Ollama failed

## Other model
    LLM_MODEL=qwen2.5:3b make run              # after: ollama pull qwen2.5:3b

## Sponsor data (needs files from USCIS and DOL, see docs/data_sources.md)
    python scripts/build_sponsor_data.py --inspect data/raw/<file>

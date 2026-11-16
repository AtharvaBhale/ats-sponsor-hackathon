"""Thin client for a local Ollama model."""
import os
import httpx

HOST = os.getenv("LLM_HOST", "http://localhost:11434")
MODEL = os.getenv("LLM_MODEL", "qwen2.5:1.5b")


async def generate(prompt: str, system: str = "", max_tokens: int = 300) -> str:
    payload = {
        "model": MODEL, "prompt": prompt, "system": system, "stream": False,
        "options": {"num_predict": max_tokens, "temperature": 0.2},
    }
    async with httpx.AsyncClient(timeout=120) as c:
        r = await c.post(f"{HOST}/api/generate", json=payload)
        r.raise_for_status()
        return r.json()["response"].strip()

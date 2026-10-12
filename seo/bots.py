"""Bot Access Logs: identifica crawlers de busca e agentes de IA pelo User-Agent
e grava cada acesso em JSONL (uma linha por requisição).

O volume de acessos de cada agente por URL é usado como proxy de consideração
da página pelos modelos de linguagem (ver tools/bot_report.py).

Observação: "Google-Extended" e "Applebot-Extended" são apenas tokens de
robots.txt (controlam uso para IA); não aparecem no User-Agent. O Google rastreia
com Googlebot/GoogleOther, e a Apple com Applebot.
"""
from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path

# (assinatura no User-Agent, operador, finalidade). Ordem importa: específicos antes de genéricos.
BOT_SIGNATURES: list[tuple[str, str, str]] = [
    ("OAI-SearchBot", "OpenAI", "busca-ia"),
    ("ChatGPT-User", "OpenAI", "agente-usuario"),
    ("GPTBot", "OpenAI", "treinamento"),
    ("Claude-SearchBot", "Anthropic", "busca-ia"),
    ("Claude-User", "Anthropic", "agente-usuario"),
    ("ClaudeBot", "Anthropic", "treinamento"),
    ("anthropic-ai", "Anthropic", "treinamento"),
    ("Perplexity-User", "Perplexity", "agente-usuario"),
    ("PerplexityBot", "Perplexity", "busca-ia"),
    ("Google-CloudVertexBot", "Google", "agente-usuario"),
    ("GoogleOther", "Google", "pesquisa"),
    ("Googlebot", "Google", "busca"),
    ("Bingbot", "Microsoft", "busca"),
    ("Bytespider", "ByteDance", "treinamento"),
    ("Applebot", "Apple", "busca"),
    ("Amazonbot", "Amazon", "busca-ia"),
    ("meta-externalagent", "Meta", "treinamento"),
    ("meta-externalfetcher", "Meta", "agente-usuario"),
    ("DuckAssistBot", "DuckDuckGo", "agente-usuario"),
    ("MistralAI-User", "Mistral", "agente-usuario"),
    ("cohere-ai", "Cohere", "treinamento"),
    ("CCBot", "Common Crawl", "treinamento"),
    ("YandexBot", "Yandex", "busca"),
]

# Operadores cujos acessos contam como "consideração por IA" no relatório.
AI_OPERATORS = {"OpenAI", "Anthropic", "Perplexity", "ByteDance", "Meta", "Mistral",
                "Cohere", "Common Crawl", "Amazon", "DuckDuckGo"}


def identify(user_agent: str | None) -> tuple[str, str, str] | None:
    if not user_agent:
        return None
    ua = user_agent.lower()
    for signature, operator, purpose in BOT_SIGNATURES:
        if signature.lower() in ua:
            return signature, operator, purpose
    return None


def client_ip(headers, remote_addr: str | None) -> str | None:
    """IP real do cliente atrás de CDN/proxy (Cloudflare envia CF-Connecting-IP)."""
    for header in ("CF-Connecting-IP", "True-Client-IP"):
        if headers.get(header):
            return headers[header]
    forwarded = headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return remote_addr


class BotLogger:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def log(self, *, method: str, path: str, status: int, user_agent: str | None,
            ip: str | None, size: int | None, cache: str | None = None) -> dict | None:
        bot = identify(user_agent)
        if bot is None:
            return None
        signature, operator, purpose = bot
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "bot": signature,
            "operador": operator,
            "finalidade": purpose,
            "ia": operator in AI_OPERATORS,
            "metodo": method,
            "path": path,
            "status": status,
            "bytes": size,
            "ip": ip,
            "cdn_cache": cache,
            "ua": user_agent,
        }
        line = json.dumps(entry, ensure_ascii=False)
        with self._lock, self.path.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
        return entry

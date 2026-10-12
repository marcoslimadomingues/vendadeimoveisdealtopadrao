"""Varre o histórico COMPLETO de repositórios Git atrás de segredos e dados pessoais (somente leitura).

O que faz:
  - clona cada repositório (bare, sem checkout) para uma pasta temporária e a apaga no fim;
  - lê cada blob único de todos os commits (inclusive arquivos já apagados);
  - aplica regras de formato de credenciais, nomes de arquivo sensíveis e CPFs válidos;
  - mostra valores sempre MASCARADOS; nunca testa o segredo em serviço externo;
  - não altera, não envia e não abre nada nos repositórios.

Uso:
  python tools/varrer_segredos.py --usuario marcoslimadomingues --excluir vendadeimoveisdealtopadrao
  python tools/varrer_segredos.py marcoslimadomingues/clickpraia C:/caminho/local/repo --saida relatorio.md

Limites: é um filtro por padrões, não uma garantia. Achado = revisar; ausência de achado ≠ ausência de risco.
Complemente com gitleaks/trufflehog e com o secret scanning do GitHub.
"""
from __future__ import annotations

import argparse
import base64
import json
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from collections import defaultdict
from pathlib import Path

MAX_BLOB = 1_000_000
IGNORAR = re.compile(
    r"(^|/)(node_modules|vendor|\.git|__pycache__|wp-includes|wp-admin)/|\.min\.(js|css)$|package-lock\.json$|"
    r"yarn\.lock$|composer\.lock$|\.(png|jpe?g|gif|webp|ico|svg|woff2?|ttf|eot|otf|mp4|mp3|webm|pdf|map)$", re.I)
PLACEHOLDER = re.compile(
    r"(?i)your|seu_|sua_|example|exemplo|changeme|change_me|xxxx|\*\*\*|placeholder|insira|coloque|"
    r"password|senha|secret|token|chave|<|>|\.\.\.|\$\{|\{\{|process\.env|getenv|environ|null|undefined|true|false|^\d+$")

# (id, severidade, regex, descrição)
REGRAS = [
    ("chave-privada", "alta", re.compile(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH |PGP )?PRIVATE KEY(?: BLOCK)?-----"), "chave privada"),
    ("aws-access-key", "alta", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"), "chave de acesso AWS"),
    ("github-token", "alta", re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{36,}\b|\bgithub_pat_[A-Za-z0-9_]{50,}\b"), "token do GitHub"),
    ("stripe-live", "alta", re.compile(r"\b[sr]k_live_[0-9a-zA-Z]{20,}\b"), "chave Stripe de produção"),
    ("slack-token", "alta", re.compile(r"\bxox[baprs]-[0-9A-Za-z-]{10,}\b"), "token do Slack"),
    ("google-oauth-secret", "alta", re.compile(r"\bGOCSPX-[0-9A-Za-z_-]{20,}\b"), "client secret do Google"),
    ("anthropic-key", "alta", re.compile(r"\bsk-ant-[A-Za-z0-9_-]{30,}\b"), "chave Anthropic"),
    ("openai-key", "alta", re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{32,}\b"), "chave OpenAI"),
    ("telegram-bot", "alta", re.compile(r"\b\d{8,10}:[A-Za-z0-9_-]{35}\b"), "token de bot do Telegram"),
    ("meta-token", "alta", re.compile(r"\bEAA[A-Za-z0-9]{60,}\b"), "token da Meta/WhatsApp"),
    ("sendgrid", "alta", re.compile(r"\bSG\.[A-Za-z0-9_-]{16,}\.[A-Za-z0-9_-]{16,}\b"), "chave SendGrid"),
    ("mercadopago", "alta", re.compile(r"\bAPP_USR-[0-9a-f-]{20,}\b"), "credencial Mercado Pago"),
    ("asaas", "alta", re.compile(r"\$aact_[A-Za-z0-9_=-]{20,}"), "chave Asaas"),
    ("url-com-senha", "alta",
     re.compile(r"\b(?:mysqli?|postgres(?:ql)?|mongodb(?:\+srv)?|redis|amqp|ftps?|sftp|smtps?)://[^\s:/@'\"<>]+:[^\s@'\"<>]{3,}@[^\s'\"<>]+", re.I),
     "URL de conexão com usuário e senha"),
    ("google-api-key", "media", re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b"), "chave de API do Google (restrinja por domínio)"),
    ("jwt", "media", re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"), "JWT"),
    ("senha-atribuida", "media",
     re.compile(r"""(?i)\b(?:db_?pass(?:word)?|pass(?:word|wd)?|senha|secret(?:_key)?|api_?key|apikey|auth_?token|"""
                r"""access_?token|private_?key|client_?secret)\b["']?\s*(?:=>|[:=])\s*["']([^"'\s$][^"'\s]{7,})["']"""),
     "valor literal atribuído a campo de segredo"),
    ("wp-define", "media",
     re.compile(r"""define\(\s*['"](?:DB_PASSWORD|AUTH_KEY|SECURE_AUTH_KEY|LOGGED_IN_KEY|NONCE_KEY)['"]\s*,\s*['"]([^'"]{6,})['"]"""),
     "segredo do wp-config"),
]

# (regex do caminho, severidade, descrição)
ARQUIVOS = [
    (re.compile(r"(^|/)\.env(\.[\w.-]+)?$", re.I), "alta", "arquivo .env"),
    (re.compile(r"\.(pem|key|p12|pfx|ppk)$", re.I), "alta", "arquivo de chave/certificado"),
    (re.compile(r"(^|/)id_(rsa|dsa|ecdsa|ed25519)$"), "alta", "chave SSH privada"),
    (re.compile(r"(serviceaccount|firebase-adminsdk|client_secret|credentials?)[^/]*\.json$", re.I), "alta", "credencial em JSON"),
    (re.compile(r"(^|/)\.htpasswd$"), "media", ".htpasswd"),
    (re.compile(r"\.(sql|dump|sqlite3?|db|bak|backup)$", re.I), "media", "dump/backup de banco"),
    (re.compile(r"\.(zip|rar|7z|tar|gz|tgz)$", re.I), "baixa", "arquivo compactado (pode conter backup)"),
    (re.compile(r"\.log$", re.I), "baixa", "arquivo de log"),
]
ARQ_EXEMPLO = re.compile(r"(?i)(example|exemplo|sample|dist|template)")

EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
CPF = re.compile(r"\b(\d{3})\.(\d{3})\.(\d{3})-(\d{2})\b")


def cpf_valido(a: str, b: str, c: str, d: str) -> bool:
    n = [int(x) for x in a + b + c + d]
    if len(set(n)) == 1:
        return False
    for i in (9, 10):
        s = sum(n[j] * (i + 1 - j) for j in range(i))
        if (s * 10 % 11) % 10 != n[i]:
            return False
    return True


def mascarar(v: str) -> str:
    if "://" in v and "@" in v:  # URL com senha: esconde a senha
        return re.sub(r"(://[^:/@]+:)[^@]+(@)", r"\1***\2", v)[:80]
    return (v[:4] + "…" + v[-2:] + f" ({len(v)} car.)") if len(v) > 8 else "***"


def jwt_funcao(token: str) -> str:
    try:
        carga = token.split(".")[1]
        dados = json.loads(base64.urlsafe_b64decode(carga + "=" * (-len(carga) % 4)))
        return str(dados.get("role", ""))
    except Exception:  # noqa: BLE001
        return ""


def git(repo: str, *args: str, entrada: bytes | None = None) -> bytes:
    r = subprocess.run(["git", "-C", repo, *args], input=entrada, capture_output=True)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.decode("utf-8", "replace")[:300])
    return r.stdout


def ler_blobs(repo: str, shas: list[str]):
    """gera (sha, conteúdo) usando git cat-file --batch em lotes."""
    for i in range(0, len(shas), 400):
        lote = shas[i:i + 400]
        saida = git(repo, "cat-file", "--batch", entrada=("\n".join(lote) + "\n").encode())
        pos = 0
        while pos < len(saida):
            fim = saida.index(b"\n", pos)
            cab = saida[pos:fim].split()
            if len(cab) < 3 or cab[1] == b"missing":
                pos = fim + 1
                continue
            tam = int(cab[2])
            yield cab[0].decode(), saida[fim + 1: fim + 1 + tam]
            pos = fim + 1 + tam + 1


def varrer(repo: str) -> dict:
    objs = git(repo, "rev-list", "--objects", "--all").decode("utf-8", "replace")
    caminhos: dict[str, list[str]] = defaultdict(list)
    for linha in objs.splitlines():
        sha, _, caminho = linha.partition(" ")
        if caminho:
            caminhos[sha].append(caminho)
    verif = git(repo, "cat-file", "--batch-check", entrada=("\n".join(caminhos) + "\n").encode()).decode()
    blobs = {}
    for ln in verif.splitlines():
        sha, tipo, tam = ln.split()
        if tipo == "blob":
            blobs[sha] = int(tam)
    ncommits = len(git(repo, "rev-list", "--all").split())
    em_head = set()
    try:
        for ln in git(repo, "ls-tree", "-r", "HEAD").decode("utf-8", "replace").splitlines():
            em_head.add(ln.split()[2])
    except RuntimeError:
        pass

    achados: dict[tuple, dict] = {}

    def registrar(regra, sev, desc, valor, caminho, sha, extra=""):
        k = (regra, valor)
        a = achados.setdefault(k, {"regra": regra, "sev": sev, "desc": desc, "valor": valor,
                                   "caminhos": set(), "atual": False, "extra": extra})
        a["caminhos"].add(caminho)
        a["atual"] = a["atual"] or sha in em_head

    ler = []
    for sha, tam in blobs.items():
        for caminho in caminhos[sha]:
            for rx, sev, desc in ARQUIVOS:
                if rx.search(caminho) and not ARQ_EXEMPLO.search(caminho):
                    registrar("arquivo-sensivel", sev, desc, caminho, caminho, sha)
        if tam <= MAX_BLOB and not all(IGNORAR.search(c) for c in caminhos[sha]):
            ler.append(sha)

    for sha, dados in ler_blobs(repo, ler):
        if b"\0" in dados[:8000]:
            continue
        texto = dados.decode("utf-8", "replace")
        caminho = next((c for c in caminhos[sha] if not IGNORAR.search(c)), caminhos[sha][0])
        for regra, sev, desc, rx, *_ in [(r[0], r[1], r[3], r[2]) for r in REGRAS]:
            for m in rx.finditer(texto):
                valor = m.group(1) if m.groups() else m.group(0)
                if regra in ("senha-atribuida", "wp-define") and PLACEHOLDER.search(valor):
                    continue
                s, extra = sev, ""
                if regra == "jwt":
                    funcao = jwt_funcao(m.group(0))
                    if funcao == "service_role":
                        s, desc2 = "alta", "JWT Supabase com role service_role (acesso total)"
                        registrar(regra, s, desc2, m.group(0), caminho, sha, funcao)
                        continue
                    extra = f"role={funcao or 'n/d'} (anon/public é esperado no front-end)"
                    if funcao in ("anon", ""):
                        s = "baixa"
                registrar(regra, s, desc, valor, caminho, sha, extra)
        cpfs = {m.group(0) for m in CPF.finditer(texto) if cpf_valido(*m.groups())}
        if cpfs:
            registrar("cpf", "alta", f"{len(cpfs)} CPF(s) válido(s) no arquivo", f"{len(cpfs)} CPFs", caminho, sha)
        emails = set(EMAIL.findall(texto))
        if len(emails) >= 20 and not IGNORAR.search(caminho):
            registrar("lista-emails", "media", f"{len(emails)} e-mails distintos no arquivo", f"{len(emails)} e-mails", caminho, sha)

    return {"commits": ncommits, "blobs": len(blobs), "lidos": len(ler), "achados": list(achados.values())}


def clonar(alvo: str, base: Path) -> tuple[str, str]:
    if Path(alvo).exists():
        return alvo, str(alvo)
    url = alvo if alvo.startswith("http") else f"https://github.com/{alvo}.git"
    destino = base / re.sub(r"\W+", "_", alvo)
    r = subprocess.run(["git", "clone", "--bare", "--quiet", url, str(destino)], capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip()[:300])
    return str(destino), alvo


def listar(usuario: str) -> list[str]:
    req = urllib.request.Request(f"https://api.github.com/users/{usuario}/repos?per_page=100",
                                 headers={"User-Agent": "varrer-segredos", "Accept": "application/vnd.github+json"})
    return [f"{usuario}/{r['name']}" for r in json.loads(urllib.request.urlopen(req, timeout=30).read())]


def formatar(resultados: dict[str, dict]) -> str:
    ordem = {"alta": 0, "media": 1, "baixa": 2}
    linhas = ["# Varredura de segredos e dados pessoais", "",
              "Somente leitura. Valores mascarados. Padrões, não garantia: achado = revisar.", ""]
    linhas += ["| Repositório | Commits | Alta | Média | Baixa |", "|---|---:|---:|---:|---:|"]
    for nome, r in resultados.items():
        if "erro" in r:
            linhas.append(f"| {nome} | erro | | | |")
            continue
        c = defaultdict(int)
        for a in r["achados"]:
            c[a["sev"]] += 1
        linhas.append(f"| {nome} | {r['commits']} | {c['alta']} | {c['media']} | {c['baixa']} |")
    for nome, r in resultados.items():
        linhas += ["", f"## {nome}", ""]
        if "erro" in r:
            linhas.append(f"Erro: {r['erro']}")
            continue
        if not r["achados"]:
            linhas.append("Nenhum achado nos padrões verificados.")
            continue
        for a in sorted(r["achados"], key=lambda a: (ordem[a["sev"]], a["regra"], sorted(a["caminhos"])[0])):
            onde = "no arquivo atual" if a["atual"] else "SÓ NO HISTÓRICO (apagado, mas recuperável)"
            cams = sorted(a["caminhos"])
            linhas.append(f"- **[{a['sev'].upper()}] {a['desc']}** — `{cams[0]}`"
                          f"{f' (+{len(cams) - 1} caminho(s))' if len(cams) > 1 else ''}; {onde}; "
                          f"valor: `{mascarar(a['valor'])}`{f'; {a['extra']}' if a['extra'] else ''}")
    return "\n".join(linhas) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("alvos", nargs="*", help="dono/repositório, URL ou pasta local")
    ap.add_argument("--usuario", help="varre todos os repositórios públicos deste usuário")
    ap.add_argument("--excluir", nargs="*", default=[], help="nomes de repositório a pular")
    ap.add_argument("--saida", help="grava o relatório em Markdown neste arquivo")
    args = ap.parse_args()

    alvos = list(args.alvos)
    if args.usuario:
        alvos += [a for a in listar(args.usuario) if a.split("/")[1] not in args.excluir]
    if not alvos:
        ap.error("informe repositórios ou --usuario")

    base = Path(tempfile.mkdtemp(prefix="varredura-"))
    resultados: dict[str, dict] = {}
    try:
        for alvo in alvos:
            try:
                pasta, nome = clonar(alvo, base)
                resultados[nome] = varrer(pasta)
                print(f"{nome}: {resultados[nome]['commits']} commits, {len(resultados[nome]['achados'])} achado(s)", flush=True)
            except Exception as e:  # noqa: BLE001
                resultados[alvo] = {"erro": str(e)}
                print(f"{alvo}: erro: {e}", flush=True)
    finally:
        shutil.rmtree(base, ignore_errors=True)  # nenhuma cópia dos repositórios fica no disco

    relatorio = formatar(resultados)
    if args.saida:
        Path(args.saida).parent.mkdir(parents=True, exist_ok=True)
        Path(args.saida).write_text(relatorio, encoding="utf-8")
        print(f"relatório: {args.saida}")
    else:
        print(relatorio)
    return 0


if __name__ == "__main__":
    sys.exit(main())

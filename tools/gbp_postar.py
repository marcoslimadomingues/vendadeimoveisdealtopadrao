"""Posta no Perfil da Empresa no Google pela API: a novidade semanal do radar e fotos.

Credenciais ficam FORA do repositório (que é público), em ~/.config/alto_padrao/:
  client_secrets.json   cliente OAuth "App para computador" do Google Cloud (ou aponte GBP_CLIENT_SECRETS)
  gbp_token.json        criado no 1º login (abre o navegador uma vez)
  gbp.json              o local escolhido: {"local": "accounts/123/locations/456"}

    py -3.14 tools/gbp_postar.py contas                       lista contas e locais (e testa se a API foi liberada)
    py -3.14 tools/gbp_postar.py local accounts/1/locations/2 grava o local padrão
    py -3.14 tools/gbp_postar.py novidades                    últimas postagens do perfil
    py -3.14 tools/gbp_postar.py radar 2026-11-09             mostra a postagem de postagens/<slug>/ sem publicar
    py -3.14 tools/gbp_postar.py radar 2026-11-09 --publicar  publica
    py -3.14 tools/gbp_postar.py foto caminho.jpg --categoria EXTERIOR [--publicar]

A imagem da novidade é a que o site já publica em /static/img/radar/<slug>-4x3.png (a API exige URL pública).
Fotos aceitam arquivo local (upload direto) ou URL https.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITE = "https://vendadeimoveisdealtopadrao.com.br"
CONF = Path.home() / ".config" / "alto_padrao"
SCOPES = ["https://www.googleapis.com/auth/business.manage"]
API_CONTAS = "https://mybusinessaccountmanagement.googleapis.com/v1"
API_INFO = "https://mybusinessbusinessinformation.googleapis.com/v1"
API_V4 = "https://mybusiness.googleapis.com/v4"
CATEGORIAS = ["COVER", "PROFILE", "LOGO", "EXTERIOR", "INTERIOR", "PRODUCT", "AT_WORK", "COMMON_AREA",
              "ROOMS", "TEAMS", "ADDITIONAL"]
LIMITE_TEXTO = 1500


def sessao():
    from google.auth.transport.requests import AuthorizedSession, Request
    from google.oauth2.credentials import Credentials

    token = CONF / "gbp_token.json"
    cred = Credentials.from_authorized_user_file(str(token), SCOPES) if token.is_file() else None
    if cred and cred.expired and cred.refresh_token:
        cred.refresh(Request())
    if not cred or not cred.valid:
        from google_auth_oauthlib.flow import InstalledAppFlow

        segredo = Path(os.environ.get("GBP_CLIENT_SECRETS", CONF / "client_secrets.json"))
        if not segredo.is_file():
            sys.exit(f"Falta o cliente OAuth em {segredo} (ou defina GBP_CLIENT_SECRETS).")
        cred = InstalledAppFlow.from_client_secrets_file(str(segredo), SCOPES).run_local_server(port=0)
    CONF.mkdir(parents=True, exist_ok=True)
    token.write_text(cred.to_json(), encoding="utf-8")
    return AuthorizedSession(cred)


def chamar(s, metodo: str, url: str, **kw) -> dict:
    r = s.request(metodo, url, timeout=60, **kw)
    if r.ok:
        return r.json() if r.content else {}
    txt = r.text
    if r.status_code == 429 and "quota" in txt.lower():
        sys.exit("A API respondeu 'cota excedida'. Com cota 0, o Google ainda não liberou o acesso "
                 "(formulário pendente). Detalhe: " + txt[:400])
    if r.status_code == 403 and ("SERVICE_DISABLED" in txt or "has not been used" in txt):
        sys.exit("API desativada no projeto do Google Cloud. Ative: My Business Account Management API, "
                 "My Business Business Information API e Google My Business API. Detalhe: " + txt[:400])
    sys.exit(f"Erro {r.status_code} em {metodo} {url}:\n{txt[:1500]}")


def local_padrao(arg: str | None) -> str:
    if arg:
        return arg
    f = CONF / "gbp.json"
    if f.is_file():
        return json.loads(f.read_text(encoding="utf-8"))["local"]
    sys.exit("Nenhum local escolhido. Rode 'contas' e depois 'local accounts/.../locations/...'.")


def cmd_contas(s, _a) -> None:
    contas = chamar(s, "GET", f"{API_CONTAS}/accounts").get("accounts", [])
    if not contas:
        print("Nenhuma conta encontrada para este login.")
    achados = []
    for c in contas:
        print(f"{c['name']}  {c.get('accountName', '')}  ({c.get('type', '')})")
        locs = chamar(s, "GET", f"{API_INFO}/{c['name']}/locations",
                      params={"readMask": "name,title,storefrontAddress", "pageSize": 100}).get("locations", [])
        for l in locs:
            caminho = f"{c['name']}/{l['name']}"
            achados.append(caminho)
            end = ", ".join((l.get("storefrontAddress") or {}).get("addressLines", []))
            print(f"   {caminho}  {l.get('title', '')}  {end}")
    if len(achados) == 1 and not (CONF / "gbp.json").is_file():
        cmd_local(s, argparse.Namespace(caminho=achados[0]))


def cmd_local(_s, a) -> None:
    CONF.mkdir(parents=True, exist_ok=True)
    (CONF / "gbp.json").write_text(json.dumps({"local": a.caminho}), encoding="utf-8")
    print(f"Local padrão gravado: {a.caminho}")


def novidades(s, local: str) -> list[dict]:
    return chamar(s, "GET", f"{API_V4}/{local}/localPosts", params={"pageSize": 20}).get("localPosts", [])


def cmd_novidades(s, a) -> None:
    for p in novidades(s, local_padrao(a.local)):
        cta = (p.get("callToAction") or {}).get("url", "")
        print(f"{p.get('createTime', '')[:10]}  {p.get('state', '')}  {cta}\n   {p.get('summary', '')[:120]!r}")


def ler_postagem(slug: str) -> tuple[str, str]:
    f = ROOT / "postagens" / slug / "postagem.md"
    if not f.is_file():
        sys.exit(f"Não achei {f}.")
    cabecalho, _, texto = f.read_text(encoding="utf-8").replace("\r\n", "\n").partition("\n\n")
    url = next((l.split("→", 1)[1].strip() for l in cabecalho.splitlines() if l.startswith("Botão:") and "→" in l),
               f"{SITE}/radar/{slug}/")
    texto = texto.strip()
    if len(texto) > LIMITE_TEXTO:
        sys.exit(f"Texto com {len(texto)} caracteres; o limite do Google é {LIMITE_TEXTO}.")
    return texto, url


def cmd_radar(s, a) -> None:
    import requests

    texto, url = ler_postagem(a.slug)
    imagem = f"{SITE}/static/img/radar/{a.slug}-4x3.png"
    corpo = {"languageCode": "pt-BR", "topicType": "STANDARD", "summary": texto,
             "callToAction": {"actionType": "LEARN_MORE", "url": url},
             "media": [{"mediaFormat": "PHOTO", "sourceUrl": imagem}]}
    print(json.dumps(corpo, ensure_ascii=False, indent=2))
    for u in (url, imagem):
        if requests.head(u, timeout=30, allow_redirects=True).status_code != 200:
            sys.exit(f"{u} ainda não responde 200; espere o deploy do site terminar.")
    if not a.publicar:
        print("\nSó conferência. Para publicar, repita com --publicar.")
        return
    local = local_padrao(a.local)
    if any((p.get("callToAction") or {}).get("url") == url for p in novidades(s, local)):
        sys.exit(f"Já existe novidade no perfil apontando para {url}; não vou duplicar.")
    p = chamar(s, "POST", f"{API_V4}/{local}/localPosts", json=corpo)
    print(f"\nPublicada: {p.get('name')} ({p.get('state', '')})\n{p.get('searchUrl', '')}")


def cmd_foto(s, a) -> None:
    cat = a.categoria.upper()
    if cat not in CATEGORIAS:
        sys.exit(f"Categoria inválida. Use uma de: {', '.join(CATEGORIAS)}")
    corpo = {"mediaFormat": "PHOTO", "locationAssociation": {"category": cat}}
    if a.descricao:
        corpo["description"] = a.descricao
    origem = a.arquivo
    if not origem.startswith("https://") and not Path(origem).is_file():
        sys.exit(f"Arquivo não encontrado: {origem}")
    print(f"Foto: {origem}  categoria {cat}")
    if not a.publicar:
        print("Só conferência. Para enviar, repita com --publicar.")
        return
    local = local_padrao(a.local)
    if origem.startswith("https://"):
        corpo["sourceUrl"] = origem
    else:
        ref = chamar(s, "POST", f"{API_V4}/{local}/media:startUpload", json={})
        dados = Path(origem).read_bytes()
        chamar(s, "POST", f"https://mybusiness.googleapis.com/upload/v1/media/{ref['resourceName']}",
               params={"upload_type": "media"}, data=dados,
               headers={"Content-Type": "application/octet-stream"})
        corpo["dataRef"] = {"resourceName": ref["resourceName"]}
    m = chamar(s, "POST", f"{API_V4}/{local}/media", json=corpo)
    print(f"Enviada: {m.get('name')}\n{m.get('googleUrl', '')}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--local", help="accounts/.../locations/... (padrão: ~/.config/alto_padrao/gbp.json)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("contas").set_defaults(f=cmd_contas)
    p = sub.add_parser("local"); p.add_argument("caminho"); p.set_defaults(f=cmd_local)
    sub.add_parser("novidades").set_defaults(f=cmd_novidades)
    p = sub.add_parser("radar"); p.add_argument("slug"); p.add_argument("--publicar", action="store_true")
    p.set_defaults(f=cmd_radar)
    p = sub.add_parser("foto"); p.add_argument("arquivo"); p.add_argument("--categoria", default="ADDITIONAL")
    p.add_argument("--descricao"); p.add_argument("--publicar", action="store_true"); p.set_defaults(f=cmd_foto)
    a = ap.parse_args()
    if a.cmd == "local":
        return cmd_local(None, a)
    if a.cmd in ("radar", "foto") and not a.publicar:
        return a.f(None, a)
    a.f(sessao(), a)


if __name__ == "__main__":
    main()

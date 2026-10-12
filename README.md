# Imóveis de Alto Padrão em Fortaleza

Site HTML5 renderizado no servidor (Flask + Jinja2), exportado como site estático e publicado no
**GitHub Pages**. Sem JavaScript no navegador, sem banco de dados, sem hospedagem paga.

> **Dados ilustrativos.** Empresa, CRECI, CNPJ, pessoas, carteira, vídeos e perfis sociais são de
> demonstração. `python tools/pre_publicacao.py` lista o que falta trocar; enquanto houver pendência, o
> site é publicado com `noindex`.

## Rodar localmente

```bash
pip install -r requirements.txt
python app.py                      # http://127.0.0.1:8000
python -m pytest -q                # testes
python tools/build_pages.py --dominio https://vendadeimoveisdealtopadrao.com.br   # gera build/pages
```

## Publicação (GitHub Pages)

O repositório é a fonte da verdade. Um `push` na `main` dispara `.github/workflows/publicar.yml`:

1. **site**: testes, checklist de dados provisórios, descobre o endereço do Pages, gera `build/pages`.
2. **publicar**: publica no Pages (só na `main`, só se o Pages estiver ativo). Pull requests só testam.

**Uma vez só, no GitHub:** *Settings → Pages → Build and deployment → Source: **GitHub Actions***.

### Domínio próprio (vendadeimoveisdealtopadrao.com.br)

1. *Settings → Pages → Custom domain*: informe o domínio. Marque **Enforce HTTPS** quando liberar.
2. *Settings (da conta) → Pages → Add a domain*: verifique o domínio (impede que outra conta o reivindique).
3. No DNS do domínio (Registro.br, se for `.com.br`):

| Tipo | Nome | Valor |
|---|---|---|
| A | `@` | `185.199.108.153`, `185.199.109.153`, `185.199.110.153`, `185.199.111.153` |
| AAAA | `@` | `2606:50c0:8000::153`, `2606:50c0:8001::153`, `2606:50c0:8002::153`, `2606:50c0:8003::153` |
| CNAME | `www` | `marcoslimadomingues.github.io` |

Confira os IPs na documentação do GitHub antes de gravar (podem mudar).

Sem domínio configurado, o site fica em `https://marcoslimadomingues.github.io/vendadeimoveisdealtopadrao/`:
o build detecta o endereço sozinho (a URL vem da API do Pages) e prefixa os links.

### Variáveis opcionais (*Settings → Secrets and variables → Actions → Variables*)

| Variável | Efeito |
|---|---|
| `SITE_URL` | força a URL de build |
| `EXIGIR_DADOS_REAIS=true` | bloqueia a publicação enquanto `pre_publicacao.py` acusar pendência |
| `FORCAR_INDEXACAO=true` | indexa mesmo com dado provisório (não recomendado) |

### Indexação automática

`tools/pre_publicacao.py` roda a cada push. Com dado provisório (vídeos, telefone, CNPJ, CRECI, fotos,
perfis, `og:image` em SVG) o site sai com `<meta name="robots" content="noindex, nofollow">`. Quando a
lista zera, a próxima publicação já sai indexável.

### O que o Pages não faz (e como o projeto contorna)

| Limitação | Solução |
|---|---|
| Sem cabeçalhos HTTP próprios | CSP e robots vão em `<meta>` (`script-src 'none'` continua valendo) |
| Sem `.htaccess` | o Pages já força HTTPS, `www` → domínio e responde 404 real com `404.html` |
| Sem logs de acesso | telemetria de bots: Search Console (estatísticas de rastreamento) ou CDN com analytics |

## Estrutura

```
app.py                  rotas SSR, cabeçalhos, modo noindex
seo/                    conteúdo, JSON-LD, títulos em links, tabelas em cartões, pilar
data/                   site, bairros, imóveis, guias, especialistas, pilar, geo (OpenStreetMap)
templates/ static/      HTML5 semântico e CSS único (sem JS, sem webfont)
tools/                  build_pages, pre_publicacao, varrer_segredos, mapa, auditorias, teste_mobile
tests/                  testes de contrato (HTTP, JSON-LD, mobile, publicação, scanner)
.github/                workflow do Pages, Dependabot
```

## Conteúdo

- **Novo imóvel:** `data/imoveis.json` (`referencia`, `tecnico`, `amenidades` com as 3 obrigatórias).
  Preço/m², custos, ITBI e FAQ são calculados; o teste confere o resumo.
- **Imóvel vendido:** `status: "vendido"` + `data_venda`: a URL passa a dar 404 e sai do sitemap.
- **Vídeos:** `videos: [...]` com `youtube_id` (11 caracteres), `tipo`, `apresentador`, `duracao`
  (ISO 8601) e `data_upload`. Os `SUBSTITUA..` são provisórios.
- **Respostas rápidas:** `secoes[].respostas_rapidas` nos guias; viram `<dl>` visível e `Question` no JSON-LD.
- **Cidade:** cidade, faixa de preço, período e ITBI ficam em `data/site.json`; nenhum template tem cidade fixa.

### Pilar "Milha de ouro"

`/milha-de-ouro-fortaleza/`: `data/pilares.json` (indicadores com fonte, data e URL) e `data/geo/`.
Todo número em texto corrido é gerado em `seo/pilares.py` a partir dos indicadores; o `Repo` recusa
indicador sem fonte ou sem data. Mapa e ruas: `python tools/mapa_milha_de_ouro.py gerar` (offline) ou
`baixar` (consulta o OpenStreetMap). Prédios reais só com nome e fonte; preço, metragem e entrega
exigem dado verificado.

### SEO, GEO, AEO e SXO

- **Entidade e contato:** `data/site.json` alimenta rodapé, `/sobre/`, `/contato/` e o nó `Organization`
  (`identifier` CNPJ/CRECI, `contactPoint`, `openingHoursSpecification`, `hasMap`). `sameAs` só aparece com perfil real.
- **AEO:** FAQ da home gerada de `Repo.faq_institucional()` (endereço, contato, ITBI, prazo por bairro), visível
  na página e em `FAQPage`; guias e pilar já trazem as suas.
- **GEO:** `/llms.txt` (resumo para agentes de IA, só na raiz do domínio) e `robots.txt` liberando os crawlers de IA.
- **SXO:** CTA de WhatsApp na abertura da home, barra fixa no celular, `/contato/` com endereço e "Como chegar".
- **Compartilhamento:** `og:image` em PNG 1200×630 (`static/img/og-marca.png`, gerado de `og-marca.svg`); SVG
  de página cai na marca pelo filtro `og_png`. Tags `twitter:*`, `hreflang` e `geo.*` em todas as páginas.

### Celular (mobile-first)

Tabelas com 3+ colunas viram cartões até 40 rem (`rotular_tabelas` + `table.empilhar`); menu em uma linha
rolável; barra fixa WhatsApp/Ligar até 48 rem; mapa em duas metades. `node tools/teste_mobile.mjs <tag>
<url>...` emula 390×844 e mede overflow horizontal (o `--window-size` do Chrome impõe largura mínima).

## Segurança

- Workflow com `contents: read`; `pages: write` e `id-token: write` só no job de publicação.
- Dependabot (`pip`, `github-actions`), `SECURITY.md` (relato privado de vulnerabilidade).
- `python tools/varrer_segredos.py --usuario <usuario> --saida relatorio.md`: varre o histórico de todos
  os repositórios (somente leitura, valores mascarados). Complementa o secret scanning do GitHub.
- Nada de credencial no repositório; `.env`, `logs/`, `build/` e `dist/` estão no `.gitignore`.

## Pendências de SEO geográfico

Ver `docs/PENDENTE-GEOTAG.md`.

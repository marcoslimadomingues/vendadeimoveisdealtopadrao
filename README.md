# Alto Padrão Imóveis — plataforma HTML5 SSR para AEO, GEO e SEO

Site de imobiliária de altíssimo padrão renderizado 100% no servidor (Flask + Jinja2), sem
JavaScript no cliente. Pode rodar como app Python ou ser exportado como HTML5 estático.

> **ATENÇÃO — dados ilustrativos.** Empresa, CRECI, CNPJ, métricas, preços, pessoas, perfis do
> LinkedIn/YouTube e IDs de vídeo (`SUBSTITUA01`…) são fictícios. Substitua tudo em `data/` por
> dados reais e verificáveis antes de publicar. Dados inventados destroem o E-E-A-T.

## Como rodar

```bash
pip install -r requirements.txt
python app.py                                   # http://127.0.0.1:8000
python -m pytest -q                             # 24 testes de contrato
python tools/export_static.py --site-url https://www.seudominio.com.br   # gera dist/
waitress-serve --port=8000 --call app:create_app                         # produção
```

Variáveis: `SITE_URL` (domínio canônico), `BOT_LOG` (caminho do log JSONL), `PORT`.

## Fluxo de trabalho (GitHub)

O repositório é a fonte da verdade: https://github.com/marcoslimadomingues/vendadeimoveisdealtopadrao

1. Mudanças entram por commit na branch `main` (conteúdo em `data/`, layout em `templates/` e `static/`).
2. `.github/workflows/publicar.yml` roda os testes, compila o site estático e, se os segredos
   existirem, publica em `/public_html/altopadrao` por FTPS. Sem segredos, só testa e compila.
3. Segredos (GitHub → Settings → Secrets and variables → Actions): `FTP_HOST`, `FTP_USER`, `FTP_PASS`.
   Use uma conta FTP restrita à pasta do site, se a hospedagem permitir.

Nada de credencial vai para o repositório: `.ftp.env` e `logs/` estão no `.gitignore`.

## Cidade

O site está configurado para **Fortaleza (CE)**. Cidade, faixa de preço (`limiar_texto`), período dos
indicadores e ITBI (alíquota geral, alíquota com pagamento antecipado) ficam em `data/site.json`;
nenhum template tem cidade fixa. Para outra cidade, troque `site.json`, `bairros.json`, `imoveis.json`,
`artigos.json` e `especialistas.json`. Pendências de SEO geográfico: `docs/PENDENTE-GEOTAG.md`.

## Pilar "Milha de ouro"

`/milha-de-ouro-fortaleza/`: Avenida Beira Mar entre Meireles e Mucuripe. Dados em `data/pilares.json`
(indicadores com fonte, data de referência e URL; empreendimentos citados na imprensa) e `data/geo/`
(OpenStreetMap). Todo número em texto corrido é gerado em `seo/pilares.py` a partir dos indicadores.

- Novo valor de m²: adicione em `indicadores` com `fonte` cadastrada em `fontes`, `origem` e `referencia`
  (`AAAA-MM`); o `Repo` recusa indicador sem fonte ou sem data.
- Mapa e ruas: `python tools/mapa_milha_de_ouro.py gerar` (offline, usa `data/geo/raw/`);
  `... baixar` refaz a consulta ao OpenStreetMap (Overpass).
- Prédios reais: só entram em `empreendimentos_citados` com nome e fonte; preço, metragem e entrega
  exigem dado verificado.
- Cloudflare: e-mails ficam entre `<!--email_off-->` para a CDN não ofuscar (a CSP bloqueia o script dela).

## Celular (mobile-first)

- Tabelas com 3+ colunas viram cartões em telas até 40 rem: `seo/titulos.py::rotular_tabelas` põe
  `data-label` em cada `<td>` e `class="empilhar"` na tabela; o CSS (`table.empilhar`) faz o resto.
  Em telas largas continua uma tabela HTML nativa. Células com texto longo ganham `class="longo"`.
- Menu em uma linha rolável; barra fixa "WhatsApp / Ligar" até 48 rem (usa `site.whatsapp` e
  `site.telefone_link`; na ficha a mensagem cita o código do imóvel).
- Mapa do pilar: figura inteira no desktop; no celular, duas metades empilhadas (oeste e leste).
- Cache: `style.css?v=<hash>` e o mapa mudam de URL quando o arquivo muda.
- Teste visual: `node tools/teste_mobile.mjs <tag> <url>...` (Chrome + Node 22+) emula 390×844, mede
  overflow horizontal e salva capturas em `build/mobile/`. Não use `--window-size` do Chrome para isso:
  ele impõe largura mínima de ~500 px.

## Publicação por FTPS

```bash
python tools/build_cpanel.py --dominio https://marcoslima.com.br/altopadrao
python tools/publicar_ftps.py --remoto /public_html/altopadrao --simular   # confere
python tools/publicar_ftps.py --remoto /public_html/altopadrao
```
Credenciais: variáveis `FTP_USER`/`FTP_PASS` ou `.ftp.env`. No Git Bash, use `MSYS_NO_PATHCONV=1`.

## Deploy em cPanel (Apache)

```bash
python tools/build_cpanel.py --dominio https://www.seudominio.com.br   # gera site-cpanel.zip
```

Gerenciador de Arquivos → `public_html/` → Carregar o zip → Extrair (mostrar arquivos ocultos para ver o `.htaccess`).
O `.htaccess` força HTTPS + host canônico, mantém 404 real (`ErrorDocument`), aplica os cabeçalhos
(`X-Robots-Tag` só em 2xx, CSP, cache) e compressão. Bot Access Logs no cPanel: Métricas → Acesso bruto
(formato combined) → `python tools/bot_report.py --combined arquivo.log`.

## Estrutura

```
app.py                  rotas SSR, status HTTP, cabeçalhos, Bot Access Log
seo/content.py          carrega data/, valida referências, calcula preço/m², custos e FAQ derivado
seo/jsonld.py           gerador do @graph Schema.org por tipo de página
seo/bots.py             identificação de crawlers/agentes de IA + logger JSONL
seo/formatting.py       formatação pt-BR (R$, %, datas)
data/*.json             conteúdo: site, bairros, imóveis, artigos, especialistas
templates/              HTML5 semântico (base, home, imóvel, bairro, artigo, perfil, 404, robots, sitemap)
static/css/style.css    CSS único, sem webfont, responsivo
tools/export_static.py  exporta dist/ (HTML puro + 404.html + _headers para Cloudflare Pages/Netlify)
tools/check_headers.py  diagnóstico HTTP/CDN: noindex, soft 404, canonical, JSON-LD, bloqueio de bots
tools/bot_report.py     relatório de consideração por URL e por agente de IA
tools/semantic_audit.py similaridade de cosseno, densidade factual, adjetivos vagos
deploy/nginx.conf       entrega estática ou proxy, 404 real, log dedicado de bots
tests/test_site.py      testes de contrato
```

## Como cada etapa do Prompt Master foi implementada

| Etapa | Implementação |
|---|---|
| **1.1 HTML5 SSR** | Todo conteúdo sai do Jinja2 na resposta inicial. Único `<script>` é o JSON-LD. CSP `script-src 'none'` impede JS. Teste `test_sem_javascript_e_sem_conteudo_oculto`. |
| **1.2 Status HTTP / CDN** | URL inexistente e imóvel `status: "vendido"` → **HTTP 404 real** (página útil com alternativas, `noindex`). 200 recebe `X-Robots-Tag: index, follow…`; 5xx recebe `no-store` (CDN não cacheia erro); `s-maxage=600` faz imóvel vendido sair da borda em até 10 min. `tools/check_headers.py` detecta noindex injetado, soft 404, divergência CDN × origem e challenge para bots. |
| **1.3 robots.txt** | `Allow: /` explícito para GPTBot, OAI-SearchBot, ClaudeBot, PerplexityBot, Google-Extended, Bytespider etc. Nenhum `Disallow`. |
| **1.4 Bot Access Logs** | `after_request` grava JSONL (bot, operador, finalidade, URL, status, IP real via `CF-Connecting-IP`). `bot_report.py` agrega por URL e lista URLs do sitemap **nunca** visitadas por IA. Nginx tem `access_log bots.log if=$bot_ia`. |
| **2.1 Zero conteúdo oculto** | Sem abas, accordions, `<details>`, dropdowns. FAQ sempre aberto. Teste bloqueia `hidden`, `aria-expanded`, `role="tab"`. |
| **2.2 Tabelas nativas** | `<table>/<caption>/<thead>/<tbody>/<tfoot>`, `scope` em `<th>`. Ficha técnica, custos, comparativo com bairro, liquidez e técnica. |
| **2.3 Triplas / pirâmide invertida** | Resumo executivo no 1º parágrafo; frases Sujeito‑Predicado‑Objeto com números; entidade repetida em cada chunk (sem "Sim. A matrícula…" solto). |
| **3 Topical Authority** | Entidade central + intenção central em `data/site.json`, no H1 da home, no `about` de todo WebPage. **Core**: `/imoveis/`, `/bairros/`. **Outdoor**: `/guias/`. Links contextuais Outdoor → Core dentro dos parágrafos (teste `test_outdoor_transfere_autoridade_para_core`). |
| **4 Vetorial / fan-out / híbrido** | Cada H2 é uma pergunta derivada (fan-out) respondida na 1ª frase. Imóveis ganham FAQ calculado (preço/m² × bairro, custo mensal, liquidez). `semantic_audit.py` mede cosseno parágrafo × intenção e parágrafo × H2 (TF-IDF ou `--modelo` sentence-transformers). |
| **5 JSON-LD** | `@graph` estático no `<head>`: Organization+RealEstateAgent, WebSite, entidade central, BreadcrumbList; imóvel = RealEstateListing + Offer (price, BRL) + SingleFamilyResidence/Apartment (floorSize MTK, amenityFeature LocationFeatureSpecification com Isolamento Acústico Europeu, Portaria Blindada, Gerador Total) + Place + VideoObject + Question; artigo = Article ↔ Person ↔ Organization (+ FAQPage); bairro = Place + Dataset; perfil = ProfilePage + Person com credencial e sameAs. |
| **6 E-E-A-T** | Página por especialista (CRECI/CAU/OAB, anos, transações, LinkedIn/YouTube `rel="me"`); autoria e revisão em cada ficha e artigo; embeds YouTube (`youtube-nocookie`, `loading="lazy"`) com descrição textual visível. |
| **7 Validação / CWV** | 22 páginas passam no `html-validate` (preset recommended). CSS único ~9 KB, sem webfont, imagens com `width/height` (CLS 0), `fetchpriority="high"` na imagem principal, zero JS (INP mínimo). |

## Operação

- **Novo imóvel**: adicione em `data/imoveis.json` (`referencia`, `tecnico`, `amenidades` com as 3 obrigatórias). Preço/m², custos e FAQ numérico são calculados; o teste confere se o `resumo` bate com o preço/m² calculado.
- **Imóvel vendido**: troque `status` para `"vendido"` e informe `data_venda`. A URL passa a responder 404, sai do sitemap e dos links.
- **Após publicar**: `python tools/check_headers.py https://www.seudominio.com.br --origem https://origem…`; confira no Cloudflare que "Block AI bots"/"Managed robots.txt" estão desativados; valide URLs no Search Console (Inspeção de URL) e no Rich Results Test.
- **Vídeos**: cada imóvel/guia tem `videos: [...]` com `youtube_id` (11 caracteres), `tipo`, `apresentador` (slug em `especialistas.json`), `duracao` ISO 8601 e `data_upload`. Os IDs `SUBSTITUA01`–`SUBSTITUA13` são placeholders: troque pelos IDs reais do YouTube.
- **Respostas rápidas**: `secoes[].respostas_rapidas` nos guias vira bloco `<dl>` visível na seção e `Question` no JSON-LD. Nas fichas, ITBI, prazo de registro, método Rw, gerador e blindagem são calculados em `seo/content.py`.

## Rotina de Access Logs (cPanel)

O cPanel arquiva os logs 1x por dia em `~/logs/marcoslima.com.br-ssl_log-<Mês>-<Ano>.gz`.
A tarefa agendada **"AltoPadrao - Coleta de Access Logs"** (diária, 11:30) roda `deploy/coletar_logs.cmd`:

1. baixa os arquivos por FTPS (`tools/coletar_logs.py`), filtra `/altopadrao/` e acumula em `logs/servidor/altopadrao.log`;
2. gera `logs/servidor/relatorio-AAAA-MM-DD.md` e `varredura.csv` (`tools/bot_report.py`):
   agentes, varredura de IA por seção (Core/Outdoor), URLs mais varridas e, para fichas e guias
   com pouca varredura, links contextuais de entrada, profundidade de clique e páginas que deveriam linkar para elas.

Credenciais: copie `.ftp.env.exemplo` para `.ftp.env` (ignorado pelo git). Log da execução: `logs/servidor/coleta.log`.
Reagendar: `deploy\agendar_coleta_logs.cmd`. Remover: `schtasks /Delete /TN "AltoPadrao - Coleta de Access Logs" /F`.

## Observações técnicas

- `Google-Extended` e `Applebot-Extended` são tokens de robots.txt, não User-Agents; o Google rastreia como Googlebot (inclusive para AI Overviews).
- User-Agent pode ser falsificado. Para auditoria rigorosa, valide IPs por DNS reverso / faixas publicadas por cada operador.
- Conteúdo tributário (holding, ITBI de Fortaleza, ITCD do Ceará, LC 214/2025) deve ser revisado por advogado antes de publicar; alíquotas mudam.

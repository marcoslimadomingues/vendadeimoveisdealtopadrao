# Imóveis de Alto Padrão em Fortaleza

Site HTML5 renderizado no servidor (Flask + Jinja2), exportado como site estático e publicado no
**GitHub Pages**. Sem JavaScript no navegador, sem banco de dados, sem hospedagem paga.

> **Só dado real.** Empresa, CRECI e CNPJ são reais; o m² por bairro vem do Sinduscon-CE e os tributos da
> legislação citada. O site não publica pessoas nem métrica própria. Os imóveis de demonstração ficam só em
> `tests/dados/` (os testes usam essa carteira). `python tools/pre_publicacao.py` lista o que falta;
> enquanto houver pendência, o site é publicado com `noindex`.

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
data/                   site, bairros, imóveis, guias, pilar, Sinduscon-CE, geo (OpenStreetMap)
templates/ static/      HTML5 semântico e CSS único (sem JS, sem webfont)
tools/                  build_pages, pre_publicacao, varrer_segredos, mapa, auditorias, teste_mobile
tests/                  testes de contrato (HTTP, JSON-LD, mobile, publicação, scanner); tests/dados: carteira de demonstração
.github/                workflow do Pages, Dependabot
```

## Conteúdo

- **Novo imóvel:** `data/imoveis.json` (`referencia`, `tecnico`, `amenidades` com as 3 obrigatórias).
  Preço/m², custos, ITBI e FAQ são calculados; o teste confere o resumo.
- **Trava de publicação:** imóvel só vai ao ar com `"publicacao_autorizada": true` (o booleano, não texto).
  Sem isso é rascunho: sem página, sem sitemap, sem `llms.txt`, e o checklist o lista. Guia que cita rascunho
  derruba o build com mensagem clara. Não grave nome de imobiliária, proprietário ou contrato nos dados: o
  repositório é público. Os 4 imóveis de demonstração levam `"ilustrativo": true`; o checklist os acusa até
  serem removidos.
- **Imóvel que saiu da carteira (sem exclusividade):** o imóvel pode ser vendido por terceiros ou retirado,
  então a página nunca diz que a venda foi nossa: só "não está mais disponível". Dois caminhos:
  1. **Manter a ficha (preferido, mantém prova social):** troque `status` para `"vendido"` (com `data_venda`) ou
     `"indisponivel"` (com `data_saida`); o resto da ficha fica. A URL segue em 200, indexável e no sitemap,
     com selo, FAQ de situação, imóveis parecidos e captação. JSON-LD: `Offer` com `availability`
     `SoldOut` (vendido) ou `OutOfStock` (indisponivel), sem preço. Opcionais: `dias_no_mercado` e, só em
     `vendido` e com autorização do proprietário, `preco_venda` + `preco_venda_autorizado: true` (mostra o
     valor e o % do preço anunciado; o percentual revela o valor, por isso segue a mesma autorização).
  2. **Redirecionar ao bairro:** acrescente `"redirecionar_para_bairro": true` (em `vendido`/`indisponivel`,
     com ou sem ficha). O GitHub Pages não faz 301: a página vira meta refresh imediato + `canonical` para
     `/bairros/<bairro>/` (o Google trata o refresh instantâneo como redirecionamento), sai do sitemap,
     do `llms.txt` e das listas, e continua exportada como arquivo. Guia que cita o imóvel precisa perder o
     vínculo (`imoveis_relacionados`), senão o build falha com mensagem clara.
- **Imóvel retirado (sem ficha):** `status: "vendido"` só com `codigo`, `titulo`, `bairro` e `data_venda`
  (sem `resumo`) devolve 404 real e sai do sitemap.
- **Trava de publicação:** imóvel só vai ao ar com `"publicacao_autorizada": true` (o booleano, não texto).
  Sem isso é rascunho: sem página, sem sitemap, sem `llms.txt`, e o checklist o lista. Guia que cita rascunho
  derruba o build com mensagem clara. Não grave nome de imobiliária, proprietário ou contrato nos dados: o
  repositório é público. Os 4 imóveis de demonstração levam `"ilustrativo": true`; o checklist os acusa até
  serem removidos.
- **Imóvel vendido (ficha mantida):** troque `status` para `"vendido"` e acrescente `data_venda`; o resto da
  ficha fica como está. A URL segue em 200, indexável e no sitemap, com selo "Vendido", sem preço anunciado,
  sem `Offer` no JSON-LD, FAQ de situação e alternativas. Opcionais: `dias_no_mercado` e, só com autorização
  do proprietário, `preco_venda` + `preco_venda_autorizado: true` (mostra o valor e o % do preço anunciado;
  o percentual revela o valor, por isso segue a mesma autorização). Guias que citam o imóvel continuam válidos.
- **Imóvel retirado (sem ficha):** `status: "vendido"` só com `codigo`, `titulo`, `bairro` e `data_venda`
  (sem `resumo`) devolve 404 real e sai do sitemap.
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

### Clusters de autoridade (pilar → satélites)

O pilar e seus satélites são o ativo permanente do site; a ficha de imóvel é a camada volátil por cima.

- **Satélite de pilar:** em `data/artigos.json`, `"pilar": "<slug-do-pilar>"` (e opcional `"url_sob_pilar": true`
  para a URL `/<pilar>/<slug>/`). Entra sozinho em sitemap e `llms.txt`, ganha o banner "Parte do pilar" e
  mostra os imóveis do pilar. Acrescente o slug em `guias` do pilar (`data/pilares.json`) para o link de volta.
- **Números só dos indicadores:** nos textos do satélite use `{m2:ID}`, `{m2ant:ID}`, `{ref:ID}`, `{acima:A:B}`,
  `{acimaant:A:B}`, `{dif:A:B}`, `{total:ID:AREA}`, `{veiculo:FONTE}`, `{dataf:FONTE}`. Token que aponta para
  indicador inexistente falha o build; valor, fonte e data nunca divergem do pilar.
- **Preço do m² por bairro (Cluster 2):** a fonte única é `data/sinduscon.json` (Sinduscon-CE, via imprensa,
  com URL, data e mês de referência). Ela define o `preco_m2` do bairro, o resumo, o título e a tabela de
  ranking das páginas `/bairros/<slug>/`, e abastece `/guias/preco-m2-por-bairro-fortaleza/`. Mês novo: troque
  os valores e `referencia`. Em guias com `"dados": "sinduscon"` use `{sm2:ID}`, `{sant:ID}`, `{svar:ID}`,
  `{sacima:ID}`, `{sdif:A:B}`, `{spct:A:B}`, `{spos:ID}`, `{sref}`, `{srefant}`, `{sveic}`, `{sdata}`, `{sfm}`,
  `{sfa}`; tabelas `"tabela_dinamica": "sinduscon"` e `"sinduscon_oferta"`. `"guia_pilar": "<slug>"` põe o
  guia como satélite de outro guia (banner "Parte do guia" e seção "Aprofunde este guia" no pilar).
  Só entra indicador publicado; prazo de venda e valorização por bairro não têm fonte e não aparecem nessas páginas.
- **Tributos (Clusters 3 e 4):** alíquotas e valores vêm de `data/site.json` (`itbi`: Sefin-Fortaleza; `itcd`: Lei
  estadual 15.812/2015 e valor da Ufirce da instrução normativa do ano). Em qualquer guia: `{t:itbi}`, `{t:itbi2}`,
  `{t:sfh}`, `{t:sfhteto}`, `{t:ufirce}`, `{t:ufirceano}`, `{u:N}` (N Ufirces em reais), `{ti:VALOR}`/`{ta:VALOR}`
  (ITBI geral e antecipado), `{ih|dd|dn:VALOR}` (ITCD herança, doação, nua-propriedade) e `{eh|ed|en:VALOR}`
  (alíquota efetiva). Tabelas: `"tabela_dinamica": "itbi" | "itcd_faixas" | "itcd_exemplos"`. **Todo ano:** troque
  `itcd.ufirce`/`ufirce_ano` e `itbi.sfh_teto`/`sfh_ano`; o teste confere o cálculo por um método independente.
- **Lacuna de dado:** marque `[PREENCHER: ...]`; o checklist o acusa e o site fica `noindex` até sair.
- `titulo_seo` (opcional) é o `<title>`; o `titulo` é o H1.

### Navegação até o imóvel (home)

Quem chega vê o imóvel primeiro: a vitrine fica logo depois da abertura e o dado de mercado vem abaixo. O botão
"Ver imóveis disponíveis" (→ `/imoveis/`) aparece na abertura, no fim da vitrine e depois dos guias. O cabeçalho é
`sticky`: no desktop fica inteiro à vista; no celular a linha da marca rola para fora (`top` negativo) e o menu, com
"Imóveis", permanece no topo. `scroll-padding-top` evita que âncoras (`#id`) fiquem sob o cabeçalho.

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

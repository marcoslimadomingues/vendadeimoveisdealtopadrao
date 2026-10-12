# Pendente: Geotag (SEO geográfico imobiliário)

Status: **aguardando execução** — registrado em 2026-09-30 a pedido do usuário ("guarde com o nome Geotag").

Origem: análise de um texto sobre "geotag para imobiliárias". Conclusão: geotag em foto (EXIF) não é
sinal de ranking e é risco de segurança no alto padrão; o que funciona é contexto geográfico explícito,
entidades de bairro/cidade, dados estruturados e Perfil da Empresa no Google.

## Já feito no pilar "Milha de ouro" (2026-10-12)

FEITO no pilar `/milha-de-ouro-fortaleza/` (escopo: só Meireles + Mucuripe):
- item 1 (mapa sem JS): SVG próprio gerado do OpenStreetMap — `tools/mapa_milha_de_ouro.py`;
- item 2 (coordenadas aproximadas): centro da faixa arredondado a 3 casas no `Place` do pilar;
- item 3 (pontos de referência): 12 marcos com posição e distância calculadas, nas páginas do pilar.
Falta replicar mapa/marcos nas páginas de cada bairro e ficha, e os itens 4 a 6.

## Itens a implementar

1. **Mapa** na ficha do imóvel e na página de bairro — sem JavaScript: imagem de mapa estática
   ou iframe OpenStreetMap (exige liberar `frame-src` na CSP do app e do `.htaccess`).
2. **Coordenadas aproximadas** (`GeoCoordinates`) em cada bairro (`Place`) e imóvel — usar centroide
   do bairro ou coordenadas arredondadas; **nunca o ponto exato** de imóvel de luxo.
3. **Pontos de referência reais** nas páginas de bairro: escolas, parques, praia, comércio, hospitais,
   com distâncias — dados verificados, nunca inventados.
4. **Página de cidade** como hub (ex.: `/fortaleza/` ou equivalente) ligando todos os bairros,
   completando a hierarquia Imóvel → Bairro → Cidade → Região.
5. **Fotos com nome de arquivo descritivo** por imóvel (`apartamento-alto-padrao-meireles-fortaleza.webp`),
   `alt` e legenda contextual; **remover EXIF/GPS** das fotos antes de publicar.
6. **Perfil da Empresa no Google** (fora do código): endereço real, categoria, telefone, site,
   fotos e avaliações — depende de verificação pelo Google.

## Cuidados

- Páginas de bairro precisam de conteúdo próprio (evitar *doorway pages*).
- Meta tags `geo.position` / `ICBM` são ignoradas pelo Google — não usar como entrega de valor.
- Dados estruturados de anúncio não geram rich result; valem para entendimento (Google e IAs).

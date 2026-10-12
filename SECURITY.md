# Política de segurança

## Como relatar uma vulnerabilidade

Use o relato privado do GitHub: aba **Security** → **Report a vulnerability** deste repositório.
Não abra *issue* pública com detalhes de uma falha, nem cole credenciais, tokens ou dados pessoais.

Se encontrar uma credencial exposta (no código, no histórico ou em um arquivo), relate pelo mesmo
canal e não a utilize.

## O que este repositório contém

- Código-fonte e conteúdo de um site estático. **Os dados de empresa, pessoas, preços e vídeos são de
  demonstração** enquanto `tools/pre_publicacao.py` acusar pendências.
- Nenhuma credencial é versionada: `.ftp.env`, `.env`, `logs/`, `build/` e `dist/` ficam fora do
  repositório (`.gitignore`). A publicação usa segredos do GitHub Actions.

## Práticas adotadas

- Varredura de segredos e *push protection* ativos (GitHub).
- Dependabot para `pip` e `github-actions`.
- Workflow com permissões mínimas (`contents: read`) e publicação em job separado, com ambiente
  `producao`.
- Cabeçalhos de segurança e CSP restritiva (`script-src 'none'`) no site gerado.

## Versões suportadas

Apenas a versão da branch `main`.

# Oportunizando: coletor automático de oportunidades

Como funciona: todo dia o GitHub roda o coletor, que lê os portais de `sources.json`,
gera `docs/oportunidades.json` e abre um pedido de revisão (pull request). Você confere
prazos e links, aprova, e a página (GitHub Pages) passa a mostrar os itens novos.

## Montagem (uma vez, ~20 minutos)
1. Crie uma conta e um repositório no GitHub e envie esta pasta inteira (inclusive `.github` e `docs`).
2. No repositório: Settings > Secrets and variables > Actions > New secret, nome `ANTHROPIC_API_KEY`, com a sua chave da API da Anthropic.
3. Em Settings > Pages, escolha a branch `main` e a pasta `/docs`. O endereço público da página aparece ali.
3b. Em Settings > Actions > General > Workflow permissions, marque "Allow GitHub Actions to create and approve pull requests".
4. Em Actions, rode "Coletar oportunidades" manualmente uma vez para testar.
5. `sources.json` já traz 7 páginas de partida. No primeiro teste, veja no log quais foram "puladas" (robots.txt) ou deram "erro" e troque por outras. Coloque seu e-mail em `UA` no `coletor.py`.

## Antes de usar de verdade
- Leia os termos de uso dos portais e prefira um acordo oficial (feed ou API) com CIEE e Sebrae.
- Nunca publique sem revisar: a extração automática pode errar prazos.
- A página só mostra o campo "Pergunte ao agente" dentro do Claude; fora dele, esse campo some.
- Custo: o GitHub Actions é gratuito para repositórios públicos; a API da Anthropic cobra por uso.

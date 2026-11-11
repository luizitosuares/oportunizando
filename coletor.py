#!/usr/bin/env python3
"""Coletor de oportunidades do Oportunizando.

Abre cada portal listado em sources.json com um navegador de verdade (Playwright),
espera o conteúdo dinâmico carregar, lê o texto e os links da página e gera
oportunidades.json no mesmo formato da base da página.

Dois modos:
  - Com ANTHROPIC_API_KEY: um modelo Claude estrutura o texto em itens (recomendado).
  - Sem chave: salva o texto bruto em saida/<fonte>.txt para revisão manual.

Uso:
  pip install playwright anthropic
  playwright install chromium
  export ANTHROPIC_API_KEY=...        # opcional
  python coletor.py
"""
import datetime
import json
import os
import re
import time
import urllib.robotparser
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright

UA = "RotaOportunidadesBot/0.1 (projeto de extensao; contato: SEU_EMAIL_AQUI)"
MODELO = os.environ.get("MODELO", "claude-haiku-5-5")
PAUSA_SEGUNDOS = 5  # educação com os servidores: uma página a cada 5 s
TIPOS = {"bolsa", "estagio", "aprendiz", "tecnico", "acesso", "pos", "emprego", "empreender", "curso"}
os.makedirs("saida", exist_ok=True)
os.makedirs("docs", exist_ok=True)

SCHEMA = (
    'Lista JSON de objetos com as chaves: t (título), k (bolsa|estagio|aprendiz|tecnico|acesso|pos|emprego|empreender|curso), '
    'n (lista com "em", "grad" e/ou "pos"), fim (AAAA-MM-DD ou null), loc (local), ing (0, 1 ou 2: '
    'nível de inglês exigido), x (descrição curta em português), u (link oficial da oportunidade), '
    's (nome da fonte), af (lista opcional com "publica", "negra", "baixa", "pcd" e/ou "mulher", SOMENTE se o texto disser que há vaga ou cota para esse público).'
)


def permitido(url: str) -> bool:
    """Respeita o robots.txt do site."""
    p = urlparse(url)
    rp = urllib.robotparser.RobotFileParser()
    rp.set_url(f"{p.scheme}://{p.netloc}/robots.txt")
    try:
        rp.read()
        return rp.can_fetch(UA, url)
    except Exception:
        return False  # na dúvida, não coleta


def renderizar(pagina, url: str):
    pagina.goto(url, wait_until="domcontentloaded", timeout=60000)
    try:  # espera o conteúdo dinâmico, mas sem travar em sites que nunca "assentam"
        pagina.wait_for_load_state("networkidle", timeout=15000)
    except Exception:
        pass
    for _ in range(6):  # rolagem para disparar carregamento sob demanda
        pagina.mouse.wheel(0, 3000)
        time.sleep(1.2)
    texto = pagina.inner_text("body")
    links = pagina.eval_on_selector_all(
        "a[href]", "els => els.map(e => [e.innerText.trim(), e.href]).filter(x => x[0])"
    )
    return texto, links


def estruturar(fonte: dict, texto: str, links: list):
    from anthropic import Anthropic

    cliente = Anthropic()
    hoje = datetime.date.today().isoformat()
    pedido = (
        f"Hoje é {hoje}. Fonte: {fonte['nome']} ({fonte['url']}).\n"
        f"Dica sobre esta fonte: {fonte.get('dica', 'nenhuma')}.\n"
        f"Extraia SOMENTE oportunidades de estudo, bolsa, estágio, aprendizagem ou capacitação que "
        f"apareçam no conteúdo abaixo. Nunca invente prazo, valor ou requisito: use null quando a "
        f"informação não estiver no texto. Ignore oportunidades com prazo anterior a hoje. "
        f"Para o campo u, use um link que esteja na lista de links. Responda apenas com: {SCHEMA}\n\n"
        f"TEXTO:\n{texto[:60000]}\n\nLINKS:\n{json.dumps(links[:300], ensure_ascii=False)}"
    )
    r = cliente.messages.create(
        model=MODELO, max_tokens=16000, messages=[{"role": "user", "content": pedido}]
    )
    # a resposta pode ter blocos de raciocínio antes do texto: junta só os blocos de texto
    texto = "".join(getattr(bl, "text", "") for bl in r.content if getattr(bl, "type", "") == "text")
    bruto = re.sub(r"^```(?:json)?|```$", "", texto.strip(), flags=re.M).strip()
    i, j = bruto.find("["), bruto.rfind("]")
    if i < 0:
        return []  # nada encontrado nesta página
    trecho = bruto[i : j + 1] if j > i else bruto[i:] + "]"
    try:
        return json.loads(trecho)
    except json.JSONDecodeError:
        # lista cortada ou com um item quebrado: aproveita os itens que vieram inteiros
        while True:
            k = trecho.rfind("},")
            if k < 0:
                return []
            try:
                return json.loads(trecho[: k + 1] + "]")
            except json.JSONDecodeError:
                trecho = trecho[: k + 1]


def main():
    fontes = json.load(open("sources.json", encoding="utf-8"))
    itens = []
    usa_ia = bool(os.environ.get("ANTHROPIC_API_KEY"))
    with sync_playwright() as pw:
        navegador = pw.chromium.launch()
        pagina = navegador.new_page(user_agent=UA)
        manual = os.environ.get("GITHUB_EVENT_NAME") == "workflow_dispatch" or not os.environ.get("GITHUB_ACTIONS")
        for f in fontes:
            if f.get("semanal") and not manual and datetime.date.today().weekday() != 0:
                continue  # fontes estáveis só rodam às segundas; o botão "Run workflow" roda todas
            if not permitido(f["url"]):
                print(f"[pulado] robots.txt não permite: {f['url']}")
                continue
            try:
                texto, links = renderizar(pagina, f["url"])
            except Exception as e:
                print(f"[erro] {f['nome']}: {e}")
                continue
            slug = re.sub(r"\W+", "_", f["nome"].lower())
            open(f"saida/{slug}.txt", "w", encoding="utf-8").write(texto)
            if usa_ia:
                try:
                    novos = estruturar(f, texto, links)
                    for it in novos:
                        it["coletado_em"] = datetime.date.today().isoformat()
                    itens += novos[: f.get("max", 40)]  # limite por fonte, para nenhuma dominar a base
                    print(f"[ok] {f['nome']}: {len(novos)} itens")
                except Exception as e:
                    print(f"[erro ao estruturar] {f['nome']}: {e}")
            else:
                print(f"[ok] {f['nome']}: texto salvo em saida/{slug}.txt")
            time.sleep(PAUSA_SEGUNDOS)
        navegador.close()
    if usa_ia:
        hoje = datetime.date.today().isoformat()
        vistos, finais = set(), []
        for it in itens:
            if not it.get("t") or not str(it.get("u", "")).startswith("http") or not isinstance(it.get("n"), list):
                continue  # item incompleto
            if it.get("k") not in TIPOS:
                continue  # tipo inválido
            it["n"] = [x for x in it["n"] if x in ("em", "grad", "pos")]
            if not it["n"]:
                continue  # sem etapa válida
            if isinstance(it.get("af"), list):
                it["af"] = [x for x in it["af"] if x in ("publica", "negra", "baixa", "pcd", "mulher")]
            chave = (it.get("u"), re.sub(r"\W+", "", str(it["t"]).lower()))
            if chave in vistos:
                continue  # repetido
            if it.get("fim") and it["fim"] < hoje:
                continue  # prazo já passou
            vistos.add(chave)
            finais.append(it)
        json.dump(finais, open("docs/oportunidades.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print(f"Pronto: {len(finais)} itens em docs/oportunidades.json. REVISE antes de publicar.")
        from collections import Counter
        por_tipo = Counter(it.get("k", "?") for it in finais)
        print("Por tipo:", dict(sorted(por_tipo.items(), key=lambda x: -x[1])))


if __name__ == "__main__":
    main()

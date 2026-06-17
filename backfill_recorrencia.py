"""
Detecta dores recorrentes agrupando itens similares por categoria.
Usa UMA chamada Claude por categoria (eficiente).
Gera campos: cluster_id (str), recorrencias (int)

Rode: python backfill_recorrencia.py
Para regenerar: python backfill_recorrencia.py --reset
"""
import json, time, sys, re
from collections import defaultdict

DADOS   = r"C:\WeeklySignals\dados.json"
from config import ANTHROPIC_API_KEY as API_KEY
RESET   = "--reset" in sys.argv

try:
    import anthropic
except ImportError:
    import subprocess, sys as _sys
    subprocess.check_call([_sys.executable, "-m", "pip", "install", "anthropic", "-q"])
    import anthropic

client = anthropic.Anthropic(api_key=API_KEY)

with open(DADOS, "r", encoding="utf-8") as f:
    dados = json.load(f)

if RESET:
    for s in dados["semanas"]:
        for i in s.get("items", []):
            i.pop("cluster_id", None)
            i.pop("recorrencias", None)
    print("Reset: cluster_id e recorrencias removidos.\n")

# Coleta todos os itens com índice global
all_items = []
for semana in dados["semanas"]:
    for item in semana.get("items", []):
        all_items.append(item)

# Agrupa por categoria
by_cat = defaultdict(list)
for idx, item in enumerate(all_items):
    by_cat[item.get("category","Outros")].append((idx, item))

print(f"Categorias: {len(by_cat)} | Itens: {len(all_items)}\n")

def clusterizar(categoria, itens):
    """
    Envia todos os itens da categoria para Claude.
    Retorna dict: idx -> cluster_label (str slug)
    """
    linhas = "\n".join(
        f"{i}. {item.get('summary') or item.get('title','')} [{item.get('semana','')}]"
        for i, (idx, item) in enumerate(itens)
    )
    prompt = (
        f"Você é analista de produto. Abaixo estão {len(itens)} pedidos de escolas "
        f"na categoria '{categoria}'.\n\n"
        f"Agrupe-os por dor central similar. Pedidos sobre o mesmo tema = mesmo grupo.\n"
        f"Seja conservador: só agrupe se a dor for realmente a mesma, não apenas parecida.\n\n"
        f"{linhas}\n\n"
        f"Responda em JSON puro, sem markdown, no formato:\n"
        f'[{{"i":0,"cluster":"slug-curto-da-dor"}}, {{"i":1,"cluster":"outro-slug"}}, ...]\n'
        f"O slug deve ser em português, com hífens, máximo 4 palavras. Ex: upload-provas-existentes"
    )
    msg = client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=1000,
        messages=[{"role": "user", "content": prompt}]
    )
    raw = msg.content[0].text.strip()
    # extrai o JSON mesmo se vier com texto ao redor
    match = re.search(r'\[.*\]', raw, re.DOTALL)
    if not match:
        return {}
    resultado = json.loads(match.group())
    return {r["i"]: r["cluster"] for r in resultado if "i" in r and "cluster" in r}

total_cats = len(by_cat)
for cat_num, (categoria, itens) in enumerate(by_cat.items(), 1):
    print(f"[{cat_num}/{total_cats}] {categoria} ({len(itens)} itens)...")
    try:
        mapa = clusterizar(categoria, itens)
        # conta quantos por cluster
        contagem = defaultdict(int)
        for i_local, cluster in mapa.items():
            contagem[cluster] += 1
        # aplica de volta
        for i_local, (idx_global, item) in enumerate(itens):
            cluster = mapa.get(i_local, f"{categoria.lower().replace(' ','_').replace('/','_')}_unico_{i_local}")
            item["cluster_id"]   = cluster
            item["recorrencias"] = contagem.get(cluster, 1)
        print(f"  {len(set(mapa.values()))} clusters encontrados")
    except Exception as e:
        print(f"  ERRO: {e}")
        for i_local, (idx_global, item) in enumerate(itens):
            item.setdefault("cluster_id", "sem_cluster")
            item.setdefault("recorrencias", 1)
    time.sleep(0.3)

with open(DADOS, "w", encoding="utf-8") as f:
    json.dump(dados, f, ensure_ascii=False, indent=2)

# Resumo dos mais recorrentes
from collections import Counter
clusters = [(i.get("cluster_id",""), i.get("recorrencias",1), i.get("category",""), i.get("summary") or i.get("title",""))
            for s in dados["semanas"] for i in s.get("items",[])]
seen = {}
for cid, rec, cat, titulo in clusters:
    if cid not in seen or rec > seen[cid][0]:
        seen[cid] = (rec, cat, titulo)

top = sorted(seen.items(), key=lambda x: -x[1][0])[:10]
print("\n🔁 Top 10 dores mais recorrentes:")
for cid, (rec, cat, titulo) in top:
    print(f"  ×{rec} [{cat}] {titulo[:80]}")

print(f"\n✓ Recorrências calculadas e salvas em dados.json")

"""
Reclassifica itens com category='Outros' usando Claude.
Rode: python backfill_categorias.py
"""
import json, time, sys

DADOS   = r"C:\WeeklySignals\dados.json"
from config import ANTHROPIC_API_KEY as API_KEY

CATEGORIAS = [
    "Avaliação / Simulados",
    "Conteúdo Didático / Autoria",
    "Analytics / Personalização",
    "Gestão Administrativa",
    "Engajamento Familiar",
    "Comunicação",
    "Criação de Conteúdo",
    "IA Pedagógica",
    "Plataforma / Integração",
    "Inclusão / Acessibilidade",
]

try:
    import anthropic
except ImportError:
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "anthropic", "-q"])
    import anthropic

client = anthropic.Anthropic(api_key=API_KEY)

with open(DADOS, "r", encoding="utf-8") as f:
    dados = json.load(f)

outros = [(s, i) for s in dados["semanas"] for i in s.get("items", []) if i.get("category") == "Outros"]
print(f"Itens 'Outros' para reclassificar: {len(outros)}\n")

cats_str = "\n".join(f"- {c}" for c in CATEGORIAS)

def classificar(title, context, suggestion):
    prompt = (
        f"Você é analista de produto educacional.\n\n"
        f"Classifique o pedido abaixo em UMA das categorias listadas.\n"
        f"Escolha a que melhor representa a dor central, não o contexto periférico.\n\n"
        f"Categorias disponíveis:\n{cats_str}\n\n"
        f"Título: {title}\n"
        f"Contexto: {context[:400]}\n"
        f"Sugestão: {suggestion[:200]}\n\n"
        f"Responda APENAS com o nome exato da categoria, sem explicação."
    )
    msg = client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=40,
        messages=[{"role": "user", "content": prompt}]
    )
    raw = msg.content[0].text.strip()
    # Garante que retornou uma categoria válida
    for cat in CATEGORIAS:
        if cat.lower() in raw.lower():
            return cat
    return raw  # retorna o que veio se não bater exato

done = 0
for semana, item in outros:
    nova = classificar(
        item.get("title", ""),
        item.get("context", ""),
        item.get("suggestion", "")
    )
    print(f"[{done+1}/{len(outros)}] {nova:<35} ← {item['title'][:60]}")
    item["category"] = nova
    done += 1
    time.sleep(0.12)

with open(DADOS, "w", encoding="utf-8") as f:
    json.dump(dados, f, ensure_ascii=False, indent=2)

print(f"\n✓ {done} itens reclassificados e salvos em dados.json")
print("Rode backfill_recorrencia.py para atualizar os clusters.")

"""
Gera campo 'impacto' (1-5) para cada item em dados.json.
5 = impacto crítico no negócio da escola | 1 = baixo impacto
Rode: python backfill_impacto.py
Para regenerar tudo: python backfill_impacto.py --reset
"""
import json, time, sys

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
            i.pop("impacto", None)
    print("Reset: todos os scores de impacto removidos.\n")

total    = sum(len(s.get("items",[])) for s in dados["semanas"])
pendente = sum(1 for s in dados["semanas"] for i in s.get("items",[]) if not i.get("impacto"))
print(f"Total: {total} | Para gerar: {pendente}\n")

def gerar_impacto(title, context, suggestion, category, priority):
    prompt = (
        f"Você é um analista sênior de produto educacional B2B.\n\n"
        f"Avalie o impacto de negócio deste pedido de escola numa escala de 1 a 5:\n"
        f"5 = Bloqueia operação central da escola ou afeta muitos professores/alunos diariamente\n"
        f"4 = Gera fricção significativa e perda de eficiência recorrente\n"
        f"3 = Melhoria relevante, mas escola consegue operar sem\n"
        f"2 = Nice-to-have, baixa urgência\n"
        f"1 = Impacto marginal ou muito específico\n\n"
        f"Categoria: {category}\n"
        f"Prioridade declarada: {priority}\n"
        f"Título: {title}\n"
        f"Contexto: {context[:500]}\n"
        f"Sugestão: {suggestion[:300]}\n\n"
        f"Responda APENAS com um número inteiro de 1 a 5, sem explicação."
    )
    msg = client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=5,
        messages=[{"role": "user", "content": prompt}]
    )
    raw = msg.content[0].text.strip()
    score = int(''.join(c for c in raw if c.isdigit())[:1] or "3")
    return max(1, min(5, score))

done = 0
for semana in dados["semanas"]:
    for item in semana.get("items", []):
        if item.get("impacto"):
            continue
        try:
            item["impacto"] = gerar_impacto(
                item.get("title",""),
                item.get("context",""),
                item.get("suggestion",""),
                item.get("category",""),
                item.get("priority","")
            )
            done += 1
            print(f"[{done}/{pendente}] impacto={item['impacto']} — {item['title'][:70]}")
        except Exception as e:
            print(f"ERRO '{item.get('title','')[:40]}': {e}")
            item["impacto"] = 3
        time.sleep(0.12)

with open(DADOS, "w", encoding="utf-8") as f:
    json.dump(dados, f, ensure_ascii=False, indent=2)

print(f"\n✓ {done} scores de impacto gerados e salvos.")

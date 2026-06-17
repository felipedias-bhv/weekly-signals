"""
Gera (ou regenera) campos 'summary' e 'summary_suggestion' para todos os itens.
Rode uma vez: python backfill_summary.py
Para regenerar tudo do zero: python backfill_summary.py --reset
"""
import json, time, sys

DADOS   = r"C:\WeeklySignals\dados.json"
from config import ANTHROPIC_API_KEY as API_KEY
RESET   = "--reset" in sys.argv

try:
    import anthropic
except ImportError:
    print("Instalando anthropic...")
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "anthropic", "-q"])
    import anthropic

client = anthropic.Anthropic(api_key=API_KEY)

with open(DADOS, "r", encoding="utf-8") as f:
    dados = json.load(f)

if RESET:
    for s in dados["semanas"]:
        for i in s.get("items", []):
            i.pop("summary", None)
            i.pop("summary_suggestion", None)
    print("Reset: todos os summaries removidos.\n")

total = sum(len(s.get("items",[])) for s in dados["semanas"])
pend_dor = sum(1 for s in dados["semanas"] for i in s.get("items",[]) if not i.get("summary"))
pend_sug = sum(1 for s in dados["semanas"] for i in s.get("items",[]) if not i.get("summary_suggestion"))
print(f"Total: {total} itens | Dor pendente: {pend_dor} | Sugestão pendente: {pend_sug}\n")

def call(prompt):
    msg = client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=100,
        messages=[{"role": "user", "content": prompt}]
    )
    return msg.content[0].text.strip().strip('"').rstrip('.')

def prompt_dor(title, context, suggestion):
    return (
        f"Você é um analista de produto que escreve para um painel executivo.\n\n"
        f"Leia o pedido abaixo na íntegra e escreva UMA frase em português que:\n"
        f"- Diga o que a escola NÃO consegue fazer hoje (a dor real)\n"
        f"- Seja compreensível para quem nunca viu esse pedido antes\n"
        f"- Seja direta: sem 'a escola precisa', sem 'foi solicitado', sem rodeios\n"
        f"- Máximo 120 car
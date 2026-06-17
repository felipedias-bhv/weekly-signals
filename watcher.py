"""
Weekly Signals Watcher — sem API, extração direta do PDF
Suporta PDFs com múltiplas semanas (ex: Q1 - WeeklySignals.pdf) e PDFs de semana única.
Formatos PT-BR (School: / Priority:) e EN (escola no texto / Prioritization:)
"""

import os
import re
import json
import time
import hashlib
import subprocess
import sys
from datetime import datetime

# ============================================================
PASTA_PDFS    = r"C:\WeeklySignals\pdfs"
ARQUIVO_DADOS = r"C:\WeeklySignals\dados.json"
INTERVALO_SEGUNDOS = 30
# ============================================================

CATEGORY_RULES = [
    (["neurodivergent", "neurodivergente", "pei", "inclusion", "inclusão", "inclusao",
      "accessibility", "acessibilidade", "adaptation", "adaptação", "pictogram", "pictograma",
      "tea", "autis"], "Inclusão / Acessibilidade"),
    (["simulad", "vestibular", "enem", "rubric", "rubrica", "assessment", "avaliação",
      "avaliacao", "grading", "criteria", "critério", "correction", "correção", "prova",
      "exam", "test", "questão", "questao", "gabarito"], "Avaliação / Simulados"),
    (["didactic material", "material didático", "authoring", "autoria", "editorial",
      "textbook", "livro didático", "curriculum identity", "identidade curricular",
      "digital material", "instructional material", "studio", "confessional",
      "conteúdo próprio", "material proprio"], "Conteúdo Didático / Autoria"),
    (["analytics", "learning trail", "trilha", "personaliz", "student profile",
      "perfil do aluno", "dashboard pedagógico", "relatório pedagógico"], "Analytics / Personalização"),
    (["certificate", "certificado", "historic", "histórico", "historico",
      "boletim", "report card", "academic record", "survey", "enquete", "admin",
      "administrativo", "directory", "diretório", "calendar", "calendário",
      "attendance", "grade horária", "timetable", "horário"], "Gestão Administrativa"),
    (["famil", "album", "photo", "foto", "guardian", "responsável", "responsavel",
      "parent", "engajamento familiar", "diary", "diário de classe"], "Engajamento Familiar"),
    (["communication", "comunicação", "comunicacao", "message", "mensagem",
      "notification", "notificação", "chat", "conversa"], "Comunicação"),
    (["slide", "presentation", "apresentação", "apresentacao", "redesign",
      "template", "modelo", "gamif", "interativ"], "Criação de Conteúdo"),
    (["ia ", "i.a.", "artificial intel", "inteligência artificial", "ai assist",
      "assistente", "gpt", "llm"], "IA Pedagógica"),
    (["integração", "integration", "totvs", "erp", "sistema", "unificad",
      "plataforma única", "single platform"], "Plataforma / Integração"),
]

def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)

def instalar_pymupdf():
    log("Instalando pymupdf (apenas na primeira vez)...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "pymupdf", "-q"])
    log("pymupdf instalado.")

def extrair_texto_pdf(caminho):
    try:
        import fitz
    except ImportError:
        instalar_pymupdf()
        import fitz
    doc = fitz.open(caminho)
    texto = "\n".join(page.get_text() for page in doc)
    doc.close()
    return texto

def classify(title, context=""):
    text = (title + " " + context).lower()
    for keywords, cat in CATEGORY_RULES:
        if any(k in text for k in keywords):
            return cat
    return "Outros"

def parse_priority(raw):
    raw = raw.lower().strip()
    if "very high" in raw or "muito alta" in raw:                            return "Muito Alta"
    if "medium–high" in raw or "medium-high" in raw or "média-alta" in raw: return "Média-Alta"
    if "low–medium" in raw or "low-medium" in raw or "low" in raw:          return "Média"
    if "high" in raw or "alta" in raw:                                       return "Alta"
    if "medium" in raw or "média" in raw or "media" in raw:                 return "Média"
    return "Média"  # desconhecido → Média, não Alta

def extract_school_from_text(text):
    """Tenta extrair nome da escola do texto do bloco (formato EN)"""
    m = re.search(r'\(([^)]+(?:–|-)[^)]+)\)', text)
    if m:
        parts = re.split(r'–|-', m.group(1))
        return parts[0].strip()
    m = re.search(r'[Ss]chool:\s*(.+)', text)
    if m:
        return m.group(1).strip()
    return "Escola não identificada"

def extrair_itens(texto):
    """Extrai itens numerados de um bloco de texto (uma semana)"""
    blocos = re.split(r'\n(?=\d+\.[ \t])', texto)
    items = []

    for bloco in blocos:
        title_m = re.match(r'\d+\.\s*(.+)', bloco.strip())
        if not title_m:
            continue
        title = title_m.group(1).strip()

        priority_m = re.search(
            r'(?:Priority|Prioritization|Prioridade|Priorização):\s*(.+)',
            bloco, re.IGNORECASE
        )
        priority = parse_priority(priority_m.group(1)) if priority_m else "Alta"

        school_m = re.search(r'School:\s*(.+)', bloco)
        if school_m:
            school = school_m.group(1).strip()
        else:
            school = extract_school_from_text(bloco)

        # Contexto / Dor — cabeçalho em linha própria (sem dois-pontos)
        ctx_m = re.search(
            r'(?:Problema\s*/\s*Contexto|Contexto(?:\s*e\s*Dor)?|Problema|Problem(?:\s*/\s*Context)?|Context)\s*\n([\s\S]+?)(?=\n\s*(?:Sugest|School\'s|Suggestion|Priority|Prioridade|Prioriza|Habilidade|Escola:|Persona:|\d+\.\s))',
            bloco, re.IGNORECASE
        )
        if not ctx_m:
            # fallback: "Contexto: texto na mesma linha"
            ctx_m = re.search(
                r'(?:Contexto|Problema)[:\s]+(.+?)(?=\n\s*(?:Sugest|School|Priority|Prioridade|\d+\.)|\Z)',
                bloco, re.IGNORECASE | re.DOTALL
            )
        context = " ".join(ctx_m.group(1).split()) if ctx_m else ""
        context = context[:800]

        # Sugestão da escola — idem
        sug_m = re.search(
            r'(?:Sugest[aã]o\s+da\s+[Ee]scola|School\'s\s+Suggestion|Suggestion)\s*\n([\s\S]+?)(?=\n\s*(?:Priority|Prioridade|Prioriza|Habilidade|Escola:|Persona:|Data:|\d+\.\s))',
            bloco, re.IGNORECASE
        )
        if not sug_m:
            sug_m = re.search(
                r'(?:Sugest[aã]o)[:\s]+(.+?)(?=\n\s*(?:Priority|Prioridade|\d+\.)|\Z)',
                bloco, re.IGNORECASE | re.DOTALL
            )
        suggestion = " ".join(sug_m.group(1).split()) if sug_m else ""
        suggestion = suggestion[:800]

        category = classify(title, bloco[:400])

        items.append({
            "title":      title,
            "school":     school,
            "priority":   priority,
            "category":   category,
            "context":    context,
            "suggestion": suggestion,
        })

    return items

# ---------------------------------------------------------------
#  NOVO: divide PDF multi-semana em seções por "Week XX – DD.MM"
# ---------------------------------------------------------------
def split_semanas(texto, nome_arquivo):
    """
    Retorna lista de (nome_semana, texto_semana).
    Se encontrar cabeçalhos "Week XX – DD.MM" divide o PDF em seções.
    Se não encontrar, trata como semana única.
    """
    # Padrão: "Week 07 – 06.02" ou "Week 07 - 06/02" (com traço normal ou em-dash)
    pattern = re.compile(r'Week\s+(\d+)\s*[–\-]\s*([\d.\/]+)', re.IGNORECASE)
    matches = list(pattern.finditer(texto))

    if not matches:
        # Formato desconhecido — semana única derivada do nome do arquivo
        base = os.path.splitext(nome_arquivo)[0]
        nome = base.replace("_", " ").replace("-", " – ")
        return [(nome, texto)]

    # Divide em seções
    semanas = []
    for i, m in enumerate(matches):
        week_num = m.group(1).zfill(2)
        week_date = m.group(2)
        nome = f"Week {week_num} – {week_date}"
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(texto)
        semanas.append((nome, texto[start:end]))

    return semanas

def carregar_dados():
    if os.path.exists(ARQUIVO_DADOS):
        with open(ARQUIVO_DADOS, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"semanas": [], "pdfs_processados": [], "updated_at": ""}

def salvar_dados(dados):
    os.makedirs(os.path.dirname(ARQUIVO_DADOS), exist_ok=True)
    dados["updated_at"] = datetime.now().isoformat()
    with open(ARQUIVO_DADOS, "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, indent=2)

def hash_arquivo(caminho):
    h = hashlib.md5()
    with open(caminho, "rb") as f:
        h.update(f.read())
    return h.hexdigest()

def processar_pdf(caminho, nome_arquivo, dados):
    log(f"Processando: {nome_arquivo}")
    try:
        texto = extrair_texto_pdf(caminho)
        if not texto.strip():
            log(f"  PDF sem texto legível.")
            dados["pdfs_processados"].append(hash_arquivo(caminho))
            salvar_dados(dados)
            return

        semanas_extraidas = split_semanas(texto, nome_arquivo)
        total_itens = 0

        for nome_semana, texto_semana in semanas_extraidas:
            itens = extrair_itens(texto_semana)
            if not itens:
                log(f"  '{nome_semana}' — nenhum item encontrado, pulando.")
                continue

            semanas = dados["semanas"]
            existente = next((s for s in semanas if s["name"] == nome_semana), None)
            if existente:
                existente["items"] = itens
                log(f"  '{nome_semana}' atualizada — {len(itens)} itens")
            else:
                semanas.append({"name": nome_semana, "items": itens})
                log(f"  '{nome_semana}' adicionada — {len(itens)} itens")

            total_itens += len(itens)

        dados["pdfs_processados"].append(hash_arquivo(caminho))
        salvar_dados(dados)
        log(f"  Total: {len(semanas_extraidas)} semanas, {total_itens} itens — salvo em {ARQUIVO_DADOS}")

    except Exception as e:
        log(f"  ERRO: {e}")
        import traceback; traceback.print_exc()

def monitorar():
    os.makedirs(PASTA_PDFS, exist_ok=True)
    log("=" * 56)
    log("Weekly Signals Watcher iniciado")
    log(f"Pasta PDFs : {PASTA_PDFS}")
    log(f"Dados JSON : {ARQUIVO_DADOS}")
    log(f"Intervalo  : {INTERVALO_SEGUNDOS}s  —  Ctrl+C para parar")
    log("=" * 56)

    dados = carregar_dados()
    dados["pdfs_processados"] = []   # força reprocessamento

    while True:
        try:
            arquivos = sorted(f for f in os.listdir(PASTA_PDFS) if f.lower().endswith(".pdf"))
            for nome in arquivos:
                caminho = os.path.join(PASTA_PDFS, nome)
                h = hash_arquivo(caminho)
                if h not in dados["pdfs_processados"]:
                    processar_pdf(caminho, nome, dados)
                    dados = carregar_dados()
        except KeyboardInterrupt:
            log("Encerrado.")
            break
        except Exception as e:
            log(f"Erro no loop: {e}")

        time.sleep(INTERVALO_SEGUNDOS)

if __name__ == "__main__":
    monitorar()

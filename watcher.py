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
from config import ANTHROPIC_API_KEY
# ============================================================

_anthropic_client = None

def get_anthropic():
    global _anthropic_client
    if _anthropic_client:
        return _anthropic_client
    try:
        import anthropic
    except ImportError:
        log("Instalando anthropic...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "anthropic", "-q"])
        import anthropic
    _anthropic_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    return _anthropic_client

def gerar_impacto(title, context, suggestion, category, priority):
    try:
        client = get_anthropic()
        prompt = (
            f"Avalie o impacto de negócio deste pedido de escola (1-5):\n"
            f"5=bloqueia operação central | 4=fricção recorrente | 3=relevante | 2=nice-to-have | 1=marginal\n"
            f"Categoria: {category} | Prioridade: {priority}\n"
            f"Título: {title}\nContexto: {context[:400]}\n"
            f"Responda APENAS com um número de 1 a 5."
        )
        msg = client.messages.create(
            model="claude-haiku-4-5",
            max_tokens=5,
            messages=[{"role": "user", "content": prompt}]
        )
        raw = msg.content[0].text.strip()
        score = int(''.join(c for c in raw if c.isdigit())[:1] or "3")
        return max(1, min(5, score))
    except Exception as e:
        log(f"  impacto API erro: {e}")
        return 3

def gerar_summary_suggestion(title, suggestion, context=""):
    try:
        client = get_anthropic()
        prompt = (
            f"Você é um analista de produto que escreve para um painel executivo.\n\n"
            f"Leia a sugestão da escola abaixo na íntegra e escreva UMA frase em português que:\n"
            f"- Diga o que a escola quer que seja construído ou melhorado (a solução proposta)\n"
            f"- Seja compreensível para quem nunca viu esse pedido antes\n"
            f"- Seja direta e objetiva: sem 'a escola sugere', sem 'foi solicitado', sem rodeios\n"
            f"- Máximo 120 caracteres\n"
            f"- Não copie o título, não comece com 'A escola'\n\n"
            f"Título: {title}\n"
            f"Sugestão da escola: {suggestion}\n"
            f"Contexto: {context}\n\n"
            f"Responda apenas com a frase, sem aspas, sem ponto final."
        )
        msg = client.messages.create(
            model="claude-haiku-4-5",
            max_tokens=100,
            messages=[{"role": "user", "content": prompt}]
        )
        return msg.content[0].text.strip().strip('"').rstrip('.')
    except Exception as e:
        log(f"  summary_suggestion API erro: {e}")
        return ""

def gerar_summary(title, context, suggestion=""):
    try:
        client = get_anthropic()
        prompt = (
            f"Você é um analista de produto que escreve para um painel executivo.\n\n"
            f"Leia o pedido abaixo na íntegra e escreva UMA frase em português que:\n"
            f"- Diga o que a escola NÃO consegue fazer hoje (a dor real)\n"
            f"- Seja compreensível para quem nunca viu esse pedido antes\n"
            f"- Seja direta: sem 'a escola precisa', sem 'foi solicitado', sem rodeios\n"
            f"- Máximo 120 caracteres\n"
            f"- Não copie o título, não comece com 'A escola'\n\n"
            f"Título: {title}\n"
            f"Contexto: {context}\n"
            f"Sugestão da escola: {suggestion}\n\n"
            f"Responda apenas com a frase, sem aspas, sem ponto final."
        )
        msg = client.messages.create(
            model="claude-haiku-4-5",
            max_tokens=100,
            messages=[{"role": "user", "content": prompt}]
        )
        return msg.content[0].text.strip().strip('"').rstrip('.')
    except Exception as e:
        log(f"  summary API erro: {e}")
        return ""

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

CATEGORIAS_VALIDAS = [
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
_cats_str = "\n".join(f"- {c}" for c in CATEGORIAS_VALIDAS)

def classify_com_claude(title, context):
    try:
        client = get_anthropic()
        prompt = (
            f"Você é analista de produto educacional.\n\n"
            f"Classifique o pedido abaixo em UMA das categorias listadas.\n"
            f"Escolha a que melhor representa a dor central.\n\n"
            f"Categorias disponíveis:\n{_cats_str}\n\n"
            f"Título: {title}\n"
            f"Contexto: {context[:400]}\n\n"
            f"Responda APENAS com o nome exato da categoria, sem explicação."
        )
        msg = client.messages.create(
            model="claude-haiku-4-5",
            max_tokens=40,
            messages=[{"role": "user", "content": prompt}]
        )
        raw = msg.content[0].text.strip()
        for cat in CATEGORIAS_VALIDAS:
            if cat.lower() in raw.lower():
                return cat
        # Se não bateu exato mas retornou algo, tenta match parcial
        for cat in CATEGORIAS_VALIDAS:
            first_word = cat.split()[0].lower()
            if first_word in raw.lower():
                return cat
        return "Plataforma / Integração"  # fallback absoluto
    except Exception as e:
        log(f"  classify_com_claude erro: {e}")
        return "Plataforma / Integração"

def classify(title, context=""):
    text = (title + " " + context).lower()
    for keywords, cat in CATEGORY_RULES:
        if any(k in text for k in keywords):
            return cat
    # Não encontrou por keywords → usa Claude
    return classify_com_claude(title, context)

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

        summary            = gerar_summary(title, context, suggestion)
        time.sleep(0.15)
        summary_suggestion = gerar_summary_suggestion(title, suggestion, context)
        time.sleep(0.15)
        impacto            = gerar_impacto(title, context, suggestion, category, priority)
        time.sleep(0.15)

        items.append({
            "title":              title,
            "school":             school,
            "priority":           priority,
            "category":           category,
            "context":            context,
            "suggestion":         suggestion,
            "summary":            summary,
            "summary_suggestion": summary_suggestion,
            "impacto":            impacto,
            "cluster_id":         "",
            "recorrencias":       1,
        })

    return items

# ---------------------------------------------------------------
#  divide PDF multi-semana em seções por "Week XX – DD.MM"
# ---------------------------------------------------------------
def split_semanas(texto, nome_arquivo):
    pattern = re.compile(r'Week\s+(\d+)\s*[–\-]\s*([\d.\/]+)', re.IGNORECASE)
    matches = list(pattern.finditer(texto))
    if not matches:
        base = os.path.splitext(nome_arquivo)[0]
        nome = base.replace("_", " ").replace("-", " – ")
        return [(nome, texto)]
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
    dados["pdfs_processados"] = []
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

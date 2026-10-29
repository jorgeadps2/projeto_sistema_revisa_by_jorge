"""Leitura local e conservadora de envelopes de pagamento em PDF."""
import math
import re
import unicodedata


MONTH_NAMES = (
    'janeiro', 'fevereiro', 'marco', 'abril', 'maio', 'junho',
    'julho', 'agosto', 'setembro', 'outubro', 'novembro', 'dezembro',
)


def normalized(value):
    text = ''.join(
        character for character in unicodedata.normalize('NFKD', value)
        if not unicodedata.combining(character))
    return ' '.join(re.findall(r'[a-z0-9]+', text.lower()))


def extract_payroll_values(pages, employees, year, month):
    results = {}
    problems = []
    found_period = False
    names = {}
    for employee in employees:
        key = normalized(employee['name'])
        names.setdefault(key, []).append(employee)
    amount_pattern = r'(?:r\$\s*)?((?:\d{1,3}(?:\.\d{3})+|\d+),\d{2})(?!\d)'
    for page_number, text in enumerate(pages, 1):
        plain = ''.join(
            character for character in unicodedata.normalize('NFKD', text)
            if not unicodedata.combining(character)).lower()
        periods = {
            (int(match[1]), MONTH_NAMES.index(match[0]) + 1)
            for match in re.findall(
                r'\b(' + '|'.join(MONTH_NAMES) + r')\s*(?:de\s+|[/\-]\s*|\s+)(20\d{2})\b', plain)
        }
        periods.update(
            (int(y), int(m)) for m, y in re.findall(
                r'(?<![\d/])(\d{2})/(20\d{2})(?![\d/])', plain))
        if (year, month) not in periods:
            problems.append(f'Página {page_number}: competência não confirmada para o mês escolhido.')
            continue
        found_period = True
        flat = normalized(text)
        matches = []
        for name, candidates in names.items():
            for match in re.finditer(r'(?<!\w)' + re.escape(name) + r'(?!\w)', flat):
                matches.append((match.start(), candidates))
        employee_ids = {employee['id'] for _, candidates in matches for employee in candidates}
        # Um envelope por página evita atribuir valores a outro funcionário.
        if len(employee_ids) != 1:
            problems.append(f'Página {page_number}: funcionário ausente, ambíguo ou mais de um envelope.')
            continue
        employee = next(employee for _, candidates in matches for employee in candidates)
        labels = list(re.finditer(
            r'\b(?:(?:valor|total)\s+liquido|liquido\s+(?:a\s+receber|do\s+mes))\b', plain))
        amounts = []
        for label in labels:
            tail = plain[label.end():]
            match = re.match(r'[\s:=>.\-]*' + amount_pattern, tail)
            if match:
                amounts.append(round(float(match[1].replace('.', '').replace(',', '.')), 2))
        if not amounts or len(set(amounts)) != 1:
            problems.append(f'Página {page_number}: valor líquido não identificado com segurança.')
            continue
        amount = amounts[0]
        if not math.isfinite(amount) or amount < 0:
            problems.append(f'Página {page_number}: valor líquido inválido.')
            continue
        employee_id = employee['id']
        if employee_id in results and results[employee_id]['amount'] != amount:
            raise ValueError('O PDF contém valores líquidos diferentes para o mesmo funcionário.')
        results[employee_id] = dict(employee_id=employee_id, name=employee['name'], amount=amount)
    if not found_period:
        raise ValueError('Não foi possível confirmar a competência do PDF. Nenhum valor foi importado.')
    if not results:
        raise ValueError('Nenhum envelope pôde ser identificado com segurança.\n' + '\n'.join(problems))
    return list(results.values()), problems


def read_payroll_pdf(path, employees, year, month):
    from pypdf import PdfReader
    reader = PdfReader(path)
    if reader.is_encrypted:
        raise ValueError('O PDF está protegido por senha. Use uma cópia desbloqueada.')
    pages = [page.extract_text(extraction_mode='layout') or '' for page in reader.pages]
    if not any(text.strip() for text in pages):
        raise ValueError('O PDF não contém texto extraível. PDFs digitalizados precisam de OCR antes da importação.')
    return extract_payroll_values(pages, employees, year, month)

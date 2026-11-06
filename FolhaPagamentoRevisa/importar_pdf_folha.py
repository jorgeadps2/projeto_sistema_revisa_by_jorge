"""Leitura local e conservadora de envelopes de pagamento em PDF."""
import math
import os
import re
import tempfile
import unicodedata
from copy import copy


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
                continue
            line_start = plain.rfind('\n', 0, label.start()) + 1
            preceding = re.findall(
                amount_pattern, plain[line_start:label.start()])
            if preceding:
                amounts.append(round(
                    float(preceding[-1].replace('.', '').replace(',', '.')), 2))
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


def employee_page_indexes(pages, employees):
    names = {}
    for employee in employees:
        key = normalized(employee['name'])
        names.setdefault(key, []).append(employee)
    page_indexes = {}
    for page_number, text in enumerate(pages, 1):
        flat = normalized(text)
        matches = []
        for name, candidates in names.items():
            if name:
                matches.extend(
                    (match.start(), candidates)
                    for match in re.finditer(
                        r'(?<!\w)' + re.escape(name) + r'(?!\w)', flat))
        employee_ids = {
            employee['id']
            for _, candidates in matches
            for employee in candidates
        }
        if len(employee_ids) > 1:
            raise ValueError(
                f'Página {page_number}: mais de um colaborador foi identificado; '
                'não é seguro anexar esta página.')
        if employee_ids:
            employee_id = next(iter(employee_ids))
            page_indexes.setdefault(employee_id, []).append(page_number - 1)
    return page_indexes


def append_employee_report_pages(
        report_path, payslip_path, employee_id, employees, year, month):
    from pypdf import PdfReader, PdfWriter
    from pypdf import Transformation
    from pypdf.generic import RectangleObject

    report = PdfReader(report_path)
    if report.is_encrypted:
        raise ValueError('O relatório externo está protegido por senha.')
    report_pages = [page.extract_text() or '' for page in report.pages]
    entries, _ = extract_payroll_values(report_pages, employees, year, month)
    if employee_id not in {entry['employee_id'] for entry in entries}:
        raise ValueError(
            'Não encontrei no relatório externo um envelope válido para este colaborador.')
    indexes = employee_page_indexes(report_pages, employees).get(employee_id)
    if not indexes:
        raise ValueError(
            'Não encontrei as páginas deste colaborador no relatório externo.')

    payslip = PdfReader(payslip_path)
    if payslip.is_encrypted:
        raise ValueError('O demonstrativo de pagamento gerado está protegido por senha.')
    writer = PdfWriter()
    writer.append(payslip)

    def report_page_for_employee(index):
        report_page = report.pages[index]
        employee_name = next(
            employee['name'] for employee in employees
            if employee['id'] == employee_id)
        if normalized(employee_name) and normalized(
                report_pages[index]).count(normalized(employee_name)) >= 2:
            left, bottom, right, top = map(float, report_page.mediabox)
            report_page = copy(report_page)
            single_copy_box = RectangleObject(
                (left, bottom + (top - bottom) / 2, right, top))
            report_page.mediabox = single_copy_box
            report_page.cropbox = single_copy_box
        return report_page

    footer_text = 'documento confidencial - uso administrativo'
    page_number_pattern = re.compile(r'página\s+\d+\s+de\s+\d+', re.IGNORECASE)
    available_pages = []
    for page_index, page in enumerate(writer.pages):
        lowest_text_y = None

        def find_lowest_text(text, content_matrix, text_matrix, __, ___):
            nonlocal lowest_text_y
            clean_text = ' '.join(text.split()).lower()
            if (not clean_text or footer_text in clean_text
                    or page_number_pattern.fullmatch(clean_text)):
                return
            text_y = (
                float(content_matrix[2]) * float(text_matrix[4])
                + float(content_matrix[3]) * float(text_matrix[5])
                + float(content_matrix[5]))
            lowest_text_y = (
                text_y if lowest_text_y is None
                else min(lowest_text_y, text_y))

        page.extract_text(visitor_text=find_lowest_text)
        page_height = float(page.mediabox.height)
        content_bottom = lowest_text_y if lowest_text_y is not None else page_height * 0.7
        available_height = content_bottom - 16 - 36
        available_pages.append((available_height, page_index))

    available_height, target_index = max(available_pages)
    if available_height <= 0:
        raise ValueError(
            'Não há espaço abaixo do demonstrativo de pagamento para incluir o relatório externo '
            'na mesma página.')

    report_page = report_page_for_employee(indexes[0])
    source_box = report_page.cropbox
    source_left, source_bottom, source_right, source_top = map(float, source_box)
    source_width = source_right - source_left
    source_height = source_top - source_bottom
    target_page = writer.pages[target_index]
    target_width = float(target_page.mediabox.width)
    side_margin = 12 * 72 / 25.4
    scale = min(
        (target_width - 2 * side_margin) / source_width,
        available_height / source_height)
    if scale <= 0:
        raise ValueError('Não foi possível dimensionar o relatório externo.')
    translate_x = (target_width - source_width * scale) / 2 - source_left * scale
    translate_y = 36 - source_bottom * scale
    target_page.merge_transformed_page(
        report_page,
        Transformation().scale(scale).translate(translate_x, translate_y))

    for index in indexes[1:]:
        writer.add_page(report_page_for_employee(index))

    output_directory = os.path.dirname(os.path.abspath(payslip_path))
    file_descriptor, temporary_path = tempfile.mkstemp(
        prefix='demonstrativo_pagamento_anexo_', suffix='.pdf', dir=output_directory)
    os.close(file_descriptor)
    try:
        with open(temporary_path, 'wb') as output:
            writer.write(output)
        os.replace(temporary_path, payslip_path)
    except Exception:
        if os.path.exists(temporary_path):
            os.remove(temporary_path)
        raise

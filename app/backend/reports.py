"""Generación de informes PDF profesionales para DoctorPlagio."""
from __future__ import annotations

import io
import re
from datetime import datetime
from typing import Any

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    KeepTogether,
)


CONFIDENCE_ES = {
    "low": "bajo",
    "medium": "medio",
    "high": "alto",
    "very high": "muy alto",
    "very_high": "muy alto",
    "bajo": "bajo",
    "medio": "medio",
    "alto": "alto",
    "muy alto": "muy alto",
    "muy_alto": "muy alto",
}

LABEL_ES = {
    "low": "bajo",
    "intermediate": "intermedio",
    "intermedio": "intermedio",
    "high": "alto",
    "bajo": "bajo",
    "alto": "alto",
}

CLASSIFICATION_ES = {
    "probable_copy": "copia probable",
    "probable_paraphrase": "paráfrasis probable",
    "same_topic": "mismo tema",
    "weak_match": "coincidencia débil",
    "unrelated": "sin relación",
    "exact_copy": "copia exacta",
    "near_verbatim": "copia casi literal",
    "paraphrase": "paráfrasis",
    "legitimate_quote": "cita legítima",
    "reference": "referencia",
}

# Claves internas de las métricas -> etiquetas visibles en español.
METRIC_LABELS_ES = {
    "characters": "Caracteres",
    "words": "Palabras",
    "sentences": "Oraciones",
    "paragraphs": "Párrafos",
    "connector_total": "Total de conectores",
    "connector_counts": "Conteo de conectores",
    "sentence_length_mean_words": "Longitud media de las oraciones (palabras)",
    "sentence_length_std_words": "Desviación estándar de la longitud de las oraciones",
    "sentence_length_cv": "Coeficiente de variación de la longitud de las oraciones",
    "paragraph_length_mean_words": "Longitud media de los párrafos (palabras)",
    "lexical_diversity": "Diversidad léxica",
    "repeated_bigram_rate": "Tasa de bigramas repetidos",
    "repeated_trigram_rate": "Tasa de trigramas repetidos",
    "repeated_words": "Palabras repetidas",
    # Nombres ya traducidos por versiones nuevas.
    "caracteres": "Caracteres",
    "palabras": "Palabras",
    "oraciones": "Oraciones",
    "parrafos": "Párrafos",
    "total_conectores": "Total de conectores",
    "conteo_conectores": "Conteo de conectores",
    "longitud_media_oraciones_palabras": "Longitud media de las oraciones (palabras)",
    "desviacion_estandar_longitud_oraciones_palabras": "Desviación estándar de la longitud de las oraciones",
    "coeficiente_variacion_longitud_oraciones": "Coeficiente de variación de la longitud de las oraciones",
    "longitud_media_parrafos_palabras": "Longitud media de los párrafos (palabras)",
    "diversidad_lexica": "Diversidad léxica",
    "tasa_bigrama_repetido": "Tasa de bigramas repetidos",
    "tasa_trigrama_repetido": "Tasa de trigramas repetidos",
    "palabras_repetidas": "Palabras repetidas",
}

# Traducción de textos técnicos que pueden llegar desde resultados históricos.
ENGLISH_PHRASES_ES = {
    "evidence coverage, not probability of plagiarism":
        "El porcentaje representa la cobertura de fragmentos con evidencia de coincidencia; no debe interpretarse como una probabilidad matemática de plagio.",
    "evidence coverage, not probability of plagiarism.":
        "El porcentaje representa la cobertura de fragmentos con evidencia de coincidencia; no debe interpretarse como una probabilidad matemática de plagio.",
}


def _es(value: Any, mapping: dict[str, str], default: str = "N/D") -> str:
    if value is None:
        return default
    key = str(value).strip().lower()
    return mapping.get(key, str(value))


def _pct(value: Any, digits: int = 2) -> str:
    try:
        x = float(value)
        if abs(x) <= 1.000001:
            x *= 100
        return f"{x:.{digits}f}%"
    except (TypeError, ValueError):
        return "N/D"


def _safe(text: Any) -> str:
    """Escapa texto para Paragraph de ReportLab."""
    s = "" if text is None else str(text)

    # Sustituye frases técnicas en inglés que no deben aparecer
    # en ninguna parte visible del informe.
    for english, spanish in ENGLISH_PHRASES_ES.items():
        s = s.replace(english, spanish)

    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _short(text: Any, limit: int = 500) -> str:
    s = str(text or "").strip()
    return s if len(s) <= limit else s[: limit - 1] + "…"


def _metric_label(key: Any) -> str:
    """Devuelve siempre una etiqueta de métrica en español."""
    key_text = str(key)
    if key_text in METRIC_LABELS_ES:
        return METRIC_LABELS_ES[key_text]
    return key_text.replace("_", " ").capitalize()


def _metric_value(value: Any) -> str:
    """Formatea valores de métricas sin traducir el contenido del documento."""
    if isinstance(value, float):
        return f"{value:.4f}"
    if isinstance(value, dict):
        if not value:
            return "Ninguno"
        return "; ".join(
            f"{key}: {val}"
            for key, val in value.items()
        )
    if isinstance(value, list):
        return ", ".join(str(item) for item in value) if value else "Ninguno"
    return str(value)


def _styles():
    styles = getSampleStyleSheet()

    styles.add(
        ParagraphStyle(
            name="DPTitle",
            parent=styles["Title"],
            alignment=TA_CENTER,
            fontSize=21,
            leading=25,
            spaceAfter=10,
        )
    )

    styles.add(
        ParagraphStyle(
            name="DPSubtitle",
            parent=styles["Normal"],
            alignment=TA_CENTER,
            fontSize=9.5,
            textColor=colors.grey,
            spaceAfter=12,
        )
    )

    styles.add(
        ParagraphStyle(
            name="DPH1",
            parent=styles["Heading1"],
            fontSize=14,
            leading=17,
            spaceBefore=10,
            spaceAfter=6,
            keepWithNext=True,
        )
    )

    styles.add(
        ParagraphStyle(
            name="DPH2",
            parent=styles["Heading2"],
            fontSize=11.5,
            leading=14,
            spaceBefore=7,
            spaceAfter=4,
            keepWithNext=True,
        )
    )

    styles.add(
        ParagraphStyle(
            name="DPBody",
            parent=styles["BodyText"],
            fontSize=8.8,
            leading=12,
            spaceAfter=4,
        )
    )

    styles.add(
        ParagraphStyle(
            name="DPSmall",
            parent=styles["BodyText"],
            fontSize=7.5,
            leading=9.5,
            textColor=colors.grey,
        )
    )

    styles.add(
        ParagraphStyle(
            name="DPWarning",
            parent=styles["BodyText"],
            fontSize=8.2,
            leading=11,
            borderWidth=0.6,
            borderColor=colors.grey,
            borderPadding=7,
            spaceBefore=6,
            spaceAfter=7,
        )
    )

    return styles


def _header_footer(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 7.5)
    canvas.setFillColor(colors.grey)
    canvas.drawString(
        1.6 * cm,
        1.0 * cm,
        "DoctorPlagio — Informe de análisis",
    )
    canvas.drawRightString(
        19.4 * cm,
        1.0 * cm,
        f"Página {doc.page}",
    )
    canvas.restoreState()


def build_pdf_report(
    results: dict[str, Any],
    filename: str = "documento",
) -> bytes:
    """
    Construye el informe PDF usando exactamente el resultado ya calculado.

    La composición utiliza flujo continuo, sin saltos de página forzados.
    Esto evita páginas casi vacías cuando una sección contiene poco contenido.
    """

    styles = _styles()
    buf = io.BytesIO()

    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        rightMargin=1.6 * cm,
        leftMargin=1.6 * cm,
        topMargin=1.45 * cm,
        bottomMargin=1.5 * cm,
        title="Informe de análisis — DoctorPlagio",
        author="DoctorPlagio",
        allowSplitting=1,
    )

    story = []

    ai = results.get("ai_analysis") or {}
    meta = results.get("analysis_meta") or {}
    history = results.get("version_history") or {}

    # ============================================================
    # ENCABEZADO
    # ============================================================

    story.append(Spacer(1, 0.7 * cm))
    story.append(
        Paragraph(
            "DoctorPlagio",
            styles["DPTitle"],
        )
    )
    story.append(
        Paragraph(
            "Informe profesional de análisis documental",
            styles["DPSubtitle"],
        )
    )

    story.append(
        Paragraph(
            f"<b>Documento:</b> {_safe(filename)}",
            styles["DPBody"],
        )
    )

    story.append(
        Paragraph(
            f"<b>Fecha del informe:</b> "
            f"{_safe(datetime.now().strftime('%d/%m/%Y %H:%M'))}",
            styles["DPBody"],
        )
    )

    if history.get("version_number"):
        story.append(
            Paragraph(
                f"<b>Versión analizada:</b> "
                f"{_safe(history.get('version_number'))}",
                styles["DPBody"],
            )
        )

    # ============================================================
    # 1. RESUMEN
    # ============================================================

    story.append(
        Paragraph(
            "1. Resumen ejecutivo",
            styles["DPH1"],
        )
    )

    summary_data = [
        ["Indicador", "Resultado"],
        [
            "Porcentaje de plagio (cobertura de evidencia)",
            _pct(results.get("plagiarism_percentage")),
        ],
        [
            "Contenido con características compatibles con IA",
            _pct(ai.get("ai_score")),
        ],
        [
            "Características humanas estimadas",
            _pct(ai.get("human_score")),
        ],
        [
            "Nivel de confianza",
            _safe(_es(ai.get("confidence"), CONFIDENCE_ES)),
        ],
        [
            "Predominio de características",
            _safe(_es(ai.get("label"), LABEL_ES)),
        ],
    ]

    t = Table(
        summary_data,
        colWidths=[10 * cm, 7 * cm],
        repeatRows=1,
        hAlign="LEFT",
    )

    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eeeeee")),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#bbbbbb")),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("FONTSIZE", (0, 0), (-1, -1), 8.3),
                ("LEFTPADDING", (0, 0), (-1, -1), 7),
                ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )

    story.append(t)
    story.append(Spacer(1, 0.22 * cm))

    story.append(
        Paragraph(
            "<b>Importante:</b> esta estimación analiza características "
            "lingüísticas y estilísticas; no demuestra autoría ni determina "
            "quién escribió el documento.",
            styles["DPWarning"],
        )
    )

    if ai.get("reasoning"):
        story.append(
            Paragraph(
                "Explicación global",
                styles["DPH2"],
            )
        )
        story.append(
            Paragraph(
                _safe(ai.get("reasoning")),
                styles["DPBody"],
            )
        )

    # ============================================================
    # 2. SIMILITUD
    # ============================================================

    story.append(
        Paragraph(
            "2. Análisis de similitud y coincidencias",
            styles["DPH1"],
        )
    )

    interpretation = meta.get("interpretation")

    if not interpretation:
        interpretation = (
            "El porcentaje representa la cobertura de fragmentos con "
            "evidencia de coincidencia según el motor configurado; "
            "no debe interpretarse como una probabilidad matemática "
            "de plagio."
        )

    story.append(
        Paragraph(
            _safe(interpretation),
            styles["DPBody"],
        )
    )

    details = results.get("details") or []

    if details:
        rows = [
            ["#", "Fuente", "Clasificación", "Evidencia"]
        ]

        for i, detail in enumerate(details, 1):
            classification = _es(
                detail.get("classification"),
                CLASSIFICATION_ES,
            )

            rows.append(
                [
                    str(i),
                    _safe(
                        _short(
                            detail.get("source", "Desconocida"),
                            90,
                        )
                    ),
                    _safe(classification),
                    _pct(detail.get("evidence_score")),
                ]
            )

        t = Table(
            rows,
            colWidths=[
                0.7 * cm,
                7.5 * cm,
                5.0 * cm,
                3.0 * cm,
            ],
            repeatRows=1,
            hAlign="LEFT",
        )

        t.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eeeeee")),
                    ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#c0c0c0")),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 7.5),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ]
            )
        )

        story.append(t)
        story.append(Spacer(1, 0.18 * cm))

        story.append(
            Paragraph(
                "Fragmentos relevantes",
                styles["DPH2"],
            )
        )

        for i, detail in enumerate(details, 1):
            classification = _es(
                detail.get("classification"),
                CLASSIFICATION_ES,
            )

            story.append(
                Paragraph(
                    f"<b>{i}. {_safe(classification)} — "
                    f"{_safe(detail.get('source', 'Desconocida'))}</b>",
                    styles["DPBody"],
                )
            )

            if detail.get("fragment"):
                story.append(
                    Paragraph(
                        f"<b>Fragmento:</b> "
                        f"{_safe(_short(detail.get('fragment'), 900))}",
                        styles["DPBody"],
                    )
                )

            if detail.get("matched_fragment"):
                story.append(
                    Paragraph(
                        f"<b>Fragmento de referencia:</b> "
                        f"{_safe(_short(detail.get('matched_fragment'), 900))}",
                        styles["DPBody"],
                    )
                )

    # Si no hay coincidencias, la interpretación anterior ya comunica el resultado.

    # ============================================================
    # 3. IA
    # ============================================================

    global_metrics = ai.get("global_metrics") or {}

    # El encabezado, la explicación y la tabla de métricas se mantienen
    # juntos cuando caben en la página siguiente. Esto evita que un título
    # quede aislado al final de una página.
    section3_block = [
        Paragraph(
            "3. Análisis de características de IA",
            styles["DPH1"],
        ),
        Paragraph(
            "El motor combina métricas lingüísticas determinísticas "
            "con análisis local mediante GPT-OSS. La puntuación expresa "
            "la presencia estimada de características compatibles con "
            "generación o asistencia automática, no una atribución de autoría.",
            styles["DPBody"],
        ),
    ]

    if global_metrics:
        section3_block.append(
            Paragraph(
                "Métricas globales",
                styles["DPH2"],
            )
        )

        metric_rows = [["Métrica", "Valor"]]

        for key, value in global_metrics.items():
            metric_rows.append(
                [
                    _safe(_metric_label(key)),
                    _safe(_metric_value(value)),
                ]
            )

        mt = Table(
            metric_rows,
            colWidths=[10 * cm, 7 * cm],
            repeatRows=1,
            hAlign="LEFT",
        )

        mt.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eeeeee")),
                    ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#c0c0c0")),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 7.8),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 6),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ]
            )
        )

        section3_block.append(mt)

    story.append(KeepTogether(section3_block))

    chapters = ai.get("chapters") or []

    if chapters:
        story.append(
            Paragraph(
                "3.1 Resultados por capítulo/sección",
                styles["DPH2"],
            )
        )

        rows = [
            [
                "Capítulo / sección",
                "Páginas",
                "IA",
                "Humano",
                "Confianza",
            ]
        ]

        for chapter in chapters:
            pages = chapter.get("pages") or []

            if pages:
                page_text = (
                    f"{pages[0]}–{pages[-1]}"
                    if len(pages) > 1
                    else str(pages[0])
                )
            else:
                page_text = "N/D"

            rows.append(
                [
                    _safe(
                        _short(
                            chapter.get(
                                "chapter",
                                "Documento",
                            ),
                            70,
                        )
                    ),
                    _safe(page_text),
                    _pct(chapter.get("ai_score")),
                    _pct(chapter.get("human_score")),
                    _safe(
                        _es(
                            chapter.get("confidence"),
                            CONFIDENCE_ES,
                        )
                    ),
                ]
            )

        ct = Table(
            rows,
            colWidths=[
                7.2 * cm,
                2.4 * cm,
                2.3 * cm,
                2.3 * cm,
                2.8 * cm,
            ],
            repeatRows=1,
            hAlign="LEFT",
        )

        ct.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eeeeee")),
                    ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#c0c0c0")),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 7.5),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ]
            )
        )

        story.append(ct)

        story.append(
            Paragraph(
                "3.2 Detalle de capítulos y segmentos",
                styles["DPH2"],
            )
        )

        for chapter in chapters:
            confidence = _es(
                chapter.get("confidence"),
                CONFIDENCE_ES,
            )

            story.append(
                Paragraph(
                    f"<b>{_safe(chapter.get('chapter', 'Documento'))}</b> — "
                    f"IA {_pct(chapter.get('ai_score'))}; "
                    f"humano {_pct(chapter.get('human_score'))}; "
                    f"confianza {_safe(confidence)}",
                    styles["DPBody"],
                )
            )

            if chapter.get("reasoning"):
                story.append(
                    Paragraph(
                        f"<b>Análisis:</b> "
                        f"{_safe(chapter.get('reasoning'))}",
                        styles["DPBody"],
                    )
                )

            for signal in (chapter.get("ai_signals") or [])[:8]:
                story.append(
                    Paragraph(
                        f"• <b>Señal compatible con IA:</b> "
                        f"{_safe(signal)}",
                        styles["DPBody"],
                    )
                )

            for signal in (chapter.get("human_signals") or [])[:8]:
                story.append(
                    Paragraph(
                        f"• <b>Señal compatible con intervención humana:</b> "
                        f"{_safe(signal)}",
                        styles["DPBody"],
                    )
                )

    if ai.get("recurring_patterns"):
        story.append(
            Paragraph(
                "3.3 Patrones transversales",
                styles["DPH2"],
            )
        )

        for item in ai["recurring_patterns"]:
            story.append(
                Paragraph(
                    f"• {_safe(item)}",
                    styles["DPBody"],
                )
            )

    # ============================================================
    # 4. EVOLUCIÓN
    # ============================================================

    story.append(
        Paragraph(
            "4. Evolución del documento",
            styles["DPH1"],
        )
    )

    if history:
        status = history.get("status", "N/D")
        status_es = {
            "new_analysis": "nueva evaluación",
            "same_document": "documento sin cambios",
            "reused": "resultado reutilizado",
            "modified": "documento modificado",
        }.get(str(status).strip().lower(), status)

        story.append(
            Paragraph(
                f"<b>Estado:</b> {_safe(status_es)}",
                styles["DPBody"],
            )
        )

        if history.get("similarity_to_previous") is not None:
            story.append(
                Paragraph(
                    f"<b>Similitud con la versión anterior:</b> "
                    f"{_pct(history.get('similarity_to_previous'))}",
                    styles["DPBody"],
                )
            )

        changes = history.get("changes") or []

        if changes:
            story.append(
                Paragraph(
                    f"<b>Cambios detectados:</b> {len(changes)}",
                    styles["DPBody"],
                )
            )

            for i, change in enumerate(changes, 1):
                change_type = str(
                    change.get(
                        "change_type",
                        "MODIFIED",
                    )
                ).lower()

                change_labels = {
                    "modified": "modificado",
                    "added": "agregado",
                    "removed": "eliminado",
                    "unchanged": "sin cambios",
                }

                change_es = change_labels.get(
                    change_type,
                    change.get("change_type", "modificado"),
                )

                story.append(
                    Paragraph(
                        f"<b>{i}. {_safe(change_es)}</b>",
                        styles["DPBody"],
                    )
                )

                if change.get("old_text"):
                    story.append(
                        Paragraph(
                            f"<b>Antes:</b> "
                            f"{_safe(_short(change['old_text'], 700))}",
                            styles["DPBody"],
                        )
                    )

                if change.get("new_text"):
                    story.append(
                        Paragraph(
                            f"<b>Ahora:</b> "
                            f"{_safe(_short(change['new_text'], 700))}",
                            styles["DPBody"],
                        )
                    )

        elif history.get("reused_previous_evaluation"):
            story.append(
                Paragraph(
                    "El contenido coincide exactamente con una evaluación "
                    "anterior; se reutilizó el resultado registrado y no "
                    "se ejecutó nuevamente el análisis costoso.",
                    styles["DPBody"],
                )
            )
        else:
            story.append(
                Paragraph(
                    "No se registraron cambios de versión para esta evaluación.",
                    styles["DPBody"],
                )
            )

    else:
        story.append(
            Paragraph(
                "No hay información de versiones disponible.",
                styles["DPBody"],
            )
        )

    # ============================================================
    # 5. METODOLOGÍA
    # ============================================================

    story.append(
        Paragraph(
            "5. Metodología y limitaciones",
            styles["DPH1"],
        )
    )

    methodology = (
        ai.get("methodology")
        or meta.get("ai_method")
        or "No disponible."
    )

    story.append(
        Paragraph(
            f"<b>Método:</b> {_safe(methodology)}",
            styles["DPBody"],
        )
    )

    for item in (ai.get("limitations") or []):
        story.append(
            Paragraph(
                f"• {_safe(item)}",
                styles["DPBody"],
            )
        )

    story.append(
        Paragraph(
            "<b>Nota metodológica:</b> los resultados dependen de los "
            "modelos, corpus, métricas y umbrales configurados en esta "
            "versión de DoctorPlagio. Deben interpretarse como evidencia "
            "para revisión, no como una prueba automática de autoría.",
            styles["DPWarning"],
        )
    )

    doc.build(
        story,
        onFirstPage=_header_footer,
        onLaterPages=_header_footer,
    )

    return buf.getvalue()


def generate_plagiarism_report(results):
    """Compatibilidad con el código histórico que esperaba un diccionario."""
    if isinstance(results, dict):
        return results
    return {"results": results}

"""Genera el PDF del resumen del simulador Aikiu."""

from pathlib import Path
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
)
from reportlab.lib.enums import TA_LEFT, TA_CENTER

OUT = Path(__file__).parent / "resumen_simulador_aikiu.pdf"

# ── Colores ──────────────────────────────────────────────────────────────────
AZUL      = colors.HexColor("#1a3a5c")
AZUL_CLARO = colors.HexColor("#2d6a9f")
GRIS      = colors.HexColor("#f4f6f9")
GRIS_OSC  = colors.HexColor("#6b7280")
VERDE     = colors.HexColor("#15803d")
ROJO      = colors.HexColor("#b91c1c")

def build():
    doc = SimpleDocTemplate(
        str(OUT), pagesize=A4,
        leftMargin=2.5*cm, rightMargin=2.5*cm,
        topMargin=2.5*cm, bottomMargin=2.5*cm,
    )

    styles = getSampleStyleSheet()

    def style(name, **kw):
        s = ParagraphStyle(name, parent=styles["Normal"], **kw)
        return s

    h1   = style("h1", fontSize=22, textColor=AZUL, spaceAfter=6, spaceBefore=0, fontName="Helvetica-Bold")
    h2   = style("h2", fontSize=14, textColor=AZUL_CLARO, spaceAfter=4, spaceBefore=14, fontName="Helvetica-Bold")
    h3   = style("h3", fontSize=11, textColor=AZUL, spaceAfter=3, spaceBefore=8, fontName="Helvetica-Bold")
    body = style("body", fontSize=10, leading=15, spaceAfter=4, textColor=colors.HexColor("#111827"))
    code = style("code", fontSize=9, leading=13, fontName="Courier", textColor=colors.HexColor("#1e293b"),
                 backColor=GRIS, borderPadding=6, spaceAfter=6, spaceBefore=4)
    sub  = style("sub", fontSize=9, textColor=GRIS_OSC, spaceAfter=2)
    bold = style("bold", fontSize=10, fontName="Helvetica-Bold", leading=14)

    story = []

    # ── Portada ───────────────────────────────────────────────────────────────
    story.append(Spacer(1, 1*cm))
    story.append(Paragraph("Simulador de Conversación", h1))
    story.append(Paragraph("Aikiu — Documentación técnica", style("sub2", fontSize=13, textColor=AZUL_CLARO, fontName="Helvetica")))
    story.append(Spacer(1, 0.3*cm))
    story.append(HRFlowable(width="100%", thickness=2, color=AZUL_CLARO))
    story.append(Spacer(1, 0.5*cm))

    # ── Qué es ────────────────────────────────────────────────────────────────
    story.append(Paragraph("¿Qué es y para qué sirve?", h2))
    story.append(Paragraph(
        "Un sistema de prueba automática que simula conversaciones entre <b>Marta</b> (la usuaria) "
        "y <b>Aikiu</b> (el bot) sin tocar el bot de producción. Permite iterar el perfil de Aikiu "
        "rápidamente, midiendo calidad con criterios objetivos.",
        body
    ))
    story.append(Paragraph(
        "<b>El problema que resuelve:</b> antes, para saber si un cambio en el perfil mejoraba la "
        "conversación, había que probarlo manualmente con el bot real. Ahora se pueden correr "
        "decenas de iteraciones automáticas en minutos.",
        body
    ))

    # ── Arquitectura ──────────────────────────────────────────────────────────
    story.append(Paragraph("Arquitectura: dos agentes", h2))

    arch_data = [
        ["Agente A — Marta (Gemini)", "Agente B — Aikiu (cascada LLMs)"],
        [
            "Simula a la usuaria usando\npersonas/marta.md\n\nModelo: gemini-2.5-flash",
            "Simula al bot usando\nperfil_simulacion.md\n\nGroq → Gemini → OpenRouter"
        ],
    ]
    arch_table = Table(arch_data, colWidths=[7.5*cm, 7.5*cm])
    arch_table.setStyle(TableStyle([
        ("BACKGROUND",   (0,0), (-1,0), AZUL),
        ("TEXTCOLOR",    (0,0), (-1,0), colors.white),
        ("FONTNAME",     (0,0), (-1,0), "Helvetica-Bold"),
        ("FONTSIZE",     (0,0), (-1,0), 10),
        ("ALIGN",        (0,0), (-1,-1), "CENTER"),
        ("VALIGN",       (0,0), (-1,-1), "MIDDLE"),
        ("FONTSIZE",     (0,1), (-1,-1), 9),
        ("BACKGROUND",   (0,1), (-1,-1), GRIS),
        ("ROWBACKGROUNDS",(0,1),(-1,-1),[GRIS]),
        ("GRID",         (0,0), (-1,-1), 0.5, colors.HexColor("#d1d5db")),
        ("TOPPADDING",   (0,0), (-1,-1), 8),
        ("BOTTOMPADDING",(0,0), (-1,-1), 8),
        ("LEFTPADDING",  (0,0), (-1,-1), 10),
        ("RIGHTPADDING", (0,0), (-1,-1), 10),
    ]))
    story.append(arch_table)
    story.append(Spacer(1, 0.3*cm))
    story.append(Paragraph(
        "Los logs de cada conversación se guardan en <font name='Courier'>simulador/logs/</font> "
        "como archivos <font name='Courier'>.jsonl</font>. El evaluador los lee y decide si actualizar el perfil.",
        body
    ))

    # ── Cascada LLMs ──────────────────────────────────────────────────────────
    story.append(Paragraph("Cascada de LLMs (fallback automático)", h2))
    story.append(Paragraph(
        "Si un proveedor falla por límite diario de tokens (429) o error de servidor, "
        "el simulador pasa automáticamente al siguiente sin interrumpir la conversación. "
        "Cada turno del log registra qué backend respondió.",
        body
    ))

    llm_data = [
        ["#", "Proveedor", "Modelo", "Límite gratis"],
        ["1", "Groq",       "llama-3.3-70b-versatile",        "100k tokens/día"],
        ["2", "Gemini",     "gemini-2.5-flash",               "1.500 req/día"],
        ["3", "OpenRouter", "openai/gpt-oss-120b:free",        "compartido"],
        ["4", "OpenRouter", "google/gemma-4-31b-it:free",      "compartido"],
        ["5", "OpenRouter", "nvidia/nemotron-120b:free",       "compartido"],
    ]
    llm_table = Table(llm_data, colWidths=[1*cm, 2.8*cm, 7*cm, 4.2*cm])
    llm_table.setStyle(TableStyle([
        ("BACKGROUND",   (0,0), (-1,0), AZUL),
        ("TEXTCOLOR",    (0,0), (-1,0), colors.white),
        ("FONTNAME",     (0,0), (-1,0), "Helvetica-Bold"),
        ("FONTSIZE",     (0,0), (-1,-1), 9),
        ("ALIGN",        (0,0), (0,-1), "CENTER"),
        ("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.white, GRIS]),
        ("GRID",         (0,0), (-1,-1), 0.5, colors.HexColor("#d1d5db")),
        ("TOPPADDING",   (0,0), (-1,-1), 6),
        ("BOTTOMPADDING",(0,0), (-1,-1), 6),
        ("LEFTPADDING",  (0,0), (-1,-1), 8),
        ("FONTNAME",     (0,1), (0,-1), "Helvetica-Bold"),
        ("TEXTCOLOR",    (0,1), (0,-1), AZUL_CLARO),
    ]))
    story.append(llm_table)

    # ── Evaluador ─────────────────────────────────────────────────────────────
    story.append(Paragraph("Evaluador: 7 criterios gerontológicos", h2))
    story.append(Paragraph(
        "Después de cada simulación, Gemini evalúa la conversación de 0 a 10 en cada criterio. "
        "<b>El perfil solo se actualiza si el score supera al anterior.</b> "
        "Si baja, se descarta. Antes de sobrescribir, hace backup automático.",
        body
    ))

    crit_data = [
        ["Criterio", "Qué mide"],
        ["Voseo rioplatense",       "¿Usó 'querés/tenés/podés'? ¿Cero tuteo neutro?"],
        ["Ratio preguntas",         "¿Máximo una pregunta por turno?"],
        ["Autorrevelación",         "¿Aikiu aportó datos/anécdotas propias antes de preguntar?"],
        ["Respuesta a vulnerabilidad", "¿Priorizó salud/dolor sobre temas triviales?"],
        ["Sin eco/espejo",          "¿Evitó repetir textualmente las palabras de Marta?"],
        ["Cierre de negativas",     "¿Ante un 'no', cerró con calidez sin repreguntar?"],
        ["Tono gerontológico",      "¿Fue cálido, no infantilizante, no enciclopédico?"],
    ]
    crit_table = Table(crit_data, colWidths=[4.5*cm, 10.5*cm])
    crit_table.setStyle(TableStyle([
        ("BACKGROUND",   (0,0), (-1,0), AZUL),
        ("TEXTCOLOR",    (0,0), (-1,0), colors.white),
        ("FONTNAME",     (0,0), (-1,0), "Helvetica-Bold"),
        ("FONTSIZE",     (0,0), (-1,-1), 9),
        ("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.white, GRIS]),
        ("GRID",         (0,0), (-1,-1), 0.5, colors.HexColor("#d1d5db")),
        ("TOPPADDING",   (0,0), (-1,-1), 6),
        ("BOTTOMPADDING",(0,0), (-1,-1), 6),
        ("LEFTPADDING",  (0,0), (-1,-1), 8),
        ("FONTNAME",     (0,1), (0,-1), "Helvetica-Bold"),
    ]))
    story.append(crit_table)

    # ── Loop ──────────────────────────────────────────────────────────────────
    story.append(Paragraph("Loop de iteraciones", h2))
    story.append(Paragraph(
        "El orquestador corre N ciclos de <b>simular → evaluar → (si mejora) actualizar perfil</b>. "
        "Al final, <font name='Courier'>perfil_simulacion.md</font> tiene la mejor versión encontrada.",
        body
    ))
    story.append(Paragraph(
        "python simulador/loop.py 10 marta 10\n# 10 iteraciones, persona marta, 10 turnos",
        code
    ))

    # ── Resultados ────────────────────────────────────────────────────────────
    story.append(Paragraph("Resultados obtenidos", h2))
    story.append(Paragraph(
        "Se corrieron 3 rondas (5 + 5 + 10 iteraciones). Mejores scores alcanzados:",
        body
    ))

    res_data = [
        ["Score", "Mejora principal aplicada al perfil"],
        ["10.0/10", "Énfasis en autorrevelación y estructura anti-interrogatorio"],
        ["9.7/10",  "Reglas de cierre de negativas y estructura ideal de respuesta"],
        ["9.0/10",  "Anti-eco explícito + respuesta a preguntas directas de Marta"],
    ]
    res_table = Table(res_data, colWidths=[2.5*cm, 12.5*cm])
    res_table.setStyle(TableStyle([
        ("BACKGROUND",   (0,0), (-1,0), AZUL),
        ("TEXTCOLOR",    (0,0), (-1,0), colors.white),
        ("FONTNAME",     (0,0), (-1,0), "Helvetica-Bold"),
        ("FONTSIZE",     (0,0), (-1,-1), 9),
        ("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.white, GRIS]),
        ("GRID",         (0,0), (-1,-1), 0.5, colors.HexColor("#d1d5db")),
        ("TOPPADDING",   (0,0), (-1,-1), 6),
        ("BOTTOMPADDING",(0,0), (-1,-1), 6),
        ("LEFTPADDING",  (0,0), (-1,-1), 8),
        ("FONTNAME",     (0,1), (0,-1), "Helvetica-Bold"),
        ("TEXTCOLOR",    (0,1), (0,-1), VERDE),
        ("ALIGN",        (0,0), (0,-1), "CENTER"),
    ]))
    story.append(res_table)

    # ── Archivos ──────────────────────────────────────────────────────────────
    story.append(Paragraph("Estructura de archivos", h2))
    story.append(Paragraph(
        "simulador/\n"
        "├── simulador.py          # motor (2 agentes + cascada LLMs)\n"
        "├── evaluador.py          # scoring + actualización del perfil\n"
        "├── loop.py               # orquestador N iteraciones\n"
        "├── perfil_simulacion.md  # perfil de prueba (no tocar a mano)\n"
        "├── scores.jsonl          # historial de scores\n"
        "├── logs/                 # conversaciones completas (.jsonl)\n"
        "└── personas/\n"
        "    └── marta.md          # perfil detallado de la usuaria simulada",
        code
    ))
    story.append(Paragraph(
        "Los logs, scores y el perfil de simulación están en <font name='Courier'>.gitignore</font> "
        "— son artefactos locales. Solo se commitean los scripts y <font name='Courier'>marta.md</font>.",
        sub
    ))

    doc.build(story)
    print(f"PDF generado: {OUT}")

if __name__ == "__main__":
    build()

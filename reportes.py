"""
Módulo de generación de reportes PDF y despacho de correos electrónicos.
Utiliza ReportLab para compilar documentos estilizados y smtplib para el envío automático.
"""
import io
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from typing import Dict, Any, Tuple, Optional
from datetime import datetime

from reportlab.lib.pagesizes import letter
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors


def generar_pdf_cierre_caja(
    fecha_str: str,
    resumen: Dict[str, Any],
    nombre_negocio: str = "Mi Comercio"
) -> bytes:
    """
    Genera en memoria un documento PDF profesional del Cierre Diario de Caja.
    Retorna los bytes del archivo PDF generado.
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=36,
        leftMargin=36,
        topMargin=36,
        bottomMargin=36
    )

    styles = getSampleStyleSheet()
    
    # Estilos tipográficos personalizados
    titulo_style = ParagraphStyle(
        "TituloReporte",
        parent=styles["Heading1"],
        fontName="Helvetica-Bold",
        fontSize=20,
        leading=24,
        textColor=colors.HexColor("#1E293B"),
        alignment=0
    )
    
    subtitulo_style = ParagraphStyle(
        "SubtituloReporte",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=10,
        leading=14,
        textColor=colors.HexColor("#64748B")
    )
    
    seccion_style = ParagraphStyle(
        "TituloSeccion",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=13,
        leading=16,
        textColor=colors.HexColor("#0F172A")
    )

    cell_bold = ParagraphStyle(
        "CellBold",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=9,
        leading=11,
        textColor=colors.HexColor("#0F172A")
    )

    cell_normal = ParagraphStyle(
        "CellNormal",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9,
        leading=11,
        textColor=colors.HexColor("#334155")
    )

    elements = []

    # 1. ENCABEZADO
    elements.append(Paragraph(nombre_negocio.upper(), titulo_style))
    elements.append(Paragraph(f"INFORME OFICIAL DE CIERRE DE CAJA & ARQUEO DIARIO", subtitulo_style))
    elements.append(Paragraph(f"Fecha Contable: <b>{fecha_str}</b> | Emisión: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}", subtitulo_style))
    elements.append(Spacer(1, 10))
    elements.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor("#CBD5E1"), spaceAfter=15))

    # 2. TARJETAS DE INDICADORES (KPIs)
    total_vendido = resumen.get("total_vendido", 0.0)
    ganancia_estimada = resumen.get("ganancia_estimada", 0.0)
    total_operaciones = resumen.get("total_operaciones", 0)

    kpi_data = [
        [
            Paragraph("<font size='9' color='#64748B'>TOTAL FACTURADO</font><br/><br/><b><font size='16' color='#0F172A'>${:,.2f}</font></b>".format(total_vendido), styles["Normal"]),
            Paragraph("<font size='9' color='#64748B'>GANANCIA ESTIMADA</font><br/><br/><b><font size='16' color='#16A34A'>${:,.2f}</font></b>".format(ganancia_estimada), styles["Normal"]),
            Paragraph("<font size='9' color='#64748B'>TOTAL DE OPERACIONES</font><br/><br/><b><font size='16' color='#2563EB'>{}</font></b>".format(total_operaciones), styles["Normal"])
        ]
    ]

    t_kpi = Table(kpi_data, colWidths=[180, 180, 180])
    t_kpi.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F8FAFC")),
        ("BOX", (0, 0), (0, 0), 1, colors.HexColor("#E2E8F0")),
        ("BOX", (1, 0), (1, 0), 1, colors.HexColor("#E2E8F0")),
        ("BOX", (2, 0), (2, 0), 1, colors.HexColor("#E2E8F0")),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
    ]))
    elements.append(t_kpi)
    elements.append(Spacer(1, 20))

    # 3. DESGLOSE POR MEDIO DE PAGO
    elements.append(Paragraph("💳 Desglose por Medio de Pago", seccion_style))
    elements.append(Spacer(1, 8))

    desglose = resumen.get("desglose_por_forma_pago", [])
    if desglose:
        tabla_pago_data = [
            [
                Paragraph("<b>Medio de Pago</b>", cell_bold),
                Paragraph("<b>Operaciones</b>", cell_bold),
                Paragraph("<b>Subtotal Recaudado</b>", cell_bold),
                Paragraph("<b>% Participación</b>", cell_bold)
            ]
        ]

        for item in desglose:
            pct = (item["total"] / total_vendido * 100.0) if total_vendido > 0 else 0.0
            tabla_pago_data.append([
                Paragraph(item["forma_pago"], cell_normal),
                Paragraph(str(item["operaciones"]), cell_normal),
                Paragraph(f"${item['total']:,.2f}", cell_bold),
                Paragraph(f"{pct:.1f}%", cell_normal)
            ])

        t_pago = Table(tabla_pago_data, colWidths=[180, 100, 140, 120])
        t_pago.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F1F5F9")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#0F172A")),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8FAFC")]),
        ]))
        elements.append(t_pago)
    else:
        elements.append(Paragraph("<i>No se registraron ventas en esta jornada.</i>", cell_normal))

    elements.append(Spacer(1, 20))

    # 4. LISTA DE TICKETS DEL DÍA
    elements.append(Paragraph("📜 Detalle Cronológico de Ventas", seccion_style))
    elements.append(Spacer(1, 8))

    ventas = resumen.get("ventas", [])
    if ventas:
        tabla_ventas_data = [
            [
                Paragraph("<b>Ticket #</b>", cell_bold),
                Paragraph("<b>Hora</b>", cell_bold),
                Paragraph("<b>Medio de Pago</b>", cell_bold),
                Paragraph("<b>Total Ticket</b>", cell_bold)
            ]
        ]

        for v in ventas:
            hora_str = v.get("fecha_hora", "")
            if " " in hora_str:
                hora_str = hora_str.split(" ")[1]

            tabla_ventas_data.append([
                Paragraph(f"#{v['id']}", cell_normal),
                Paragraph(hora_str, cell_normal),
                Paragraph(v.get("forma_pago", ""), cell_normal),
                Paragraph(f"${v.get('total_venta', 0.0):,.2f}", cell_bold)
            ])

        t_ventas = Table(tabla_ventas_data, colWidths=[100, 120, 180, 140])
        t_ventas.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F1F5F9")),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8FAFC")]),
        ]))
        elements.append(t_ventas)
    else:
        elements.append(Paragraph("<i>Sin tickets emitidos en la fecha indicada.</i>", cell_normal))

    elements.append(Spacer(1, 30))
    elements.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#E2E8F0"), spaceAfter=10))
    elements.append(Paragraph("Documento de control interno generado automáticamente por el Sistema de Gestión Comercial.", subtitulo_style))

    # Construir documento
    doc.build(elements)
    buffer.seek(0)
    return buffer.getvalue()


def enviar_email_cierre(
    destinatario: str,
    pdf_bytes: bytes,
    fecha_str: str,
    resumen: Dict[str, Any],
    config_smtp: Dict[str, Any]
) -> Tuple[bool, str]:
    """
    Envía por correo electrónico el PDF de cierre de caja adjunto usando smtplib.
    Retorna una tupla (éxito: bool, mensaje: str).
    """
    destinatario_limpio = (destinatario or config_smtp.get("email_destinatario", "")).strip()
    if not destinatario_limpio:
        return False, "No se especificó ninguna dirección de correo de destino."

    servidor_smtp = config_smtp.get("smtp_servidor", "").strip()
    puerto_smtp = int(config_smtp.get("smtp_puerto", 587))
    usuario_smtp = config_smtp.get("smtp_usuario", "").strip()
    password_smtp = config_smtp.get("smtp_password", "").strip()
    nombre_negocio = config_smtp.get("nombre_negocio", "Mi Comercio")

    if not servidor_smtp or not usuario_smtp or not password_smtp:
        return False, "La configuración de servidor SMTP, usuario o contraseña está incompleta."

    try:
        total_vendido = resumen.get("total_vendido", 0.0)
        ganancia_estimada = resumen.get("ganancia_estimada", 0.0)
        total_ops = resumen.get("total_operaciones", 0)

        # Crear mensaje MIME
        msg = MIMEMultipart()
        msg["From"] = f"{nombre_negocio} <{usuario_smtp}>"
        msg["To"] = destinatario_limpio
        msg["Subject"] = f"📊 Cierre de Caja {fecha_str} - {nombre_negocio}"

        cuerpo_html = f"""
        <html>
        <body style="font-family: Arial, sans-serif; color: #333; line-height: 1.6;">
            <div style="background-color: #f8fafc; padding: 20px; border-radius: 8px; border: 1px solid #e2e8f0; max-width: 600px;">
                <h2 style="color: #0f172a; margin-top: 0;">Resumen Diario de Ventas - {nombre_negocio}</h2>
                <p>Adjunto encontrarás el informe oficial en formato PDF correspondiente al cierre del día <b>{fecha_str}</b>.</p>
                <hr style="border: 0; border-top: 1px solid #cbd5e1; margin: 15px 0;">
                <table style="width: 100%; border-collapse: collapse;">
                    <tr>
                        <td style="padding: 8px 0; color: #64748b;">Total Facturado:</td>
                        <td style="padding: 8px 0; text-align: right; font-weight: bold; font-size: 16px; color: #0f172a;">${total_vendido:,.2f}</td>
                    </tr>
                    <tr>
                        <td style="padding: 8px 0; color: #64748b;">Ganancia Estimada:</td>
                        <td style="padding: 8px 0; text-align: right; font-weight: bold; font-size: 16px; color: #16a34a;">${ganancia_estimada:,.2f}</td>
                    </tr>
                    <tr>
                        <td style="padding: 8px 0; color: #64748b;">Cantidad de Operaciones:</td>
                        <td style="padding: 8px 0; text-align: right; font-weight: bold; color: #2563eb;">{total_ops} tickets</td>
                    </tr>
                </table>
                <hr style="border: 0; border-top: 1px solid #cbd5e1; margin: 15px 0;">
                <p style="font-size: 12px; color: #94a3b8; margin-bottom: 0;">Enviado automáticamente por el Sistema de Gestión Comercial.</p>
            </div>
        </body>
        </html>
        """
        msg.attach(MIMEText(cuerpo_html, "html"))

        # Adjuntar archivo PDF
        adjunto = MIMEApplication(pdf_bytes, _subtype="pdf")
        adjunto.add_header("Content-Disposition", "attachment", filename=f"Cierre_Caja_{fecha_str}.pdf")
        msg.attach(adjunto)

        # Conectar al servidor SMTP y enviar
        with smtplib.SMTP(servidor_smtp, puerto_smtp, timeout=20) as server:
            server.ehlo()
            if puerto_smtp == 587:
                server.starttls()
                server.ehlo()
            server.login(usuario_smtp, password_smtp)
            server.send_message(msg)

        return True, f"Correo enviado exitosamente a {destinatario_limpio}."

    except Exception as e:
        return False, f"Error al enviar correo por SMTP: {str(e)}"

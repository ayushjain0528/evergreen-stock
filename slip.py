"""Printable dispatch slip (A5 PDF)."""
import io
from reportlab.lib.pagesizes import A5
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.units import mm


def _fmt(q):
    return ("%g" % round(q, 3))


def make_slip(load):
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A5, leftMargin=10 * mm, rightMargin=10 * mm, topMargin=10 * mm, bottomMargin=10 * mm)
    ss = getSampleStyleSheet()
    h = ParagraphStyle("h", parent=ss["Title"], fontSize=15, spaceAfter=2)
    sm = ParagraphStyle("s", parent=ss["Normal"], fontSize=9, leading=12)
    cell = ParagraphStyle("c", parent=ss["Normal"], fontSize=9, leading=11)
    story = [Paragraph("Evergreen Irrigation", h), Paragraph("<b>DISPATCH SLIP</b> &nbsp;&nbsp; No. %s" % load["ref"][:6].upper(), sm), Spacer(1, 3 * mm),
             Paragraph("<b>Date:</b> %s &nbsp;&nbsp;&nbsp; <b>Vehicle:</b> %s" % (load["date"], load["vehicle"]), sm)]
    drops = load.get("drops") or [(load.get("party", ""), load["lines"])]
    for n, (party, lines) in enumerate(drops, 1):
        story += [Spacer(1, 3 * mm), Paragraph("<b>%sCustomer / place:</b> %s" % (("Drop %d &nbsp; " % n) if len(drops) > 1 else "", (party or "-").replace("&", "&amp;")), sm), Spacer(1, 1.5 * mm)]
        data = [["#", "Item", "Qty", "Unit"]]; tot = 0.0
        for i, ln in enumerate(lines, 1):
            nm = (ln["brand"] + " | " if ln["brand"] and ln["brand"].lower() != "evergreen" else "") + ln["name"]
            data.append([str(i), Paragraph(nm.replace("&", "&amp;"), cell), _fmt(ln["qty"]), ln["unit"]]); tot += ln["qty"]
        data.append(["", "Total quantity", _fmt(tot), ""])
        t = Table(data, colWidths=[8 * mm, 78 * mm, 18 * mm, 16 * mm], repeatRows=1)
        t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), .5, colors.black), ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E8F5E9")), ("FONTSIZE", (0, 0), (-1, -1), 9),
                               ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"), ("FONTNAME", (1, -1), (2, -1), "Helvetica-Bold"), ("ALIGN", (2, 0), (2, -1), "RIGHT"), ("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
        story += [t]
    if load.get("note"): story += [Spacer(1, 2 * mm), Paragraph("<b>Note:</b> %s" % load["note"], sm)]
    story += [Spacer(1, 14 * mm), Table([["Prepared by: %s" % load["user"], "Loaded by: _________", "Driver: _________", "Received by: _________"]],
                                        colWidths=[30 * mm, 32 * mm, 30 * mm, 32 * mm], style=[("FONTSIZE", (0, 0), (-1, -1), 7.5)])]
    doc.build(story)
    return buf.getvalue()

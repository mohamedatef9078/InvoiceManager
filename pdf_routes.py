from flask import Blueprint, send_file
import io
from reportlab.pdfgen import canvas

pdf_blueprint = Blueprint("pdf", __name__)


@pdf_blueprint.route("/pdf/test")
def test_pdf():

    buffer = io.BytesIO()

    pdf = canvas.Canvas(buffer)

    pdf.setTitle("Invoice")

    pdf.drawString(
        100,
        800,
        "Electronic Invoice Manager"
    )

    pdf.drawString(
        100,
        780,
        "PDF Module Works Successfully"
    )

    pdf.drawString(
        100,
        760,
        "Version 1.0"
    )

    pdf.save()

    buffer.seek(0)

    return send_file(
        buffer,
        as_attachment=True,
        download_name="test.pdf",
        mimetype="application/pdf",
    )
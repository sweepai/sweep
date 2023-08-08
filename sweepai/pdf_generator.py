from reportlab.pdfgen import canvas

class PDFGenerator:
    def create_pdf(self, data, filename):
        try:
            c = canvas.Canvas(filename)
            textobject = c.beginText()
            textobject.setTextOrigin(10, 730)
            for line in data:
                textobject.textLine(line)
            c.drawText(textobject)
            c.save()
        except Exception as e:
            print(f"An error occurred while creating the PDF: {e}")
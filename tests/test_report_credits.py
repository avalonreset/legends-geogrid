import tempfile
import unittest
from pathlib import Path
from pypdf import PdfReader
from reportlab.pdfgen.canvas import Canvas
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from report_design import add_pdf_brand_links

class BrandCreditTests(unittest.TestCase):
    def test_links_are_only_on_first_and_last_pages_without_losing_content(self):
        for count in (1, 3):
            with self.subTest(pages=count), tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp)/'report.pdf'
                canvas = Canvas(str(path))
                for index in range(count):
                    canvas.drawString(48, 600, 'Original page '+str(index))
                    canvas.showPage()
                canvas.save()
                add_pdf_brand_links(path)
                doc = PdfReader(path)
                self.assertEqual(count, len(doc.pages))
                for index, page in enumerate(doc.pages):
                    self.assertIn('Original page '+str(index), page.extract_text())
                    urls = [a.get_object()['/A']['/URI'] for a in page.get('/Annots', [])]
                    expected = []
                    if index == 0: expected.append('https://cto-legends.com')
                    if index == count-1: expected.append('https://www.skool.com/ai-marketing-hub-pro/about')
                    self.assertEqual(expected, urls)

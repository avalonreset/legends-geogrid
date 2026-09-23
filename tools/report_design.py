"""Versioned presentation contract shared by report output formats.

Business data and narrative never select layout or inject CSS.
"""
import os
from pathlib import Path
import shutil


def legends_font():
    """Optional licensed local font; never bundle a private font in source."""
    value = os.environ.get('GEOGRID_LEGENDS_FONT')
    if not value:
        return None
    path = Path(value).resolve()
    if not path.is_file():
        raise ValueError('GEOGRID_LEGENDS_FONT does not point to a font file')
    return path


def prepare_html_font(output, theme):
    font = legends_font()
    if font:
        shutil.copyfile(font, Path(output)/'legends-regular.ttf')


def prepare_banner(output, theme):
    """Keep the approved artwork; reverse neutral ink for the print palette."""
    source = Path(__file__).resolve().parents[1]/'assets/banner.png'
    target = Path(output)/'banner.png'
    if theme == 'light':
        from PIL import Image
        with Image.open(source) as original:
            image = original.convert('RGB')
            image.putdata([(255-r,255-g,255-b) if max(r,g,b)-min(r,g,b)<12 else (r,g,b)
                           for r,g,b in image.getdata()])
            image.save(target)
    else:
        shutil.copyfile(source, target)
    return target

DESIGN_VERSION = 'legends-editorial-v5'
BRAND_TOP = '<div class="brand-credit brand-credit-top"><a href="https://cto-legends.com">cto-legends</a></div>'
BRAND_BOTTOM = '<div class="brand-credit brand-credit-bottom"><a href="https://www.skool.com/ai-marketing-hub-pro/about">ai-marketing-hub-pro</a></div>'


def add_pdf_brand_links(path):
    """Two quiet credits per document, never repeated on every page."""
    from io import BytesIO
    from pypdf import PdfReader, PdfWriter
    from reportlab.pdfgen.canvas import Canvas
    from reportlab.pdfbase.pdfmetrics import stringWidth
    reader = PdfReader(str(path))
    writer = PdfWriter()
    for index, page in enumerate(reader.pages):
        width, height = float(page.mediabox.width), float(page.mediabox.height)
        credits = []
        if index == 0:
            credits.append(('cto-legends', 'https://cto-legends.com', height - 31))
        if index == len(reader.pages) - 1:
            credits.append(('ai-marketing-hub-pro', 'https://www.skool.com/ai-marketing-hub-pro/about', 28))
        if credits:
            overlay = BytesIO()
            canvas = Canvas(overlay, pagesize=(width, height))
            canvas.setFont('Helvetica', 8.5)
            canvas.setFillColorRGB(1, 0, 0)
            for label, url, baseline in credits:
                text_width = stringWidth(label, 'Helvetica', 8.5)
                x = width - MARGIN - text_width
                canvas.drawString(x, baseline, label)
                canvas.linkURL(url, (x, baseline-3, x+text_width, baseline+10), relative=0)
            canvas.save()
            overlay.seek(0)
            page.merge_page(PdfReader(overlay).pages[0])
        writer.add_page(page)
    if reader.metadata:
        writer.add_metadata(dict(reader.metadata))
    buffer = BytesIO()
    writer.write(buffer)
    Path(path).write_bytes(buffer.getvalue())
PAGE_W, PAGE_H, MARGIN, COLUMN = 612, 792, 48, 516
THEMES = {
    'geogrid': dict(BG='#000000', PANEL='#000000', INK='#FFFFFF', MUTED='#666666', ACCENT='#FF0000', LINE='#666666'),
    'light': dict(BG='#FFFFFF', PANEL='#FFFFFF', INK='#000000', MUTED='#555555', ACCENT='#FF0000', LINE='#CCCCCC'),
}


def html_styles(theme='geogrid'):
    t = THEMES[theme]
    base = '''
*{box-sizing:border-box}
html{color-scheme:SCHEME;scroll-behavior:smooth}
body{margin:0;background:BG;color:INK;font:16px/1.6 Arial,Helvetica,sans-serif}
main{max-width:960px;margin:0 auto;padding:48px 32px}
h1,h2,h3{color:INK;font-weight:600;line-height:1.25;letter-spacing:-.02em;overflow-wrap:anywhere}
h1{font-size:36px;margin:16px 0 24px}h2{font-size:24px;margin:0 0 16px}h3{font-size:18px;margin:24px 0 12px}
p{margin:0 0 16px;overflow-wrap:anywhere}a{color:inherit;text-underline-offset:3px}
.mono,.eyebrow,small{font:12px/1.5 ui-monospace,monospace;color:MUTED}
.report-cover,.report-lane,.report-section{padding:32px 0;border-bottom:1px solid LINE}
.report-cover{padding-top:0}.report-nav{display:flex;flex-wrap:wrap;gap:12px 24px;padding:16px 0;border-bottom:1px solid LINE}
.report-nav a{font-size:14px}.report-lane{scroll-margin-top:20px}
.report-map{margin:24px 0}.report-map img{display:block;width:100%;height:auto}
.report-map figcaption{font-size:13px;color:MUTED}
.banner{display:block;width:100%;max-height:100px;object-fit:contain;object-position:left center}
.brand-strip{height:6px;background:linear-gradient(115deg,#CC0000,#8C0000,#111111,#777777,#FFFFFF)}
.notice{border:1px solid LINE;padding:16px;margin:24px 0}
table{width:100%;border-collapse:collapse;font-size:13px}th,td{text-align:left;vertical-align:top;padding:10px;border-bottom:1px solid LINE;overflow-wrap:anywhere}
th{color:MUTED}summary{cursor:pointer;padding:16px 0;font-weight:600}details{border-top:1px solid LINE;margin-top:24px}
.scroll{overflow-x:auto;max-width:100%}.scroll table{min-width:700px}
footer{padding:32px 0;color:MUTED;font-size:13px}
.brand-credit{display:flex;justify-content:flex-end;font:13px/1.5 Arial,Helvetica,sans-serif}.brand-credit a{color:#FF0000}.brand-credit-top{margin-bottom:24px}.brand-credit-bottom{margin-top:28px}
@media(max-width:600px){main{padding:24px 16px}h1{font-size:28px}h2{font-size:22px}.report-lane,.report-section{padding:24px 0}}
@media print{@page{size:Letter;margin:48pt}html{print-color-adjust:exact;-webkit-print-color-adjust:exact}body{font-size:11pt;line-height:1.45}main{max-width:none;margin:0;padding:0}.report-nav,.report-downloads{display:none}.report-lane,.report-section{break-before:page}h1,h2,h3{break-after:avoid}.report-map,img,tr{break-inside:avoid}h1{font-size:24pt}h2{font-size:17pt}}
'''.replace('SCHEME', 'light' if theme == 'light' else 'dark').replace('MUTED', t['MUTED']).replace('LINE', t['LINE']).replace('INK', t['INK']).replace('BG', t['BG'])
    font_css = ''
    if legends_font():
        font_css = "@font-face{font-family:Legends;src:url('legends-regular.ttf') format('truetype');font-weight:100 900;font-display:block}body,h1,h2,h3,.mono,.eyebrow,small{font-family:Legends,monospace!important;font-synthesis:none}"
    editorial = '''
/* Legends Design Bible: dark presentation only. Evidence colors are separate. */
/* A small visual vocabulary: query tickets, measured rails, and decision cards. */
.query-deck{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:20px;margin:28px 0}
.query-ticket{border:1px solid #666666;padding:24px;position:relative;min-width:0}
.query-ticket::before{content:"";position:absolute;top:-1px;left:-1px;width:40px;height:3px;background:#FF0000}
.query-ticket h3{margin:10px 0 18px;font-size:23px}.query-ticket p{font-size:15px}
.query-index{color:#FFFFFF;font-size:13px;letter-spacing:.1em}
.query-token{display:inline-block;border:1px solid #666666;padding:7px 12px;color:#FFFFFF;font-size:15px;margin:0 0 12px;max-width:100%;overflow-wrap:anywhere}
.metric-rail{display:block;height:5px;width:100%;background:#666666;margin:10px 0 4px}.metric-rail>span{display:block;height:100%;background:#FFFFFF}
.decision-card{border:1px solid #666666;padding:28px;margin:24px 0;border-left:3px solid #FFFFFF}
.decision-card h3{font-size:24px;margin:12px 0 24px}.decision-card p{margin-bottom:18px}
.decision-class{display:inline-block;font-size:13px;letter-spacing:.07em;border-bottom:2px solid #FF0000;padding-bottom:8px}
.decision-label{display:block;font-size:13px;letter-spacing:.06em;margin-bottom:6px;text-transform:lowercase}
.report-lane>.eyebrow{color:#FFFFFF;display:flex;align-items:center;gap:14px}.report-lane>.eyebrow::before{content:"";display:inline-block;width:32px;height:3px;background:#FF0000}
@media(max-width:650px){.query-deck{grid-template-columns:1fr}.query-ticket,.decision-card{padding:20px}.decision-card h3{font-size:21px}}

body{font-size:17px;line-height:1.65}
main{max-width:1080px;padding:64px 48px}
h1{font-size:clamp(28px,3.5vw,44px);line-height:1.18;width:100%;max-width:none;text-wrap:balance;word-break:normal;overflow-wrap:anywhere;margin:28px 0}
h2{font-size:28px;text-wrap:balance}h3{font-size:18px}
p{text-wrap:pretty;max-width:76ch}
a{color:#FF0000;text-decoration:underline}a:hover,a:focus-visible{text-decoration:none}
.eyebrow,.mono{text-transform:lowercase;letter-spacing:.06em;color:#666666}
.supporting-copy{color:#666666}
.report-cover{padding-bottom:40px;border-bottom:1px solid #FFFFFF}
.report-lane,.report-section{padding:40px 0}
.report-nav{padding:22px 0;gap:14px 28px}
.report-map{margin:28px 0}.report-map figcaption{color:#FFFFFF;font-size:14px}
.banner{height:auto;max-height:none;width:100%;max-width:720px;margin:0 0 28px}
.study-overview{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:24px;border-top:1px solid #FFFFFF;border-bottom:1px solid #FFFFFF;padding:24px 0;margin:28px 0}
.study-overview strong{font-size:32px;display:block;font-weight:500;line-height:1.2}
.study-overview span{font-size:15px;display:block;margin-top:8px;color:#666666}
.theme-list{padding:0;list-style:none}.theme-list li{padding:16px 0;border-bottom:1px solid #666666}
.theme-list strong{display:block;font-weight:600}.theme-list p{margin:6px 0 0;font-size:15px}
[data-stage="proposal"] .theme-list p{color:#FFFFFF}
details>summary{color:#FF0000;font-weight:400;list-style:none;text-decoration:underline}
details>summary::-webkit-details-marker{display:none}details[open]>summary{color:#FFFFFF;text-decoration:none}details>summary:focus-visible{outline:1px solid #FF0000;outline-offset:4px}
details{padding-bottom:12px}details p{font-size:15px}
[data-stage="proposal"]>.report-section+details{border-top:0;margin-top:0}
.report-downloads{border-top:1px solid #FFFFFF}
.visibility-table{font-size:16px;margin:24px 0}.visibility-table th{color:#FFFFFF;font-weight:400}.visibility-table td,.visibility-table th{padding:16px 8px}.visibility-table td:not(:first-child){font-variant-numeric:tabular-nums}
.report-legend{font-size:15px;color:#FFFFFF}.summary-note{font-size:15px}
.report-cover>h2{margin-top:28px}.report-cover>details{margin-top:28px}
@media(max-width:600px){.visibility-table{font-size:14px}.visibility-table td,.visibility-table th{padding:12px 4px}}
@media(max-width:600px){main{padding:32px 22px}.study-overview{gap:12px}.study-overview strong{font-size:25px}.study-overview span{font-size:12px}.report-section,.report-lane{padding:30px 0}}
@media print{main{padding:0}body{font-size:11pt}h1{font-size:26pt}.report-section,.report-lane{padding:20px 0}}
/* v5: type roles and surfaces carry meaning, never alternate randomly. */
h2{font-size:32px;line-height:1.2;margin:0 0 24px}
.report-section>h2:not(:first-child){margin-top:48px}
h3{font-size:24px;line-height:1.3;margin:32px 0 16px}
.query-ticket h3,.decision-card h3{font-size:24px;line-height:1.3}
p{color:#E0E0E0}
.eyebrow,.mono,small,.supporting-copy,footer{color:#A3A3A3}
.query-ticket{background:linear-gradient(145deg,#1C1C1C 0%,#111111 65%);border-color:#404040;box-shadow:inset 0 1px 0 #FFFFFF14}
.query-ticket p{font-size:16px;line-height:1.65}
.query-token{background:linear-gradient(120deg,#301414,#111111);border-color:#794040;padding:12px 18px;font-size:22px;line-height:1.4}
.query-token::before{content:"SEARCH KEYWORD";display:block;font-size:12px;letter-spacing:.08em;color:#BDBDBD;margin-bottom:8px}
.query-index{color:#A3A3A3}
.decision-card{background:linear-gradient(120deg,#231818 0%,#181818 38%,#121212 100%);border-color:#404040;border-left-color:#FF0000;box-shadow:inset 0 1px 0 #FFFFFF14}
.decision-class{color:#FFFFFF;background:#300909;border:0;padding:6px 10px;letter-spacing:.04em}
.decision-label{color:#FFFFFF;font-size:14px;margin-top:20px;margin-bottom:8px}
.notice{background:#211010;border-color:#794040;padding:24px}
details{border-color:#404040}
details>summary{font-size:20px;line-height:1.35;padding:20px 0}
.query-ticket details>summary,.report-cover details>summary{font-size:14px;color:#BDBDBD}
.report-section,.report-lane{padding:48px 0;border-color:#404040}
.visibility-table th{background:#181818;font-size:14px;color:#BDBDBD}
.visibility-table td{padding-top:20px;padding-bottom:20px}
.metric-rail{background:#404040}
@media(max-width:650px){h2{font-size:28px}h3,.query-ticket h3,.decision-card h3{font-size:22px}.report-section,.report-lane{padding:36px 0}}
@media print{h2{font-size:19pt}h3,.query-ticket h3,.decision-card h3{font-size:15pt}p,.query-ticket p{font-size:11pt}.query-ticket,.decision-card{break-inside:avoid;background:#181818;box-shadow:none}}
'''
    if theme == 'light':
        # One layout in both modes; change only ink, surfaces and decoration.
        import re
        palette = {'#FFFFFF14':'#00000000', '#FFFFFF':'#000000',
                   '#E0E0E0':'#000000', '#A3A3A3':'#555555', '#BDBDBD':'#555555',
                   '#666666':'#666666', '#404040':'#CCCCCC', '#1C1C1C':'#FFFFFF',
                   '#111111':'#FFFFFF', '#301414':'#F7F7F7', '#794040':'#CCCCCC',
                   '#231818':'#FFFFFF', '#181818':'#FFFFFF', '#121212':'#FFFFFF',
                   '#300909':'#F3F3F3', '#211010':'#FFFFFF'}
        editorial = re.sub(r'#[0-9A-Fa-f]{8}\b|#[0-9A-Fa-f]{6}\b',
                           lambda m: palette.get(m[0], m[0]), editorial)
        editorial += '\n.query-ticket,.decision-card,.query-token,.notice{background:#FFFFFF;box-shadow:none}.metric-rail{background:#DDDDDD}\n'
    return base + editorial + font_css

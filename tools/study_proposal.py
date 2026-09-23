"""Render a validated study proposal offline, using the shared design contract."""
from datetime import datetime, timezone
from html import escape
import json
from pathlib import Path
import shutil
import tempfile

from report_design import BRAND_TOP, BRAND_BOTTOM, add_pdf_brand_links, DESIGN_VERSION, THEMES, PAGE_W, PAGE_H, MARGIN, COLUMN, html_styles, prepare_html_font
from study_contract import validate, require, digest


def sections(plan, receipt):
    b, s = plan['business'], plan['settings']
    result = [('Study decision', [s['decision'], plan['selection']['coverage_summary'],
        'Scope: '+receipt['scope']+'. '+plan['identity']['reconciliation'],
        'Named listing: '+b['name']+' | '+b['location_label']+' | CID '+b['cid'],
        'Proposed measurements, not completed findings. Existing pilots establish sampling intent only.'])]
    if receipt['scope'] == 'focused':
        result[0][1].append(plan['selection']['fewer_themes']['reason'])
    if receipt['website_limitation']:
        result[0][1].append('Website unavailable; offerings supported by public profile only. '+receipt['website_limitation'])
    for q in plan['queries']:
        if not q['selected']:
            continue
        t = q['theme']
        paragraphs = ['Representative query: '+q['query'], 'Customer need: '+t['customer_need'],
            'Why study this: '+q['reason'], 'Distinct comparison: '+t['distinct_value'],
            'Search intent: '+q['intent_assessment'], 'Demand scope: '+q['demand_scope'],
            'Limitations: '+q['limitations']]
        for ref in q['offering_evidence']:
            paragraphs.append('Offering evidence ['+ref['source_id']+']: '+ref['quote'])
        paragraphs.append('Demand source: '+q['demand_source']+'. Pilot sources: '+', '.join(q['pilot_sources']))
        result.append((t['label'], paragraphs))
    rejected = [q['query']+': '+q.get('reason','No reason supplied') for q in plan['queries'] if not q['selected']]
    if rejected:
        result.append(('Queries not selected', rejected))
    result.append(('Shared measurement geography', [s['geography_reason'],
        f"{s['grid_size']} by {s['grid_size']} origins per query; radius parameter {s['radius_km']} km. "
        'This sampling boundary is not a verified customer catchment.',
        f"Center: {b['lat']}, {b['lng']}. All queries use the same origins and settings.",
        'Settings: '+', '.join(f'{k}={s[k]}' for k in ('method','depth','zoom','device','language_code','se_domain','search_this_area'))]))
    result.append(('Cost and delivery', [f"Estimated grid collection: ${receipt['estimated_grid_cost_usd']:.6f} USD. "
        'Research already performed and basemap charges, if any, are separate; this is not an all-in total.',
        'Estimates are advisory, not provider-enforced billing caps. Rendering this proposal makes no provider calls and does not authorize collection.',
        'Deliverables: comparable street maps, observed rankings, evidence limitations, and supported next steps in HTML and PDF.',
        receipt['qualification']]))
    result.append(('Sources and provenance', [f"[{x['id']}] {x['kind']} | {x['observed_at']} | {x['url']}" for x in plan['sources']]))
    return result


def render_proposal(plan_path, output_dir, theme='geogrid'):
    require(theme in THEMES, 'unknown proposal theme')
    plan, receipt = validate(plan_path)
    output = Path(output_dir).resolve()
    require(not output.exists(), 'proposal output exists; choose a new reading-edition folder')
    content = sections(plan, receipt)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=output.parent) as tmp:
        stage = Path(tmp)
        prepare_html_font(stage,theme)
        title = plan['business']['name']
        from report_design import prepare_banner
        banner = prepare_banner(stage, theme)
        parts = ['<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">',
            '<title>'+escape(title)+' | study proposal</title><style>'+html_styles(theme)+'</style></head>',
            '<body><main data-design="'+DESIGN_VERSION+'" data-stage="proposal">'+BRAND_TOP+'<header class="report-cover">',
            '<img class="banner" src="banner.png" alt="legends-geogrid"><p class="eyebrow">proposed study</p><h1>'+escape(title)+'</h1></header>']
        selected=[q for q in plan['queries'] if q['selected']]
        points=plan['settings']['grid_size']**2
        parts += ['<section class="report-section"><h2>the proposed study</h2><p>'+escape(plan['settings']['decision'])+'</p>',
            '<div class="study-overview"><div><strong>'+str(len(selected))+'</strong><span>search themes</span></div><div><strong>'+str(points)+'</strong><span>shared locations per theme</span></div><div><strong>$'+format(receipt['estimated_grid_cost_usd'],'.2f')+'</strong><span>estimated grid data only</span></div></div>',
            '<p>Research and optional map charges are separate. This is an estimate, not a billing cap.</p><ul class="theme-list">']
        for q in selected:
            parts += ['<li><strong>'+escape(q['query'])+'</strong><p>'+escape(q['theme']['customer_need'])+'</p></li>']
        parts += ['</ul><h3>scope and limitations</h3><p>'+escape(plan['selection']['coverage_summary'])+'</p>',
            '<p>'+escape(plan['identity']['reconciliation'])+'</p>',
            '<p>Proposed measurements, not completed findings. Detailed selection evidence follows.</p></section>']
        for heading, paragraphs in content:
            if heading=='Study decision':
                if receipt['scope']=='focused':
                    parts += ['<p>'+escape(plan['selection']['fewer_themes']['reason'])+'</p>']
                if receipt['website_limitation']:
                    parts += ['<p>'+escape(receipt['website_limitation'])+'</p>']
                continue
            collapsed=heading in ('Queries not selected','Sources and provenance')
            parts += ['<details'+('' if collapsed else ' open')+'><summary>'+escape(heading.lower())+'</summary>']
            secondary=heading in ('Sources and provenance','Shared measurement geography')
            parts += [('<p class="supporting-copy">' if secondary else '<p>')+escape(p)+'</p>' for p in paragraphs]
            parts += ['</details>']
        parts += ['<footer><a href="proposal.pdf">PDF proposal</a>'+BRAND_BOTTOM+'</footer></main></body></html>']
        (stage/'proposal.html').write_text('\n'.join(parts), encoding='utf-8')
        from reportlab.lib.colors import HexColor
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Image, PageBreak
        import strategy_report as report
        old_theme = report.THEME
        try:
            report.apply_theme(theme)
            report.register_fonts(dict(theme=theme,business=dict(name=title,location=plan['business']['location_label']),
                thesis='',center_label='',objectives=[p for _,ps in content for p in ps],
                next_actions=[],missing_evidence=[],lanes=[]))
            t = THEMES[theme]
            body = ParagraphStyle('body', fontName='ReportBody', fontSize=11, leading=16,
                textColor=HexColor(t['INK']), spaceAfter=10, splitLongWords=True)
            heading_style = ParagraphStyle('heading', parent=body, fontName='ReportBold', fontSize=15,
                leading=20, spaceBefore=14, keepWithNext=True)
            secondary_style = ParagraphStyle('supporting',parent=body,textColor=HexColor(t['MUTED']))
            from PIL import Image as PILImage
            with PILImage.open(banner) as image:
                width,height=image.size
            logo=Image(str(banner),width=COLUMN,height=COLUMN*height/width)
            logo.hAlign='LEFT'
            story = [logo,Paragraph(escape(title), heading_style)]
            overview=[plan['settings']['decision'],
                f"{len(selected)} search themes / {points} shared locations per theme / ${receipt['estimated_grid_cost_usd']:.2f} estimated grid data.",
                'Research and optional map charges are separate. This is an estimate, not a billing cap.']
            story += [Paragraph(escape(p),body) for p in overview]
            for q in selected:
                story.append(Paragraph('<b>'+escape(q['query'])+'</b>: <font color="#666666">'+escape(q['theme']['customer_need'])+'</font>',body))
            story += [Paragraph('scope and limitations',heading_style),Paragraph(escape(plan['selection']['coverage_summary']),body),
                Paragraph('Proposal only. Identity reconciliation, offering evidence and research limitations follow.',body),PageBreak()]
            for heading, paragraphs in content:
                story.append(Paragraph(escape(heading.lower()), heading_style))
                paragraph_style=secondary_style if heading in ('Sources and provenance','Shared measurement geography') else body
                story.extend(Paragraph(escape(report.display_text(p)), paragraph_style) for p in paragraphs)
            def page(canvas, doc):
                canvas.setFillColor(HexColor(t['BG']))
                canvas.rect(0,0,PAGE_W,PAGE_H,stroke=0,fill=1)
                canvas.setFillColor(HexColor(t['MUTED']))
                canvas.setFont('ReportBody',8.5)
                canvas.drawString(MARGIN,761,'legends-geogrid / proposed study')
                canvas.drawString(MARGIN,28,'PROPOSAL / NOT COMPLETED GRID FINDINGS')
                canvas.drawRightString(PAGE_W/2,28,str(doc.page))
            doc = SimpleDocTemplate(str(stage/'proposal.pdf'),pagesize=(PAGE_W,PAGE_H),
                leftMargin=MARGIN,rightMargin=MARGIN,topMargin=65,bottomMargin=58,
                title=title+' | proposed study',author='legends-geogrid')
            doc.build(story,onFirstPage=page,onLaterPages=page)
            add_pdf_brand_links(stage/'proposal.pdf')
            qa = report.pdf_qa(stage/'proposal.pdf',proof=True,required=True)
            require(qa['status']=='passed', 'proposal PDF QA failed: '+str(qa.get('issues')))
        finally:
            report.apply_theme(old_theme)
        summary = dict(design_version=DESIGN_VERSION,stage='proposal',theme=theme,
            generated_at=datetime.now(timezone.utc).isoformat(),plan_sha256=receipt['plan_sha256'],
            provider_calls=0,pdf=qa,validation=receipt,
            sha256={p.name:digest(p) for p in stage.iterdir() if p.is_file()})
        (stage/'proposal-receipt.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
        # Exclusive destination creation prevents overwriting any frozen proposal.
        output.mkdir()
        shutil.copytree(stage,output,dirs_exist_ok=True)
    return summary

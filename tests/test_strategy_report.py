"""Offline input, denominator, geographic and PDF regression checks."""
from __future__ import annotations

import copy
import importlib.util
import json
import math
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'tools'))
from report_model import bounds, finding, load_config, metrics, runner_records, validate_observation
from strategy_report import Projection, build, georeferenced_image, map_image, map_qa, pdf_qa, register_fonts

RENDERING = all(importlib.util.find_spec(m) for m in ('reportlab', 'PIL'))
PDFIUM = bool(importlib.util.find_spec('pypdfium2'))


def observation(index=0, state='found', rank=4):
    return dict(query_id='test', lat=40+index*.002, lng=-75+index*.003,
                rank=rank if state == 'found' else None, state=state,
                returned_count=20 if state in ('found','not_returned') else 0,
                depth=20 if state in ('found','not_returned') else 0,
                requested_depth=20, sampled_at=None if state == 'unmeasured' else '2026-09-01T12:00:00Z',
                source='synthetic-replay')


def config(records=None):
    return dict(schema_version=1, synthetic=True,
                business=dict(name='Synthetic Test Business',location='Synthetic district',lat=40,lng=-75),
                thesis='Visibility might vary across origins; this is a hypothesis.',
                objectives=['Establish an observed baseline.'],
                lanes=[dict(query_id='test',label='Test service',query='test service',
                            records=records if records is not None else [observation()])],
                map=dict(radius_bands_km=[1,3]))


class ModelTests(unittest.TestCase):
    def load(self, cfg):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'config.json'
            path.write_text(json.dumps(cfg),encoding='utf-8')
            return load_config(path)

    def test_exact_denominators_and_near_miss_edges(self):
        rows = [observation(i,rank=rank) for i,rank in enumerate([1,3,4,10,11,20])]
        rows += [observation(i+6,state=state) for i,state in enumerate(('not_returned','error','empty','unmeasured'))]
        result = metrics(rows)
        self.assertEqual((10,7,3,2,4,2),tuple(result[k] for k in ('sampled','measured','excluded','top3','top10','near_miss')))
        self.assertEqual(4/7,result['top10_observed_share'])
        self.assertEqual(1,result['top10_unknown_absence'])
        rows[6]['observed_ranks'] = list(range(1,21))
        self.assertEqual(0,metrics(rows)['top10_unknown_absence'])

    def test_count_and_requested_depth_do_not_imply_complete_ranks(self):
        row=observation(state='not_returned')
        row['returned_count']=100
        row['depth']=100
        row['observed_ranks']=[1,2,4,10]
        self.assertEqual(1,metrics([row])['top3_unknown_absence'])
        self.assertEqual(1,metrics([row])['top10_unknown_absence'])

    def test_no_measured_origins_has_undefined_shares(self):
        lane=self.load(config([observation(state='error')]))['lanes'][0]
        self.assertIsNone(lane['metrics']['top3_observed_share'])
        self.assertIn('undefined',finding(lane))

    def test_market_center_is_explicit_and_business_default_preserved(self):
        model=self.load(config())
        self.assertEqual('business',model['center_kind'])
        self.assertEqual(model['business']['name'],model['center_label'])
        cfg=config();cfg.update(center_kind='market',center_label='Synthetic town square')
        model=self.load(cfg)
        self.assertEqual('market',model['center_kind'])
        self.assertEqual('Synthetic town square',model['center_label'])
        self.assertEqual(40,model['business']['lat'])
        for value in (None,'',17):
            cfg['center_label']=value
            with self.assertRaisesRegex(ValueError,'center_label'):
                self.load(cfg)
        cfg.pop('center_label')
        with self.assertRaisesRegex(ValueError,'center_label'):
            self.load(cfg)
        cfg['center_kind']='centroid'
        with self.assertRaisesRegex(ValueError,'center_kind'):
            self.load(cfg)

    def test_invalid_states_ranks_coordinates_timestamps(self):
        cases=[('rank',0),('rank',True),('rank',-1),('rank',1.5),('state','unknown'),
               ('lat',math.nan),('lat',86),('lng',181),('lat',True),('depth',-1),
               ('returned_count',-1),('sampled_at','2026-09-01'),('source','')]
        for key,value in cases:
            with self.subTest(key=key,value=value):
                row=observation();row[key]=value
                with self.assertRaises(ValueError):
                    validate_observation(row,'test')
        for state in ('not_returned','error','empty','unmeasured'):
            row=observation();row['state']=state
            with self.assertRaises(ValueError):
                validate_observation(row,'test')

    def test_collector_zero_depth_and_extra_fields(self):
        row=observation(state='unmeasured')
        row.update(x=0,y=0,clean_negative=False,observed_ranks=[])
        lane=self.load(config([row]))['lanes'][0]
        self.assertEqual(0,lane['records'][0]['depth'])
        self.assertEqual(20,lane['records'][0]['requested_depth'])

    def test_collector_target_rank_error_retains_other_rank_evidence_but_is_excluded(self):
        row=observation(state='error')
        row.update(returned_count=5,depth=4,observed_ranks=[1,2,3,4],error_code='target_rank_missing')
        lane=self.load(config([row]))['lanes'][0]
        self.assertEqual([1,2,3,4],lane['records'][0]['observed_ranks'])
        self.assertEqual(0,lane['metrics']['measured'])

    def test_depth_must_match_explicit_contiguous_observed_ranks(self):
        row=observation(state='not_returned')
        row.update(returned_count=2,observed_ranks=[1,2],depth=20,requested_depth=20)
        with self.assertRaisesRegex(ValueError,'depth contradicts'):
            self.load(config([row]))
        row.update(returned_count=4,observed_ranks=[4,1,7,2],depth=2,requested_depth=100)
        saved=self.load(config([row]))['lanes'][0]['records'][0]
        self.assertEqual(2,saved['depth']);self.assertEqual(100,saved['requested_depth'])
        self.assertEqual([1,2,4,7],saved['observed_ranks'])
        for wrong in (0,1,4,7):
            with self.subTest(depth=wrong),self.assertRaisesRegex(ValueError,'depth contradicts'):
                validate_observation(dict(row,depth=wrong),'test')
        self.assertIsNone(validate_observation(dict(row,depth=None),'test')['depth'])
        empty=dict(observation(state='empty'),observed_ranks=[],depth=1)
        with self.assertRaisesRegex(ValueError,'depth contradicts'):
            validate_observation(empty,'test')
        self.assertEqual(0,validate_observation(dict(empty,depth=0),'test')['depth'])

    def test_provenance_preserves_only_typed_digests_and_retention_flag(self):
        safe=dict(request_fingerprint='a'*64,evidence_sha256='B'*64,response_sha256='c'*64,response_retained=True)
        raw=dict(safe,evidence_path='/private/source.json',account_route='private-route',
                 raw={'credential':'DO_NOT_EXPORT'},requested_at='arbitrary unsafe text',url='https://example.invalid/?key=DO_NOT_EXPORT')
        row=dict(observation(),provenance=raw)
        saved=self.load(config([row]))['lanes'][0]['records'][0]
        self.assertEqual(dict(safe,evidence_sha256='b'*64),saved['provenance'])
        for disallowed in ('private/source','private-route','DO_NOT_EXPORT','arbitrary unsafe text'):
            self.assertNotIn(disallowed,json.dumps(saved))
        for key,value in (('response_sha256','not-a-digest'),('request_fingerprint','https://example.invalid'),('response_retained',1)):
            with self.subTest(key=key),self.assertRaises(ValueError):
                validate_observation(dict(row,provenance={key:value}),'test')

    def test_distance_unit_default_validation_and_lane_override(self):
        self.assertEqual('km',self.load(config())['lanes'][0]['map']['distance_unit'])
        cfg=config();cfg['map']['distance_unit']='mi'
        self.assertEqual('mi',self.load(cfg)['lanes'][0]['map']['distance_unit'])
        cfg['lanes'][0]['map']={'distance_unit':'km'}
        self.assertEqual('km',self.load(cfg)['lanes'][0]['map']['distance_unit'])
        cfg['lanes'][0]['map']['distance_unit']='miles'
        with self.assertRaisesRegex(ValueError,'distance_unit'):
            self.load(cfg)

    def test_map_height_is_bounded_integer(self):
        for value in (409,481,True,480.5,None):
            cfg=config();cfg['map']['height_pt']=value
            with self.subTest(height=value),self.assertRaisesRegex(ValueError,'height_pt'):
                self.load(cfg)
        cfg=config();cfg['map']['height_pt']=480
        self.assertEqual(480,self.load(cfg)['lanes'][0]['map']['height_pt'])

    def test_duplicate_origins_and_ids_fail(self):
        with self.assertRaisesRegex(ValueError,'duplicate coordinates'):
            self.load(config([observation(),observation()]))
        cfg=config();cfg['lanes']*=2
        with self.assertRaisesRegex(ValueError,'duplicate query_id'):
            self.load(cfg)

    def test_observed_rank_contradictions_fail(self):
        for ranks in ([1,2,3],[4,4],[4,False],list(range(1,30))):
            row=observation();row['observed_ranks']=ranks
            with self.subTest(ranks=ranks),self.assertRaises(ValueError):
                validate_observation(row,'test')

    def test_bounds_crop_adds_appendix_and_rejects_antimeridian(self):
        cfg=config([observation(0),observation(50)])
        cfg['map']['bounds']=[-75.01,39.99,-74.99,40.01]
        lane=self.load(cfg)['lanes'][0]
        self.assertEqual(1,lane['outside_view'])
        self.assertTrue(lane['needs_appendix'])
        for extent in ([170,-1,-170,1],[-181,-1,-170,1],[-75,40,-75,41],[-75,84,-74,89]):
            with self.subTest(extent=extent),self.assertRaises(ValueError):
                bounds(extent)
        cfg=config([observation(0),dict(observation(1),lng=179)])
        with self.assertRaisesRegex(ValueError,'antimeridian'):
            self.load(cfg)

    def test_relative_shared_collector_files_and_multiple_paths(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);cfg=config()
            cfg['lanes'][0].pop('records')
            cfg['lanes'][0]['records_paths']=['a.json','b.json']
            (root/'a.json').write_text(json.dumps([observation(),dict(observation(),query_id='another')]),encoding='utf-8')
            (root/'b.json').write_text(json.dumps({'observations':[observation(1)]}),encoding='utf-8')
            (root/'config.json').write_text(json.dumps(cfg),encoding='utf-8')
            self.assertEqual(2,load_config(root/'config.json')['lanes'][0]['metrics']['sampled'])

    def test_legacy_runner_adapter_uses_actual_statuses_and_checks_identity(self):
        cfg=config();lane=cfg['lanes'][0]
        payload=dict(target=cfg['business']['name'],keyword=lane['query'],measurement_settings={'depth':20},results=[])
        statuses=['found','not_returned_depth_reached','not_returned_incomplete','provider_error','empty_results','no_organic_results','missing_result']
        for i,status in enumerate(statuses):
            payload['results'].append(dict(point={'lat':40+i*.001,'lng':-75},rank=4 if status=='found' else None,
                                           status=status,organic_items_count=20 if i<3 else 0,observed_ranks=list(range(1,21)) if i<2 else []))
        rows=runner_records(payload,lane,cfg['business'])
        for row in rows:
            validate_observation(row,'test')
        self.assertEqual(['found','not_returned','not_returned','error','empty','unmeasured','unmeasured'],[r['state'] for r in rows])
        self.assertEqual(1,metrics(rows)['top10_unknown_absence'])
        self.assertEqual([20,20,0],[r['depth'] for r in rows[:3]])
        self.assertTrue(all(r['requested_depth']==20 for r in rows))
        payload['target']='Wrong business'
        with self.assertRaisesRegex(ValueError,'target'):
            runner_records(payload,lane,cfg['business'])

    def test_legacy_depth_is_observed_and_missing_sequence_stays_unknown(self):
        cfg=config();lane=cfg['lanes'][0]
        row=dict(point={'lat':40,'lng':-75},rank=None,status='not_returned_incomplete',organic_items_count=5,
                 observed_ranks=[1,2,4,6,8])
        payload=dict(measurement_settings={'depth':100},results=[row])
        output=runner_records(payload,lane,cfg['business'])[0]
        self.assertEqual(2,output['depth']);self.assertEqual(100,output['requested_depth'])
        del row['observed_ranks']
        self.assertIsNone(runner_records(payload,lane,cfg['business'])[0]['depth'])
        row['observed_ranks']=[1,False]
        with self.assertRaisesRegex(ValueError,'observed_ranks'):
            runner_records(payload,lane,cfg['business'])

    def test_mixed_sources_are_rejected_and_unknown_sources_are_disclosed(self):
        for source in ('dataforseo-live','runner parsed-grid','unknown label'):
            with self.subTest(source=source),self.assertRaisesRegex(ValueError,'mixed synthetic'):
                self.load(config([observation(),dict(observation(1),source=source)]))
        cfg=config([dict(observation(),source='supplied spreadsheet')]);cfg['synthetic']=False
        model=self.load(cfg)
        self.assertFalse(model['synthetic'])
        self.assertIn('does not independently authenticate',model['evidence_disclosure'])
        row=observation();row.pop('source')
        with self.assertRaisesRegex(ValueError,'source'):
            self.load(config([row]))

    def test_synthetic_fixtures_are_contrasting_and_consistent(self):
        urban=load_config(ROOT/'examples/reports/urban-dentist.json')
        rural=load_config(ROOT/'examples/reports/rural-mobile.json')
        self.assertEqual(3,len(urban['lanes']))
        self.assertEqual(1,len(rural['lanes']))
        for model in (urban,rural):
            self.assertTrue(model['synthetic'])
            for lane in model['lanes']:
                self.assertEqual(lane['metrics']['near_miss'],lane['metrics']['top10']-lane['metrics']['top3'])

    def test_network_paths_and_missing_basemap_attribution_fail(self):
        cfg=config();cfg['lanes'][0].pop('records');cfg['lanes'][0]['records_path']='https://example.invalid/data'
        with self.assertRaisesRegex(ValueError,'local'):
            self.load(cfg)
        cfg=config();cfg['map']['basemap']={'path':'missing.png','crs':'EPSG:3857','bounds':[-76,39,-74,41]}
        with self.assertRaises(ValueError):
            self.load(cfg)


@unittest.skipUnless(RENDERING,'report rendering dependencies not installed')
class RenderTests(unittest.TestCase):
    def render(self,cfg,root,**kwargs):
        path=root/'config.json';path.write_text(json.dumps(cfg),encoding='utf-8')
        return build(path,root/'output',**kwargs)

    def test_two_fixtures_render_offline_with_pdf_bounds(self):
        for name in ('urban-dentist','rural-mobile'):
            with self.subTest(name=name),tempfile.TemporaryDirectory() as folder:
                with patch('socket.socket',side_effect=AssertionError('network forbidden')):
                    result=build(ROOT/f'examples/reports/{name}.json',Path(folder)/'output',require_pdf_qa=PDFIUM)
                self.assertEqual(0,result['network_calls'])
                self.assertTrue(result['layout_boxes'])
                if PDFIUM:
                    self.assertEqual('passed',result['pdf']['status'])
                self.assertTrue(all(a['main']['width_pt']==516 for a in result['maps']))
                if name=='rural-mobile':
                    self.assertEqual(0,result['maps'][0]['full']['outside'])

    def test_light_theme_renders_white_page_with_verification_notes(self):
        import strategy_report
        cfg=json.loads((ROOT/'examples/reports/urban-dentist.json').read_text(encoding='utf-8'))
        cfg['lanes']=[dict(lane,records_path=str(ROOT/'examples/reports'/lane['records_path'])) for lane in cfg['lanes']]
        cfg.update(theme='light',verification_notes=['Synthetic check note.'])
        try:
            with tempfile.TemporaryDirectory() as folder:
                result=self.render(cfg,Path(folder),require_pdf_qa=PDFIUM)
                html=(Path(folder)/'output/report.html').read_text(encoding='utf-8')
                self.assertIn('background:#FFFFFF', html)
                for state in ('error','empty','unmeasured'):
                    self.assertEqual('#FFFFFF',strategy_report.marker_style(state,None)[1])
                self.assertNotIn('checked with jev', html.lower())
                self.assertIn('legends-geogrid', html)
                if PDFIUM:
                    import pypdfium2
                    pdf=pypdfium2.PdfDocument(str(Path(folder)/'output/report.pdf'))
                    try:
                        for page in pdf:
                            bitmap=page.render(scale=.25)
                            self.assertEqual((255,255,255),bitmap.to_pil().convert('RGB').getpixel((1,1)))
                            bitmap.close()
                            page.close()
                    finally:
                        pdf.close()

            if PDFIUM:
                self.assertEqual('passed',result['pdf']['status'])
            self.assertNotIn('class="brand-strip"',html)
            self.assertIn('How the findings were checked',html)
            self.assertIn('class="visibility-table"',html)
            self.assertIn('class="banner"',html)
            self.assertIn('SEARCH KEYWORD',html)
            self.assertIn('color:#000000',html)
        finally:
            strategy_report.apply_theme(strategy_report.DEFAULT_THEME)
        try:
            with tempfile.TemporaryDirectory() as folder:
                result=self.render(dict(cfg,theme='geogrid'),Path(folder),require_pdf_qa=PDFIUM)
                html=(Path(folder)/'output/report.html').read_text(encoding='utf-8')
            if PDFIUM:
                self.assertEqual('passed',result['pdf']['status'])
            self.assertNotIn('class="brand-strip"',html)
            self.assertIn('background:#000000',html)
            self.assertIn('data-design="legends-editorial-v5"',html)
            self.assertIn('class="report-nav"',html)
            self.assertEqual(len(cfg['lanes']),html.count('class="report-lane"'))
            self.assertEqual(len(cfg['lanes']),html.count('<summary>Exact observation ledger</summary>'))
            self.assertLess(html.index('class="report-cover"'),html.index('class="report-lane"'))
            self.assertLess(html.index('class="report-lane"'),html.index('id="next-steps"'))

        finally:
            strategy_report.apply_theme(strategy_report.DEFAULT_THEME)
        with self.assertRaises(ValueError):
            with tempfile.TemporaryDirectory() as folder:
                self.render(dict(cfg,theme='neon'),Path(folder))

    def test_default_dark_and_legacy_light_alias(self):
        from report_model import load_config
        cfg=config()
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'config.json'
            path.write_text(json.dumps(cfg),encoding='utf-8')
            self.assertEqual('geogrid',load_config(path)['theme'])
            cfg['theme']='jev'
            path.write_text(json.dumps(cfg),encoding='utf-8')
            self.assertEqual('light',load_config(path)['theme'])

    @unittest.skipUnless((ROOT/'tools/adaptive_geogrid.py').is_file(),'collector not installed')
    def test_real_collector_replay_feeds_report_without_conversion(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            process=subprocess.run([sys.executable,str(ROOT/'tools/adaptive_geogrid.py'),
                                    '--config',str(ROOT/'examples/adaptive/sample.json'),
                                    '--replay',str(ROOT/'examples/adaptive/replay.json'),
                                    '--output-dir',str(root/'collection')],capture_output=True,text=True)
            self.assertEqual(0,process.returncode,process.stderr)
            cfg=config();cfg['business'].update(lat=40,lng=-100)
            cfg['lanes']=[dict(query_id=q,label=q,query=q,records_path='collection/observations.json') for q in ('pizza','delivery')]
            result=self.render(cfg,root,require_pdf_qa=PDFIUM)
            self.assertEqual(1,result['metrics']['delivery']['near_miss'])
            self.assertEqual(0,result['metrics']['pizza']['near_miss'])
            self.assertEqual(result['metrics']['pizza']['measured'],result['metrics']['delivery']['measured'])
            self.assertEqual(0,result['metrics']['pizza']['top10_unknown_absence'])

    def test_many_lanes_long_names_long_copy_continue_without_shrinking(self):
        cfg=config();cfg['business']['name']='Synthetic '+('Long Business Identity ' * 10)
        cfg['thesis']='Hypothesis only. '+('This is intentionally long user supplied copy with <markup> & punctuation. '*90)
        lane=cfg['lanes'][0]
        lane['label']='A long service name with multiple phrases and a balanced readable heading'
        lane['narrative']='Long supplied interpretation. '*160
        cfg['lanes']=[]
        for i in range(6):
            item=copy.deepcopy(lane);item['query_id']=f'lane{i}';item['records'][0]['query_id']=f'lane{i}'
            cfg['lanes'].append(item)
        with tempfile.TemporaryDirectory() as folder:
            result=self.render(cfg,Path(folder),require_pdf_qa=PDFIUM)
            self.assertEqual(6,len(result['maps']))
            self.assertGreater(max(x['page'] for x in result['layout_boxes']),8)
            html=(Path(folder)/'output/report.html').read_text(encoding='utf-8')
            self.assertIn('&lt;markup&gt;',html)

    def test_dense_irregular_pins_disclose_overlap_without_coordinate_changes(self):
        rows=[dict(observation(i),lat=40+i*.000001,lng=-75+i*.000001) for i in range(120)]
        cfg=config(rows)
        with tempfile.TemporaryDirectory() as folder:
            result=self.render(cfg,Path(folder),require_pdf_qa=PDFIUM)
            self.assertGreater(result['maps'][0]['main']['pin_collisions'],0)
            emitted=json.loads((Path(folder)/'output/report-model.json').read_text(encoding='utf-8'))
            self.assertEqual([r['lat'] for r in rows],[r['lat'] for r in emitted['lanes'][0]['records']])
            self.assertEqual(8,result['maps'][0]['main']['pin_font_pt'])

    def test_failure_never_overwrites_existing_output(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'output').mkdir();(root/'output/keep.txt').write_text('user work')
            with self.assertRaisesRegex(ValueError,'preserved'):
                self.render(config(),root)
            self.assertEqual('user work',(root/'output/keep.txt').read_text())
            self.assertFalse((root/'output/report.pdf').exists())

    def test_unsupported_glyph_fails_explicitly(self):
        cfg=config();cfg['business']['name']='Synthetic \U0001f9ea'
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaisesRegex(ValueError,'glyphs'):
                self.render(cfg,Path(folder))

    def test_display_normalizes_em_dashes_without_mutating_evidence(self):
        import reportlab
        cfg=config()
        cfg['business']['name']='Synthetic Name\u2014Long Form'
        cfg['business']['location']='Town\u2014Region'
        cfg['thesis']='Hypothesis\u2014not proven'
        cfg['objectives']=['Observe\u2014then review']
        cfg['next_actions']=['User action\u2014verify']
        cfg['missing_evidence']=['Demand\u2014unknown']
        lane=cfg['lanes'][0]
        lane.update(label='Service\u2014Area',query='Query\u2014Original',narrative='User\u2014interpretation')
        lane['records'][0]['source']='synthetic\u2014replay'
        font_root=Path(reportlab.__file__).parent/'fonts'
        cfg['fonts']={key:str(font_root/name) for key,name in
                      [('regular','Vera.ttf'),('bold','VeraBd.ttf'),('title','Vera.ttf')]}
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            self.render(cfg,root,require_pdf_qa=PDFIUM)
            html=(root/'output/report.html').read_text(encoding='utf-8')
            self.assertNotIn('\u2014',html)
            self.assertIn('Synthetic Name - Long Form',html)
            saved=json.loads((root/'output/report-model.json').read_text(encoding='utf-8'))
            self.assertEqual('Query\u2014Original',saved['lanes'][0]['query'])
            if PDFIUM:
                import pypdfium2
                with pypdfium2.PdfDocument(str(root/'output/report.pdf')) as doc:
                    for page in doc:
                        tp=page.get_textpage()
                        self.assertNotIn('\u2014',tp.get_text_range())
                        tp.close();page.close()

    def test_market_center_disclosure_survives_pdf_html_and_map_ledger(self):
        cfg=config();cfg.update(center_kind='market',center_label='Synthetic town square\u2014market reference')
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);result=self.render(cfg,root,require_pdf_qa=PDFIUM)
            self.assertEqual('market',result['maps'][0]['main']['center_kind'])
            html=(root/'output/report.html').read_text(encoding='utf-8')
            self.assertIn('Market scan center: Synthetic town square - market reference',html)
            self.assertIn('not a verified physical business location',html)
            self.assertNotIn('Business origin:',html)
            saved=json.loads((root/'output/report-model.json').read_text())
            self.assertEqual((40,-75),tuple(saved['business'][k] for k in ('lat','lng')))
            if PDFIUM:
                import pypdfium2
                with pypdfium2.PdfDocument(str(root/'output/report.pdf')) as doc:
                    all_text=[]
                    for page_index in range(len(doc)):
                        page=doc[page_index];tp=page.get_textpage()
                        content=' '.join(tp.get_text_range().split())
                        all_text.append(content)
                        if page_index == 0 or 'Rings:' in content:
                            self.assertIn('Market scan center: Synthetic town square - market reference',content)
                            self.assertIn('not a verified physical business location',content)
                        self.assertNotIn('Business origin:',content)
                        self.assertNotIn('origins and business location',content)
                        tp.close();page.close()
                    self.assertIn('origins and the declared market reference',' '.join(all_text))

    def test_mile_labels_captions_and_legends_do_not_change_geometry(self):
        from strategy_report import map_caption,brief_caption
        cfg=config();cfg['map'].update(bounds=[-75.2,39.8,-74.8,40.2],
                                       radius_bands_km=[1.609344,4.828032,8.04672],distance_unit='mi')
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);result=self.render(cfg,root,require_pdf_qa=PDFIUM)
            asset=result['maps'][0]['main']
            self.assertEqual(['1 mi','3 mi','5 mi'],[label['label'] for label in asset['band_labels']])
            html=(root/'output/report.html').read_text(encoding='utf-8')
            self.assertIn('Rings: mi',html);self.assertIn('Neutral bands: 1, 3, 5 mi',html)
            self.assertNotIn('Rings: km',html)
            self.assertIn('Rings: 1, 3, 5 mi',brief_caption(asset))
            omitted=copy.deepcopy(asset);omitted['omitted_radius_bands_km']=[16.09344]
            self.assertIn('Bands omitted outside view: 10 mi.',map_caption({'map':cfg['map']},omitted))
            cfg['map']['distance_unit']='km'
            model=ModelTests().load(cfg);fonts=register_fonts(model)
            km_asset=map_image(model['lanes'][0],model['business'],root/'km.png',fonts)
            self.assertEqual(asset['bounds'],km_asset['bounds'])
            self.assertEqual(asset['marker_geometry'],km_asset['marker_geometry'])
            self.assertEqual(asset['ring_geometry'],km_asset['ring_geometry'])
            self.assertEqual(asset['drawn_radius_bands_km'],km_asset['drawn_radius_bands_km'])
            self.assertEqual('passed',map_qa(model['lanes'][0],model['business'],km_asset,root/'km.png',fonts)['status'])
            self.assertEqual('1.60934 km',km_asset['band_labels'][0]['label'])
            if PDFIUM:
                import pypdfium2
                with pypdfium2.PdfDocument(str(root/'output/report.pdf')) as doc:
                    map_page=next(box['page'] for box in result['layout_boxes'] if box['kind']=='map')
                    page=doc[map_page-1];tp=page.get_textpage();text=' '.join(tp.get_text_range().split())
                    self.assertIn('Rings: mi',text);self.assertIn('Rings: 1, 3, 5 mi',text)
                    self.assertNotIn(' km',text)
                    tp.close();page.close()

    @unittest.skipUnless(PDFIUM,'PDFium required')
    def test_customer_headings_keep_hypothesis_and_complete_appendix_lanes(self):
        import pypdfium2
        cfg=config()
        cfg['next_actions']=['Verify the supplied observation baseline.']
        cfg['missing_evidence']=['Demand and causation remain unverified.']
        cfg['lanes']=[dict(query_id=f'lane{i}',label=f'Synthetic service {i}',query=f'service {i}',
                           narrative='Visibility could vary by origin.',
                           records=[dict(observation(),query_id=f'lane{i}')]) for i in range(4)]
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);self.render(cfg,root,require_pdf_qa=True)
            html=(root/'output/report.html').read_text(encoding='utf-8')
            with pypdfium2.PdfDocument(str(root/'output/report.pdf')) as doc:
                pages=[]
                for index in range(len(doc)):
                    page=doc[index];tp=page.get_textpage()
                    pages.append(' '.join(tp.get_text_range().split()))
                    tp.close();page.close()
            pdf=' '.join(pages)
            for content in (html,pdf):
                for heading in ('Working assessment','Objectives','Recommended next steps','What remains unverified'):
                    self.assertIn(heading.lower(),content.lower())
                self.assertIn('Hypothesis, not an established finding:',content)
                self.assertNotIn('Objectives - user supplied',content)
                self.assertNotIn('User-supplied interpretation',content)
            start=next(i for i,text in enumerate(pages) if 'Evidence & denominator appendix' in text)
            appendix=pages[start:]
            self.assertGreater(len(appendix),1)
            self.assertEqual(4,sum(text.count('Observed top 10 share:') for text in appendix))
            for text in appendix:
                heading_count=text.count('SEARCH KEYWORD')
                self.assertEqual(heading_count,text.count('Sources:'))
                self.assertEqual(heading_count,text.count('Evidence bounds ['))
                self.assertEqual(heading_count,text.count('Observed top 10 share:'))

    @unittest.skipUnless(PDFIUM,'PDFium required')
    def test_negative_font_bearing_at_wrapped_line_start_stays_in_bounds(self):
        import reportlab
        font_root=Path(reportlab.__file__).parent/'fonts'
        cfg=config()
        cfg['fonts']={'regular':str(font_root/'VeraIt.ttf'),'bold':str(font_root/'VeraBd.ttf')}
        cfg['next_actions']=['A preceding line.\njustified checks remain inside the fixed page margins.\n'+
                             'https://example.invalid/'+'j'*200]
        with tempfile.TemporaryDirectory() as folder:
            result=self.render(cfg,Path(folder),require_pdf_qa=True)
            self.assertEqual('passed',result['pdf']['status'])
            self.assertTrue(all(page['out_of_bounds_glyphs']==0 for page in result['pdf']['pages']))

    @unittest.skipUnless(PDFIUM,'PDFium required')
    def test_pdf_qa_rejects_forbidden_em_dash(self):
        from reportlab.pdfgen.canvas import Canvas
        from reportlab.lib.colors import HexColor
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'bad.pdf'
            register_fonts(ModelTests().load(config()))
            c=Canvas(str(path),pagesize=(612,792))
            c.setFillColor(HexColor('#08131E'));c.rect(0,0,612,792,fill=1,stroke=0)
            c.setFillColor(HexColor('#F3F6F8'));c.setFont('ReportBody',11)
            c.drawString(48,700,'A forbidden\u2014dash in otherwise sufficient report text for QA.')
            c.save()
            result=pdf_qa(path,required=True)
            self.assertEqual('failed',result['status'])
            self.assertIn('page 1: forbidden em dash',result['issues'])

    def test_not_returned_ring_is_visible_hollow_and_distinct_from_unmeasured(self):
        from PIL import Image,ImageColor
        from strategy_report import MUTED,PANEL,SCALE,marker_label,marker_style
        cfg=config([observation(1,state='not_returned'),observation(8,state='unmeasured')])
        cfg['map'].update(radius_bands_km=[],bounds=[-75.02,39.98,-74.94,40.05])
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);result=self.render(cfg,root,require_pdf_qa=PDFIUM)
            asset=result['maps'][0]['main'];marker=asset['marker_geometry'][0]
            self.assertEqual(4.25*SCALE,marker['radius_px'])
            self.assertEqual('',marker['label'])
            x,y=map(int,marker['center_px']);top=int(marker['footprint_px'][1])
            with Image.open(root/'output'/asset['file']) as image:
                self.assertEqual(ImageColor.getrgb(PANEL),image.getpixel((x,y)))
                for dy in range(3):
                    self.assertEqual(ImageColor.getrgb(MUTED),image.getpixel((x,top+dy)))
                self.assertEqual(ImageColor.getrgb(PANEL),image.getpixel((x,top+3)))
            self.assertEqual('U',marker_label('unmeasured',None))
            self.assertIsNotNone(marker_style('unmeasured',None)[0])
            html=(root/'output/report.html').read_text(encoding='utf-8')
            self.assertIn('border:1px solid '+MUTED+'"></span>Not returned',html)
            self.assertIn('background:#00FF00"></span>Ranks 1–3',html)

    def test_rank_palette_and_neutral_annuli(self):
        from PIL import Image
        from strategy_report import marker_style,shade_bands
        self.assertEqual(('#00FF00','#000000'),marker_style('found',3))
        self.assertEqual(('#FFFF00','#000000'),marker_style('found',4))
        self.assertEqual(('#FFFF00','#000000'),marker_style('found',10))
        self.assertEqual(('#FF0000','#FFFFFF'),marker_style('found',11))
        overlay=Image.new('RGBA',(100,100))
        shade_bands(overlay,[{'points_px':[(40,40),(60,40),(60,60),(40,60),(40,40)]},
                             {'points_px':[(20,20),(80,20),(80,80),(20,80),(20,20)]}])
        self.assertEqual((255,255,255,34),overlay.getpixel((50,50)))
        self.assertEqual((255,255,255,12),overlay.getpixel((30,30)))
        self.assertEqual((0,0,0,0),overlay.getpixel((5,5)))

    def test_basemap_reprojects_instead_of_stretching_and_requires_attribution(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            source=Image.new('RGB',(100,100),'red')
            for y in range(50,100):
                for x in range(100):source.putpixel((x,y),(0,0,255))
            source.save(root/'base.png')
            base=dict(path=str(root/'base.png'),bounds=[-1,0,1,80],crs='EPSG:4326',attribution='Synthetic image; test-owned',
                      attribution_policy='separate-caption',overlay_safe=True)
            image=georeferenced_image(base,[-1,0,1,80],100,100)
            # Mercator midpoint latitude is ~57 degrees: still the red upper half.
            self.assertGreater(image.getpixel((50,50))[0],200)
            base['crs']='EPSG:3857'
            image=georeferenced_image(base,[-1,0,1,80],100,100)
            self.assertGreater(image.getpixel((50,60))[2],200)
            # Extent outside source stays transparent instead of filling by stretching.
            image=georeferenced_image(base,[-2,0,2,80],100,100)
            self.assertEqual(0,image.getpixel((5,50))[3])
            cfg=config();base.update(path='base.png',bounds=[-75.1,39.9,-74.9,40.1]);cfg['map']['basemap']=base
            result=self.render(cfg,root,require_pdf_qa=PDFIUM)
            self.assertEqual('Synthetic image; test-owned',result['maps'][0]['main']['attribution'])
            saved=(root/'output/report-model.json').read_text(encoding='utf-8')
            self.assertNotIn(str(root).replace('\\','\\\\'),saved)
            cfg['map']['basemap'].pop('attribution');(root/'bad.json').write_text(json.dumps(cfg))
            with self.assertRaisesRegex(ValueError,'attribution'):
                load_config(root/'bad.json')

    def test_long_unbroken_tokens_wrap_at_readable_floor(self):
        cfg=config();cfg['business']['name']='W'*280
        cfg['thesis']='unbroken_'+'m'*1500
        cfg['lanes'][0]['label']='LongQuery'+'X'*240
        cfg['lanes'][0]['narrative']='abc123'*400
        with tempfile.TemporaryDirectory() as folder:
            result=self.render(cfg,Path(folder),require_pdf_qa=PDFIUM)
            self.assertTrue(all(b.get('font_size_pt',8.5)>=8.5 for b in result['layout_boxes']))
            self.assertIn('m'*1500,(Path(folder)/'output/report.html').read_text(encoding='utf-8'))

    def test_missing_pdf_qa_dependency_fails_closed_when_required(self):
        with tempfile.TemporaryDirectory() as folder,patch.dict(sys.modules,{'pypdfium2':None}):
            root=Path(folder)
            with self.assertRaisesRegex(ValueError,'pypdfium2 required'):
                self.render(config(),root,require_pdf_qa=True)
            self.assertFalse((root/'output/report.pdf').exists())
            self.assertEqual('skipped',pdf_qa(root/'unused.pdf')['status'])

    def test_all_empty_unknown_and_missing_absence_render_honestly(self):
        for state in ('empty','unmeasured','error','not_returned'):
            with self.subTest(state=state),tempfile.TemporaryDirectory() as folder:
                root=Path(folder);cfg=config([observation(state=state)])
                result=self.render(cfg,root,require_pdf_qa=PDFIUM)
                html=(root/'output/report.html').read_text(encoding='utf-8')
                if state=='not_returned':
                    self.assertEqual(1,result['metrics']['test']['top3_unknown_absence'])
                    self.assertIn('Unknown absence: top 3 = 1; top 10 = 1',html)
                else:
                    self.assertIsNone(result['metrics']['test']['top3_observed_share'])
                    self.assertIn('Shares are undefined, not zero visibility',html)
                    self.assertNotIn('0/0',html)

    def test_supplied_unknown_source_disclosure_survives_pdf_and_html(self):
        cfg=config([dict(observation(),source='user spreadsheet')]);cfg['synthetic']=False;cfg['map']['provider']='schematic'
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);self.render(cfg,root,require_pdf_qa=PDFIUM)
            self.assertIn('this renderer does not independently authenticate source labels or origin records',
                          (root/'output/report.html').read_text(encoding='utf-8'))
            if PDFIUM:
                import pypdfium2
                with pypdfium2.PdfDocument(str(root/'output/report.pdf')) as doc:
                    page=doc[0];tp=page.get_textpage()
                    self.assertIn('User-supplied evidence',tp.get_text_range())
                    tp.close();page.close()

    def test_nonsquare_basemap_stays_continuous_with_credits_in_place(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            result=build(ROOT/'examples/reports/georeferenced-mobile.json',root/'output',require_pdf_qa=PDFIUM)
            asset=result['maps'][0]['main'];qa=result['map_validation'][0]['main']
            self.assertEqual([1280,704],asset['basemap_native_pixels'])
            self.assertEqual([1548,1356],qa['native_pixels'])
            self.assertEqual(516,qa['geographic_plot_pt']['width'])
            self.assertNotEqual(asset['requested_bounds'],asset['bounds'])
            self.assertEqual(1356,asset['geographic_height_px'])
            self.assertEqual([216,216],qa['effective_ppi'])
            self.assertTrue(qa['protected_credit_pixels_checked'])
            model=load_config(ROOT/'examples/reports/georeferenced-mobile.json')
            base=model['lanes'][0]['map']['basemap']
            self.assertEqual(base['bounds'],asset['bounds'])
            frame=asset['geographic_frame_px']
            expected=georeferenced_image(base,base['bounds'],frame[2]-frame[0],frame[3]-frame[1]).convert('RGB')
            box=asset['protected_credit_box_px']
            self.assertEqual(frame[3],box[3])
            self.assertGreater(box[1],frame[1])
            with Image.open(root/'output'/asset['file']) as rendered:
                local=[box[0]-frame[0],box[1]-frame[1],box[2]-frame[0],box[3]-frame[1]]
                self.assertEqual(expected.crop(local).tobytes(),rendered.crop(box).tobytes())
                # A quiet left-edge column crosses the old slice boundary. Both
                # sides must match ONE continuous transform, with no inset/gap.
                crossing=[frame[0]+12,box[1]-24,frame[0]+18,box[3]]
                local=[crossing[0]-frame[0],crossing[1]-frame[1],crossing[2]-frame[0],crossing[3]-frame[1]]
                self.assertEqual(expected.crop(local).tobytes(),rendered.crop(crossing).tobytes())
            self.assertEqual(17,qa['markers_checked'])
            self.assertGreater(qa['rings_checked'],0)

    def test_optional_480pt_main_map_retains_credits_and_single_page_brief(self):
        cfg=json.loads((ROOT/'examples/reports/georeferenced-mobile.json').read_text(encoding='utf-8'))
        cfg['lanes'][0]['records_path']=str(ROOT/'examples/reports/rural-mobile-observations.json')
        cfg['map']['basemap']['path']=str(ROOT/'examples/reports/synthetic-georeferenced.png')
        cfg['map']['height_pt']=480
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);result=self.render(cfg,root,require_pdf_qa=PDFIUM)
            asset=result['maps'][0]['main']
            self.assertEqual([1548,1440],asset['native_pixels'])
            self.assertEqual([216,216],asset['effective_ppi'])
            self.assertEqual(480,asset['height_pt'])
            self.assertEqual(516,asset['geographic_plot_pt']['width'])
            self.assertTrue(result['map_validation'][0]['main']['protected_credit_pixels_checked'])
            self.assertEqual(17,result['map_validation'][0]['main']['markers_checked'])
            map_pages=[b['page'] for b in result['layout_boxes'] if b['kind']=='map']
            self.assertEqual(1,len(map_pages))
            self.assertGreaterEqual(map_pages[0],2) # custom fonts can extend the introduction
            if PDFIUM:
                import pypdfium2
                with pypdfium2.PdfDocument(str(root/'output/report.pdf')) as doc:
                    page=doc[map_pages[0]-1];tp=page.get_textpage()
                    self.assertIn('Measured:',tp.get_text_range())
                    tp.close();page.close()

    def test_map_qa_rejects_bad_counts_clipped_markers_rings_and_modified_credit(self):
        from PIL import Image
        model=load_config(ROOT/'examples/reports/georeferenced-mobile.json');lane=model['lanes'][0]
        fonts=register_fonts(model)
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'map.png';asset=map_image(lane,model['business'],path,fonts)
            self.assertEqual('passed',map_qa(lane,model['business'],asset,path,fonts)['status'])
            changes=[lambda a:a.update(plotted=a['plotted']+1),
                     lambda a:a['marker_geometry'][0].update(radius_px=500),
                     lambda a:a['marker_geometry'][0].update(center_px=[1547,500]),
                     lambda a:a['ring_geometry'][0]['points_px'].pop(),
                     lambda a:a.update(effective_ppi=[72,72])]
            for change in changes:
                broken=copy.deepcopy(asset);change(broken)
                with self.assertRaises(ValueError):map_qa(lane,model['business'],broken,path,fonts)
            image=Image.open(path).convert('RGB');box=asset['protected_credit_box_px'];image.putpixel((box[0]+2,box[1]+2),(255,0,0));image.save(path)
            with self.assertRaisesRegex(ValueError,'credit pixels'):
                map_qa(lane,model['business'],asset,path,fonts)
            for geometry in (asset['marker_geometry'][0]['center_px'],asset['ring_geometry'][0]['points_px'][0]):
                asset=map_image(lane,model['business'],path,fonts)
                with Image.open(path) as original:image=original.convert('RGB')
                image.putpixel(tuple(int(v) for v in geometry),(255,0,255));image.save(path)
                with self.assertRaisesRegex(ValueError,'painted pixels'):
                    map_qa(lane,model['business'],asset,path,fonts)

    def test_basemap_without_declared_attribution_policy_fails(self):
        cfg=json.loads((ROOT/'examples/reports/georeferenced-mobile.json').read_text(encoding='utf-8'))
        cfg['lanes'][0]['records_path']=str(ROOT/'examples/reports/rural-mobile-observations.json')
        cfg['map']['basemap']['path']=str(ROOT/'examples/reports/synthetic-georeferenced.png')
        cfg['map']['basemap'].pop('protected_bottom_px');cfg['map']['basemap'].pop('attribution_policy')
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaisesRegex(ValueError,'attribution_policy'):
                self.render(cfg,Path(folder))

    def test_legacy_detached_credit_mode_requires_complete_image_migration(self):
        cfg=json.loads((ROOT/'examples/reports/georeferenced-mobile.json').read_text(encoding='utf-8'))
        cfg['lanes'][0]['records_path']=str(ROOT/'examples/reports/rural-mobile-observations.json')
        base=cfg['map']['basemap']
        base['path']=str(ROOT/'examples/reports/synthetic-georeferenced.png')
        base['credit_strip_px']=base.pop('protected_bottom_px')
        for policy in ('preserve-bottom-strip',None):
            base['attribution_policy']=policy
            with self.subTest(policy=policy),tempfile.TemporaryDirectory() as folder:
                with self.assertRaisesRegex(ValueError,'COMPLETE image'):
                    self.render(cfg,Path(folder))
        with self.assertRaisesRegex(ValueError,'detached credit strips'):
            georeferenced_image(base,base['bounds'],100,100)

    def test_embedded_credits_default_to_in_place_and_reject_marker_overlap(self):
        cfg=json.loads((ROOT/'examples/reports/georeferenced-mobile.json').read_text(encoding='utf-8'))
        cfg['lanes'][0]['records_path']=str(ROOT/'examples/reports/rural-mobile-observations.json')
        base=cfg['map']['basemap'];base['path']=str(ROOT/'examples/reports/synthetic-georeferenced.png')
        base.pop('attribution_policy')
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);cfgpath=root/'config.json';cfgpath.write_text(json.dumps(cfg))
            model=load_config(cfgpath);lane=model['lanes'][0];fonts=register_fonts(model)
            self.assertEqual('preserve-in-place',lane['map']['basemap']['attribution_policy'])
            lane['records'][0].update(lat=40.66,lng=-100.77)
            with self.assertRaisesRegex(ValueError,'marker overlaps embedded credits'):
                map_image(lane,model['business'],root/'map.png',fonts)
            lane['map']['bounds'][0]-=1
            with self.assertRaisesRegex(ValueError,'cover the requested view'):
                map_image(lane,model['business'],root/'map.png',fonts)

    def test_projection_retains_geometry_and_extreme_latitude(self):
        projection=Projection([-76,39,-74,41])
        a=projection.point(40,-75)
        b=projection.point(40,-74.9)
        c=projection.point(40,-75.1)
        self.assertAlmostEqual(b[0]-a[0],a[0]-c[0])
        cfg=config([dict(observation(),lat=84.9,lng=179.9)])
        cfg['business'].update(lat=84.9,lng=179.9)
        with tempfile.TemporaryDirectory() as folder:
            result=self.render(cfg,Path(folder),require_pdf_qa=PDFIUM)
            self.assertEqual(1,result['maps'][0]['main']['plotted'])

    def test_cli_bad_config_is_nonzero_without_traceback(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'bad.json';path.write_text('{}')
            result=subprocess.run([sys.executable,str(ROOT/'tools/strategy_report.py'),'--config',str(path),'--output-dir',str(Path(folder)/'out')],capture_output=True,text=True)
            self.assertEqual(2,result.returncode)
            self.assertIn('schema_version',result.stderr)
            self.assertNotIn('Traceback',result.stderr)


if __name__=='__main__':
    unittest.main()


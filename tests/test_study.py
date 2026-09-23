"""Credential-free tests of study lineage and pre-HTTP spending barriers."""
import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from study_contract import validate, digest
from study import research, run, website, assemble_report


def fixture(root):
    sources=[]
    def source(sid,kind,value):
        p=root/(sid+'.json');p.write_text(json.dumps(value))
        sources.append(dict(id=sid,kind=kind,file=p.name,sha256=digest(p),observed_at=datetime.now(timezone.utc).isoformat(),url='https://example.org/'+sid))
    def envelope(data,item):
        return dict(status_code=20000,tasks=[dict(status_code=20000,data=data,result=[dict(items=[item])])])
    source('site','website',dict(text='Example Pizza, 1 Main Street. Pizza delivery and dine-in.'))
    source('gbp','gbp',envelope({},dict(cid='123',latitude=40.,longitude=-75.,url='https://example.org/',title='Example Pizza',category='Pizza restaurant')))
    source('demand','demand',envelope(dict(keywords=['pizza restaurant']),dict(keyword='pizza restaurant')))
    for i,lat in enumerate([40.,40.001,39.999]):
        source('pilot'+str(i),'maps_probe',envelope(dict(keyword='pizza restaurant',location_coordinate=f'{lat},-75,15z',language_code='en',device='desktop',search_this_area=True,depth=20),dict(title='Example Pizza',category='Pizza restaurant')))
    ref=lambda sid,p,q:dict(source_id=sid,pointer=p,quote=q)
    plan=dict(schema='geogrid-study/v1',business=dict(name='Example Pizza',cid='123',domain='example.org',location_label='Example town',lat=40.,lng=-75.),sources=sources,
        identity=dict(source_id='gbp',pointer='/tasks/0/result/0/items/0',website_reference=ref('site','/text','1 Main Street'),reconciliation='Address and business identity agree.'),
        settings=dict(method='standard',grid_size=3,radius_km=1,depth=20,zoom=15,device='desktop',search_this_area=True,language_code='en',se_domain='google.com',geography_reason='Local catchment baseline, not a service boundary.',decision='Measure nearby discovery for pizza.'),
        queries=[dict(query='pizza restaurant',selected=True,role='category',reason='Verified category and offering.',offering_evidence=[ref('site','/text','Pizza delivery')],demand_source='demand',demand_scope='US monthly, not town-level demand.',intent_assessment='Pilot returns pizza restaurants.',limitations='National demand cannot establish local conversion.',pilot_sources=['pilot0','pilot1','pilot2'],intent_evidence=[ref('pilot0','/tasks/0/result/0/items/0/category','Pizza restaurant')])])
    plan['queries'][0]['theme']=dict(id='category',label='Pizza category',customer_need='Find a pizza restaurant nearby',distinct_value='Broad category discovery')
    plan['selection']=dict(coverage_summary='Focused fixture for category discovery; service lanes not piloted.',evidence=[ref('site','/text','Pizza delivery'),ref('gbp','/tasks/0/result/0/items/0/category','Pizza restaurant')],fewer_themes=dict(reason='Only the category pilot is available in this bounded fixture; not a complete business study.',evidence=[ref('gbp','/tasks/0/result/0/items/0/category','Pizza restaurant')]))
    path=root/'plan.json';path.write_text(json.dumps(plan));return path,plan

class StudyTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name);self.path,self.plan=fixture(self.root)
    def save(self):self.path.write_text(json.dumps(self.plan))
    def rejects(self,text):
        self.save()
        with self.assertRaisesRegex(ValueError,text):validate(self.path)
    def test_valid_and_no_spend_preview(self):
        self.assertEqual(validate(self.path)[1]['selected_queries'],['pizza restaurant'])
        with patch('study.subprocess.run') as call:run(self.path,self.root/'out');call.assert_not_called()
        self.assertFalse((self.root/'out').exists())
    def test_absolute_source_path_rejected(self):
        self.plan['sources'][0]['file']=str(self.root/'site.json');self.rejects('escapes')
    def test_successful_run_freezes_evidence_and_controls(self):
        out=self.root/'collected'
        def fake_collect(argv,**kwargs):
            from local_heatmap_poc import parse_args, generate_grid, PointResult, write_outputs
            import subprocess
            args=parse_args(argv[2:])
            points=generate_grid(args.center_lat,args.center_lng,args.grid_size,args.radius_km)
            rows=[PointResult(p,2,{'cid':'123','title':'Example Pizza'},[],status='found',returned_items_count=3,organic_items_count=3,observed_ranks=(1,2,3)) for p in points]
            outputs=write_outputs(args,[],{'cost':0,'tasks':[]},rows)
            return subprocess.CompletedProcess(argv,0,stdout=json.dumps({'outputs':outputs}))
        with patch('study.subprocess.run',side_effect=fake_collect) as collect:
            result=run(self.path,out,True,1)
        self.assertEqual(result['status'],'report_handoff_ready')
        self.assertEqual(validate(out/'evidence/study-plan.json')[1]['selected_queries'],['pizza restaurant'])
        argv=collect.call_args.args[0]
        self.assertEqual(argv[argv.index('--target-cid')+1],'123')
        self.assertIn('--search-this-area',argv)
        cfg=json.loads((out/'report-config.json').read_text())
        self.assertEqual(cfg['business']['location'],'Example town')
        self.assertIn('Focused scope reason:',cfg['verification_notes'][0])
        self.assertIn('Pizza category',cfg['lanes'][0]['narrative'])
        from report_model import load_config
        model=load_config(out/'report-config.json')
        self.assertEqual(len(model['lanes'][0]['records']),9)
        self.assertNotEqual(Path(cfg['lanes'][0]['records_path']).parent,out/'lane-1')
        (out/'lane-1/collector-output.json').unlink() # legacy interrupted wrapper recovery
        with patch('study.subprocess.run') as collect:
            recovered=assemble_report(out,out/'recovered.json');collect.assert_not_called()
        self.assertEqual(recovered['assembly_provider_calls'],0)
        parsed=Path(cfg['lanes'][0]['records_path']);v=json.loads(parsed.read_text());v['measurement_settings']['target_cid']='wrong';parsed.write_text(json.dumps(v))
        with self.assertRaisesRegex(ValueError,'settings mismatch'):assemble_report(out,out/'wrong.json')
    def test_website_failure_never_becomes_evidence(self):
        out=self.root/'capture.json'
        with patch('urllib.request.urlopen',side_effect=OSError('HTTP 500')):
            with self.assertRaises(OSError):website('https://example.org/',out)
        self.assertFalse(out.exists())
    def test_website_strips_script_and_retains_text(self):
        import io
        from email.message import Message
        response=io.BytesIO(b'<h1>Pizza delivery</h1><script>fake service</script>')
        response.headers=Message();response.geturl=lambda:'https://example.org/'
        out=self.root/'capture.json'
        with patch('urllib.request.urlopen',return_value=response):result=website('https://example.org/',out)
        self.assertEqual(json.loads(out.read_text())['text'],'Pizza delivery')
        self.assertEqual(result['sha256'],digest(out))
    def expand_themes(self,count):
        import copy
        terms=['pizza restaurant','pizza delivery','pizza catering','vegan pizza','gluten free pizza','pizza takeaway'][:count]
        site=self.root/'site.json';site.write_text(json.dumps(dict(text='Example Pizza, 1 Main Street. Pizza delivery and dine-in. Offerings: '+', '.join(terms))))
        self.plan['sources'][0]['sha256']=digest(site)
        demand=self.root/'demand.json';v=json.loads(demand.read_text());v['tasks'][0]['data']['keywords']=terms;demand.write_text(json.dumps(v));self.plan['sources'][2]['sha256']=digest(demand)
        original=copy.deepcopy(self.plan['queries'][0])
        for n,term in enumerate(terms[1:],1):
            q=copy.deepcopy(original);q['query']=term;q['theme']=dict(id='theme'+str(n),label=term,customer_need='Find '+term,distinct_value='Offering-specific discovery for '+term)
            q['offering_evidence']=[dict(source_id='site',pointer='/text',quote=term)]
            pilots=[]
            for i in range(3):
                old=next(x for x in self.plan['sources'] if x['id']=='pilot'+str(i));v=json.loads((self.root/old['file']).read_text());v['tasks'][0]['data']['keyword']=term
                sid=f'lane{n}pilot{i}';p=self.root/(sid+'.json');p.write_text(json.dumps(v));src=dict(old,id=sid,file=p.name,sha256=digest(p));self.plan['sources'].append(src);pilots.append(sid)
            q['pilot_sources']=pilots;q['intent_evidence'][0]['source_id']=pilots[0];self.plan['queries'].append(q)
        self.save()
    def test_three_and_five_theme_studies(self):
        self.expand_themes(5);self.plan['selection'].pop('fewer_themes');self.save()
        receipt=validate(self.path)[1];self.assertEqual(len(receipt['selected_themes']),5);self.assertEqual(receipt['scope'],'standard')
        self.plan['queries']=self.plan['queries'][:3];self.save();self.assertEqual(len(validate(self.path)[1]['selected_themes']),3)
    def test_one_or_two_themes_need_explanation(self):
        self.plan['selection'].pop('fewer_themes');self.rejects('explicit reason')
        self.expand_themes(2);self.rejects('explicit reason')
    def test_narrow_scope_needs_citation(self):
        self.plan['selection']['fewer_themes']['evidence']=[];self.rejects('supporting evidence')
    def test_duplicate_theme_cannot_pad_count(self):
        self.expand_themes(3);self.plan['queries'][1]['theme']['id']=' CATEGORY ';self.rejects('duplicate themes')
    def test_six_themes_exceeds_baseline(self):
        self.expand_themes(6);self.rejects('three to five')
    def test_selection_must_consider_website_and_gbp(self):
        self.plan['selection']['evidence']=self.plan['selection']['evidence'][:1];self.rejects('website and GBP')
    def test_theme_needs_customer_question(self):
        self.plan['queries'][0]['theme'].pop('customer_need');self.rejects('customer_need')
    def restrict_to_profile(self):
        self.plan['evidence_mode']='profile_supported';self.plan['website_limitation']='Official site unavailable from two retrieval methods; no website-only services inferred.'
        self.plan['sources']=self.plan['sources'][1:]
        ref=dict(source_id='gbp',pointer='/tasks/0/result/0/items/0/category',quote='Pizza restaurant')
        self.plan['queries'][0]['offering_evidence']=[ref];self.plan['selection']['evidence']=[ref];self.plan['identity'].pop('website_reference')
        for method in ['http','browser']:
            p=self.root/(method+'.json');p.write_text(json.dumps(dict(url='https://example.org/',status='unavailable',http_status=500,method=method)))
            self.plan['sources'].append(dict(id=method,kind='website_attempt',file=p.name,sha256=digest(p),observed_at=datetime.now(timezone.utc).isoformat(),url='https://example.org/'))
        self.save()
    def test_profile_supported_retains_demand_and_pilot_requirements(self):
        self.restrict_to_profile();receipt=validate(self.path)[1];self.assertEqual(receipt['evidence_mode'],'profile_supported');self.assertIn('unavailable',receipt['website_limitation'])
        self.plan['queries'][0]['pilot_sources']=[];self.rejects('three pilot')
    def test_restricted_requires_two_retrieval_methods(self):
        self.restrict_to_profile();self.plan['sources'].pop();self.rejects('HTTP and browser')
    def test_restricted_wrong_site_is_not_failure_proof(self):
        self.restrict_to_profile();p=self.root/'http.json';v=json.loads(p.read_text());v['url']='https://wrong.example/';p.write_text(json.dumps(v));self.plan['sources'][-2]['sha256']=digest(p);self.rejects('domain mismatch')
    def test_restricted_successful_site_is_not_failure(self):
        self.restrict_to_profile();p=self.root/'http.json';v=json.loads(p.read_text());v['http_status']=200;p.write_text(json.dumps(v));self.plan['sources'][-2]['sha256']=digest(p);self.rejects('HTTP failure')
    def test_restricted_cannot_use_missing_website_offering(self):
        self.restrict_to_profile();self.plan['queries'][0]['offering_evidence']=[dict(source_id='site',pointer='/text',quote='Pizza delivery')];self.rejects('unknown citation')
    def test_missing_website(self):
        self.plan['sources']=self.plan['sources'][1:];self.rejects('required website')
    def test_changed_evidence(self):
        (self.root/'site.json').write_text('{}');self.rejects('hash mismatch')
    def test_fabricated_quote(self):
        self.plan['queries'][0]['offering_evidence'][0]['quote']='invented offering';self.rejects('not present')
    def test_wrong_cid(self):
        self.plan['business']['cid']='456';self.rejects('CID differs')
    def test_domain_substring_not_identity(self):
        self.plan['business']['domain']='ample.org';self.rejects('domain mismatch')
    def test_stale(self):
        self.plan['sources'][0]['observed_at']='2000-01-01T00:00:00Z';self.rejects('older than')
    def test_path_escape(self):
        self.plan['sources'][0]['file']='../escape.json';self.rejects('escapes')
    def test_insufficient_pilots(self):
        self.plan['queries'][0]['pilot_sources']=['pilot0'];self.rejects('three pilot')
    def test_unresearched_demand(self):
        self.plan['queries'][0]['query']='plumber';self.rejects('demand request')
    def test_pending_is_not_evidence(self):
        p=self.root/'gbp.json';v=json.loads(p.read_text());v['tasks'][0]['status_code']=20100;p.write_text(json.dumps(v));self.plan['sources'][1]['sha256']=digest(p);self.rejects('pending/failed')
    def test_ceiling_before_output_or_collection(self):
        with patch('study.subprocess.run') as call:
            with self.assertRaisesRegex(ValueError,'exceeds ceiling'):run(self.path,self.root/'out',True,.000001)
            call.assert_not_called()
        self.assertFalse((self.root/'out').exists())
    def test_research_preview_does_not_import_or_call_transport(self):
        request=self.root/'request.json';request.write_text(json.dumps(dict(kind='demand',body=[{'keywords':['pizza']}],estimated_cost_usd=.02)))
        result=research(request,self.root/'research');self.assertEqual(result['status'],'estimate_only');self.assertFalse((self.root/'research').exists())
    def test_research_budget_before_http(self):
        request=self.root/'request.json';request.write_text(json.dumps(dict(kind='demand',body=[{}],estimated_cost_usd=.02)))
        with self.assertRaisesRegex(ValueError,'budget exceeded'):research(request,self.root/'research',True,.01)
    def test_ambiguous_request_never_retried(self):
        request=self.root/'request.json';request.write_text(json.dumps(dict(kind='demand',body=[{}],estimated_cost_usd=.02)))
        out=self.root/'research'
        import types
        fake=types.ModuleType('legends_dataforseo')
        def fail(*a,**kw):raise OSError('connection lost')
        fake.api_request=fail
        with patch.dict(sys.modules,legends_dataforseo=fake):
            with self.assertRaises(OSError):research(request,out,True,1)
            with self.assertRaisesRegex(ValueError,'already reserved'):research(request,out,True,1)
        self.assertFalse((out/'.research-lock').exists())

if __name__=='__main__':unittest.main()

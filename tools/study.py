"""Research-backed study workflow. Agent selects; software validates and executes."""
from __future__ import annotations
import argparse
import json
import math
from datetime import datetime, timezone
from pathlib import Path
import subprocess
import shutil
import sys
from study_contract import SCHEMA, digest, validate, require, number

ROOT=Path(__file__).resolve().parent
ROUTES={
 'gbp':'/business_data/google/my_business_info/live',
 'demand':'/dataforseo_labs/google/keyword_overview/live',
 'maps_probe':'/serp/google/maps/live/advanced',
 'organic_probe':'/serp/google/organic/live/advanced',
}

def write_new(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('x',encoding='utf-8') as stream:json.dump(value,stream,indent=2,ensure_ascii=False,allow_nan=False)


def research(request_path,output,execute=False,ceiling=0):
    """One request per invocation; persist reservation before HTTP, never auto-retry."""
    request=json.loads(Path(request_path).read_text(encoding='utf-8-sig'))
    kind=request.get('kind');require(kind in ROUTES,'unknown research kind')
    body=request.get('body');require(isinstance(body,list) and len(body)==1 and isinstance(body[0],dict),'one research task per request')
    estimate=number(request.get('estimated_cost_usd'),0.000001,1,'research estimate')
    output=Path(output); ledger=output/'research-ledger.jsonl'
    import hashlib
    fingerprint=hashlib.sha256(json.dumps([ROUTES[kind],body],sort_keys=True).encode()).hexdigest()
    rows=[json.loads(line) for line in ledger.read_text().splitlines()] if ledger.exists() else []
    require(not any(r.get('request_sha256')==fingerprint for r in rows),'request already reserved; inspect saved result or ambiguous failure, do not resubmit')
    reserved=sum(r['reserved_usd'] for r in rows if r['event']=='reserve')
    overage=sum(max(0,r['actual_usd']-r['reserved_usd']) for r in rows if r['event']=='response')
    receipt={'kind':kind,'endpoint':ROUTES[kind],'estimated_cost_usd':estimate,
             'cumulative_reserved_usd':reserved+overage+estimate,'request_sha256':fingerprint}
    if not execute:return {'status':'estimate_only',**receipt}
    number(ceiling,0.000001,100,'research ceiling')
    require(receipt['cumulative_reserved_usd']<=ceiling,'research budget exceeded')
    output.mkdir(parents=True,exist_ok=True)
    # Exclusive lock prevents concurrent reservations overspending one folder.
    lock=output/'.research-lock'
    try:
        with lock.open('x') as f:f.write(fingerprint)
    except FileExistsError:raise ValueError('research folder busy; inspect lock before recovery') from None
    try:
        current=ledger.read_text() if ledger.exists() else ''
        require([json.loads(line) for line in current.splitlines()]==rows,'research ledger changed; re-estimate')
        stamp=datetime.now(timezone.utc).isoformat()
        with ledger.open('a') as f:f.write(json.dumps({'event':'reserve','reserved_usd':estimate,'observed_at':stamp,**receipt})+'\n')
        from legends_dataforseo import api_request
        response=api_request(ROUTES[kind],body,confirm=True,estimated_cost_usd=estimate,max_cost_usd=ceiling-reserved-overage,consumer='geogrid-study')
        target=output/(fingerprint+'.json');write_new(target,response)
        actual=response.get('cost',0)
        number(actual,0,1000000,'reported provider cost')
        with ledger.open('a') as f:f.write(json.dumps({'event':'response','request_sha256':fingerprint,'reserved_usd':estimate,'actual_usd':actual,'file':target.name})+'\n')
        source={'id':fingerprint[:16],'kind':kind,'file':target.name,'sha256':digest(target),'observed_at':stamp,'url':'https://api.dataforseo.com/v3'+ROUTES[kind]}
        write_new(output/(fingerprint+'.source.json'),source)
        return {'status':'response_saved','source':source,'actual_usd':actual,'provider_status':response.get('status_code'),'task_statuses':[t.get('status_code') for t in response.get('tasks',[])],'usable_completed_response':response.get('status_code')==20000 and bool(response.get('tasks')) and all(t.get('status_code')==20000 for t in response['tasks'])}
    finally:lock.unlink()


def website(url,output):
    """Capture public page text without turning retrieval failures into evidence."""
    import urllib.request
    from urllib.parse import urlparse
    from html.parser import HTMLParser
    parsed=urlparse(url)
    require(parsed.scheme in ('http','https') and parsed.hostname and not parsed.username and not parsed.password,'public HTTP(S) URL required')
    output=Path(output);require(not output.exists(),'website output already exists')
    class PageText(HTMLParser):
        def __init__(self):super().__init__();self.parts=[];self.skip=0
        def handle_starttag(self,tag,attrs):
            if tag in ('script','style','noscript'):self.skip+=1
        def handle_endtag(self,tag):
            if tag in ('script','style','noscript'):self.skip=max(0,self.skip-1)
        def handle_data(self,data):
            if not self.skip and data.strip():self.parts.append(data.strip())
    request=urllib.request.Request(url,headers={'User-Agent':'legends-geogrid research/1.0'})
    with urllib.request.urlopen(request,timeout=30) as response:
        raw=response.read(4000001);require(len(raw)<=4000000,'website exceeds capture limit')
        final_url=response.geturl();encoding=response.headers.get_content_charset() or 'utf-8'
    parser=PageText();parser.feed(raw.decode(encoding,errors='replace'))
    text='\n'.join(parser.parts);require(bool(text.strip()),'website has no readable text; use a browser capture')
    stamp=datetime.now(timezone.utc).isoformat()
    write_new(output,{'url':url,'final_url':final_url,'observed_at':stamp,'text':text})
    return {'id':'website-'+digest(output)[:12],'kind':'website','file':output.name,'url':final_url,'observed_at':stamp,'sha256':digest(output)}


def run(plan_path,output,execute=False,ceiling=0,checkpoint=None):
    plan,receipt=validate(plan_path)
    if not execute:return receipt
    number(ceiling,0.000001,1000000,'grid ceiling')
    require(receipt['estimated_grid_cost_usd']<=ceiling,'grid estimate exceeds ceiling')
    output=Path(output).resolve();output.mkdir(parents=True,exist_ok=False)
    # Preserve a portable evidence snapshot, separate from generated scan outputs.
    archive=output/'evidence';archive.mkdir()
    for source in plan['sources']:
        target=archive/source['file'];target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(Path(plan_path).resolve().parent/source['file'],target)
    write_new(archive/'study-plan.json',plan);write_new(output/'study-receipt.json',receipt)
    validate(archive/'study-plan.json')
    if checkpoint:checkpoint('collection-started')
    b=plan['business'];s=plan['settings'];lanes=[]
    selected=[q for q in plan['queries'] if q['selected']]
    for i,q in enumerate(selected,1):
        _,latest=validate(plan_path)
        require(latest['plan_sha256']==receipt['plan_sha256'],'plan changed during collection')
        lane=output/f'lane-{i}'
        argv=[sys.executable,str(ROOT/'local_heatmap_poc.py'),'--diagnostic','--execute',
              '--confirm-cost-usd',f"{receipt['estimated_grid_cost_usd']/len(selected) + 0.0001:.4f}",
              '--keyword',q['query'],'--target-name',b['name'],'--target-cid',b['cid'],
              '--center-lat',str(b['lat']),'--center-lng',str(b['lng']),
              '--location-label',b['location_label'],'--output-dir',str(lane)]
        for key in ('method','grid_size','radius_km','depth','zoom','device','language_code','se_domain'):
            argv += ['--'+key.replace('_','-'),str(s[key])]
        argv += ['--search-this-area' if s['search_this_area'] else '--no-search-this-area']
        # No retry: preserve partial run and provider task identifiers for inspection.
        try:
            completed=subprocess.run(argv,check=True,stdout=subprocess.PIPE,text=True)
        except subprocess.CalledProcessError:
            if checkpoint:checkpoint('collection-interrupted')
            raise
        emitted=json.loads(completed.stdout)
        parsed=Path(emitted['outputs']['parsed_json']).resolve()
        validate_collected_file(parsed,lane,plan,q)
        write_new(lane/'collector-output.json',emitted)
        if checkpoint:checkpoint('lane-'+str(i)+'-collected')
    return assemble_report(output,output/'report-config.json')


def validate_collected_file(parsed,lane,plan,query):
    require(parsed.is_relative_to(lane.resolve()) and parsed.name=='parsed-grid.json' and parsed.is_file(),'collector output must be an existing parsed grid within its lane')
    data=json.loads(parsed.read_text(encoding='utf-8-sig'))
    require(data.get('keyword')==query['query'] and data.get('target')==plan['business']['name'],'collected business/query mismatch')
    settings=data.get('measurement_settings',{})
    expected=dict(plan['settings'],center_lat=plan['business']['lat'],center_lng=plan['business']['lng'],target_cid=plan['business']['cid'])
    for key in ('method','grid_size','radius_km','depth','zoom','device','language_code','se_domain','search_this_area','center_lat','center_lng','target_cid'):
        require(settings.get(key)==expected[key],'collected settings mismatch: '+key)
    from local_heatmap_poc import generate_grid
    expected_points={(p.lat,p.lng) for p in generate_grid(plan['business']['lat'],plan['business']['lng'],settings['grid_size'],settings['radius_km'])}
    rows=data.get('results',[])
    points={(r['point']['lat'],r['point']['lng']) for r in rows}
    require(len(rows)==len(expected_points) and points==expected_points,'collected grid origins mismatch')


def assemble_report(output,config_path):
    """Read-only collection recovery: never invokes a collector or provider."""
    output=Path(output).resolve();config_path=Path(config_path).resolve()
    require(not config_path.exists(),'report config exists; choose a new recovery filename')
    plan,receipt=validate(output/'evidence/study-plan.json')
    b=plan['business'];s=plan['settings'];lanes=[]
    selected=[q for q in plan['queries'] if q['selected']]
    for i,q in enumerate(selected,1):
        lane=output/f'lane-{i}'
        emitted=lane/'collector-output.json'
        if emitted.is_file():
            parsed=Path(json.loads(emitted.read_text(encoding='utf-8-sig'))['outputs']['parsed_json']).resolve()
        else:
            candidates=list(lane.glob('*/parsed-grid.json'))
            require(len(candidates)==1,'missing or ambiguous collected lane; inspect saved artifacts, do not recollect')
            parsed=candidates[0].resolve()
        validate_collected_file(parsed,lane,plan,q)
        lanes.append({'query_id':f'q{i}','label':q['query'],'query':q['query'],
                      'records_path':str(parsed),
                      'narrative':'Study theme: '+q['theme']['label']+'. Customer need: '+q['theme']['customer_need']+'. Why this search: '+q['reason']+' Limitation: '+q['limitations']})
    config={'schema_version':1,'synthetic':False,'business':{'name':b['name'],'lat':b['lat'],'lng':b['lng'],'location':b['location_label'],'website':b.get('domain')},
            'thesis':'Descriptive visibility baseline for evidenced offerings; ranking patterns alone do not establish causes or commercial returns.',
            'profile_review':receipt['profile_review'],
            'objectives':[s['decision']],'lanes':lanes,'map':{'provider':'auto'},
            'next_actions':['Review recurring competitors at nearby ranks 4-10. Choose one source-backed relevance hypothesis and remeasure unchanged locations after the intervention; do not infer a ranking cause from this snapshot.'],
            'missing_evidence':['Conversion, profitability and causal ranking factors were not measured.']+(['Website unavailable; study offerings are supported by the public GBP only. '+receipt['website_limitation']] if receipt['evidence_mode']=='profile_supported' else []),
            'verification_notes':['Study scope: '+receipt['scope']+'. '+plan['selection']['coverage_summary']+(' Focused scope reason: '+plan['selection']['fewer_themes']['reason'] if receipt['scope']=='focused' else ''), 'Study plan '+receipt['plan_sha256']+'; source lineage validated, semantic judgments remain agent-authored.']}
    write_new(config_path,config)
    from report_model import load_config
    load_config(config_path)
    return {'status':'report_handoff_ready','report_config':str(config_path),'receipt':receipt,'assembly_provider_calls':0}


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='command',required=True)
    sub.add_parser('library-init')
    e=sub.add_parser('enhance');e.add_argument('--run-dir',required=True);e.add_argument('--output-dir',required=True)
    e.add_argument('--execute',action='store_true');e.add_argument('--confirm-cost-usd',type=float,default=0)
    e.add_argument('--max-age-hours',type=float,default=24);e.add_argument('--target-spacing-km',type=float,default=.75)
    bank=sub.add_parser('bank');bank.add_argument('--plan',required=True);bank.add_argument('--run-dir');bank.add_argument('--report-dir');bank.add_argument('--stage',default='saved');bank.add_argument('--parent-study');bank.add_argument('--relationship',choices=('baseline','expansion','monitoring'),default='baseline')
    p=sub.add_parser('proposal');p.add_argument('--plan',required=True);p.add_argument('--output-dir',required=True)
    p.add_argument('--theme',choices=('geogrid','light'),default='geogrid')
    a=sub.add_parser('assemble');a.add_argument('--run-dir',required=True);a.add_argument('--output-config',required=True)
    w=sub.add_parser('website');w.add_argument('--url',required=True);w.add_argument('--output',required=True)
    r=sub.add_parser('research');r.add_argument('--request',required=True);r.add_argument('--output-dir',required=True)
    r.add_argument('--execute',action='store_true');r.add_argument('--confirm-cost-usd',type=float,default=0)
    for name in ('validate','run'):
        s=sub.add_parser(name);s.add_argument('--plan',required=True)
        if name=='run':
            s.add_argument('--output-dir',required=True);s.add_argument('--execute',action='store_true');s.add_argument('--confirm-cost-usd',type=float,default=0)
    for command in sub.choices.values():command.add_argument('--vault-dir',help='Vault root; defaults to GEOGRID_VAULT_DIR or Documents/legends-geogrid-vault')
    args=parser.parse_args(argv)
    try:
        from study_library import bank_study, save_checkpoint
        if args.command=='enhance':
            from study_enhance import run as enhance
            result=enhance(args.run_dir,args.output_dir,args.execute,args.confirm_cost_usd,args.vault_dir,args.max_age_hours,args.target_spacing_km)
        elif args.command=='library-init':
            from study_library import configure
            result=configure(args.vault_dir)
        elif args.command=='bank':
            result=bank_study(args.plan,args.run_dir,args.report_dir,vault=args.vault_dir,stage=args.stage,parent_study=args.parent_study,relationship=args.relationship)
        elif args.command=='proposal':
            from study_proposal import render_proposal
            result=render_proposal(args.plan,args.output_dir,args.theme)
            result['library']=bank_study(args.plan,report_dir=args.output_dir,vault=args.vault_dir,stage='proposal')
        elif args.command=='assemble':
            result=assemble_report(args.run_dir,args.output_config)
            result['library']=bank_study(Path(args.run_dir)/'evidence/study-plan.json',args.run_dir,vault=args.vault_dir,stage='assembled')
        elif args.command=='website':
            result=website(args.url,args.output)
            result['library']=save_checkpoint({'research/'+Path(args.output).name:args.output},vault=args.vault_dir,run_id=Path(args.output).parent.name,stage='website')
        elif args.command=='research':
            result=research(args.request,args.output_dir,args.execute,args.confirm_cost_usd)
            if args.execute:
                directory=Path(args.output_dir);source=result['source']
                result['library']=save_checkpoint({'research/'+source['file']:directory/source['file'],'research/research-ledger.jsonl':directory/'research-ledger.jsonl'},vault=args.vault_dir,run_id=directory.name,stage='research')
        elif args.command=='validate':result=validate(args.plan)[1]
        else:
            checkpoint=lambda stage:bank_study(args.plan,args.output_dir,vault=args.vault_dir,stage=stage)
            result=run(args.plan,args.output_dir,args.execute,args.confirm_cost_usd,checkpoint)
            if args.execute:result['library']=checkpoint('assembled')
        print(json.dumps(result,indent=2));return 0
    except (ValueError,OSError,subprocess.CalledProcessError) as exc:
        print('Study stopped: '+str(exc),file=sys.stderr);return 2

if __name__=='__main__':raise SystemExit(main())

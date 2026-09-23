"""Plan and execute an incremental, banked study refinement; no implicit spending."""
import argparse
from dataclasses import asdict
from datetime import datetime, timezone
from html import escape
import json
import math
from pathlib import Path
import shutil

import local_heatmap_poc as collector
from report_model import load_config, runner_records, require
from sampling_review import review
from study_contract import digest, validate


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def write(path, value):
    with Path(path).open('x', encoding='utf-8') as stream:
        json.dump(value, stream, indent=2)


def key(row):
    return round(row['lat'], 7), round(row['lng'], 7)


def parsed_row(result):
    row=asdict(result)
    row['observed_ranks']=list(result.observed_ranks)
    return row


def fresh(row, now, hours):
    if row['state'] not in ('found', 'not_returned') or not row.get('sampled_at'):
        return False
    if row['state']=='not_returned':
        depth=row.get('requested_depth')
        if type(depth) is not int or depth<=0 or not set(range(1,depth+1)).issubset(row.get('observed_ranks',[])):
            return False
    try:
        stamp = datetime.fromisoformat(row['sampled_at'].replace('Z', '+00:00'))
        return stamp.tzinfo is not None and 0 <= (now-stamp).total_seconds() <= hours*3600
    except ValueError:
        return False


def arguments(plan, query):
    b, s = plan['business'], plan['settings']
    # Live makes point-level persistence possible; search controls stay unchanged.
    args = collector.parse_args(['--keyword', query, '--target-name', b['name'],
        '--target-cid', b['cid'], '--center-lat', str(b['lat']), '--center-lng', str(b['lng'])])
    for name in ('depth','zoom','device','language_code','se_domain','search_this_area'):
        setattr(args, name, s[name])
    args.method = 'live'
    return args


def normalized_response(response, point, plan, lane):
    args = arguments(plan, lane['query'])
    rows = []
    for result in collector.parse_results(response, [point], args):
        row = parsed_row(result)
        row['source'] = 'DataForSEO Maps Live; saved enhancement response'
        rows.append(row)
    return runner_records({'results':rows,'measurement_settings':collector.measurement_settings(args)}, lane, plan['business'])[0]


def baseline(run):
    """Bind a study to its saved evidence, never accept arbitrary report prose."""
    from study import validate_collected_file
    run = Path(run).resolve()
    plan_path = run/'evidence/study-plan.json'
    plan, _ = validate(plan_path)
    cfg_path = run/'report-config.json'
    cfg = read(cfg_path)
    require(cfg['business']['name']==plan['business']['name'] and
            cfg['business']['lat']==plan['business']['lat'] and cfg['business']['lng']==plan['business']['lng'],
            'baseline business identity mismatch')
    files = {str(plan_path):digest(plan_path), str(cfg_path):digest(cfg_path)}
    for src in plan['sources']:
        p = plan_path.parent/src['file']; files[str(p)] = digest(p)
    selected = [q for q in plan['queries'] if q['selected']]
    require(len(cfg['lanes']) == len(selected), 'baseline lane selection mismatch')
    prior = run/'enhancement-complete.json'
    if prior.exists():
        receipt = read(prior)
        for name, expected in receipt['sha256'].items():
            p = (run/name).resolve()
            require(p.is_relative_to(run) and p.is_file() and digest(p)==expected, 'enhancement evidence integrity mismatch')
            files[str(p)] = expected
    for index, (lane, query) in enumerate(zip(cfg['lanes'], selected), 1):
        require(lane['query'] == query['query'], 'baseline query mismatch')
        p = Path(lane['records_path'])
        p = p if p.is_absolute() else run/p
        if not p.exists() and not prior.exists():
            recovered=list((run/f'lane-{index}').glob('*/parsed-grid.json'))
            require(len(recovered)==1,'missing or ambiguous baseline collector output')
            p=recovered[0]
        require(p.resolve().is_relative_to(run), 'baseline observations must be inside the run')
        files[str(p.resolve())] = digest(p)
        if not prior.exists():
            validate_collected_file(p.resolve(), run/f'lane-{index}', plan, query)
            payload = read(p)
            raw_path = p.parent/'dataforseo-response.raw.json'
            raw = read(raw_path); files[str(raw_path.resolve())] = digest(raw_path)
            args = arguments(plan, query['query'])
            points = [collector.GridPoint(**r['point']) for r in payload['results']]
            requests=read(p.parent/'dataforseo-request-tasks.json')
            files[str((p.parent/'dataforseo-request-tasks.json').resolve())]=digest(p.parent/'dataforseo-request-tasks.json')
            expected=collector.build_tasks(args,points)
            require(len(requests)==len(expected),'baseline request count mismatch')
            for actual,wanted in zip(requests,expected):
                for k in ('keyword','location_coordinate','depth','zoom','language_code','device','search_places','search_this_area','se_domain'):
                    require(actual.get(k)==wanted.get(k),'baseline request settings mismatch: '+k)
            require(len(raw.get('tasks',[]))==len(requests),'baseline provider task count mismatch')
            by_tag={t['tag']:t for t in requests}
            seen=set()
            for task in raw['tasks']:
                data=task.get('data') or {}; tag=data.get('tag') or task.get('tag')
                require(tag in by_tag and tag not in seen,'baseline provider task identity mismatch')
                seen.add(tag)
                for k in ('keyword','location_coordinate','depth','language_code','device','search_places','search_this_area','se_domain'):
                    require(data.get(k)==by_tag[tag].get(k),'baseline provider settings mismatch: '+k)
            parsed = collector.parse_results(raw, points, args)
            require(len(parsed)==len(points), 'baseline raw response mismatch')
            # Normalize from the retained provider response, including its dates.
            lane['records'] = runner_records({'results':[parsed_row(r) for r in parsed],
                'measurement_settings':payload['measurement_settings']}, lane, plan['business'])
        else:
            lane['records'] = read(p)
        lane.pop('records_path')
    # Validate/compute metrics using the same report contract, without writing.
    # load_config accepts a path, so normalize from a private temporary config.
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp)/'config.json'; write(p, cfg)
        model = load_config(p)
    return plan, cfg, model, files


def plan_enhancement(run, now=None, max_age_hours=24, target_spacing_km=.75):
    now = now or datetime.now(timezone.utc)
    require(math.isfinite(max_age_hours) and 0 < max_age_hours <= 168, 'reuse age must be within 1-168 hours')
    plan, cfg, model, files = baseline(run)
    audit = review(model, target_spacing_km)
    grids = [{key(r) for r in lane['records']} for lane in model['lanes']]
    require(all(g == grids[0] for g in grids), 'enhance requires shared origins across themes')
    coords = grids[0]; ys = sorted({p[0] for p in coords}); xs = sorted({p[1] for p in coords})
    require(len(coords)==len(xs)*len(ys) and len(xs)==len(ys) and len(xs)>1, 'enhance requires a complete square origin grid')
    for axis in (xs,ys):
        steps=[b-a for a,b in zip(axis,axis[1:])]
        require(max(steps)-min(steps)<1e-6, 'irregular spacing needs an explicit geographic plan')
    densify = any((x.get('max_neighbor_spacing_km',0)>target_spacing_km*1.05 or x.get('sharp_rank_transitions',0))
                  and any(r['state']=='found' for r in lane['records'])
                  for x,lane in zip(audit['lanes'],model['lanes']))
    # One nested doubling, then reassess. Never chase a rank boundary endlessly.
    if densify:
        require(2*len(xs)-1 <= 25, 'next refinement exceeds 25x25; plan a targeted study instead')
        require(min(x['max_neighbor_spacing_km'] for x in audit['lanes'])>.10, 'already at fine resolution; review locally rather than auto-densify')
        subdivide=lambda axis: sorted(set(axis)|{round((a+b)/2,7) for a,b in zip(axis,axis[1:])})
        xs,ys=subdivide(xs),subdivide(ys)
    targets=[{'lat':y,'lng':x} for y in ys for x in xs]
    lanes=[]
    for lane in model['lanes']:
        old={key(r):r for r in lane['records']}
        reusable={p:r for p,r in old.items() if fresh(r,now,max_age_hours)}
        missing=[p for p in targets if key(p) not in reusable]
        lanes.append({'query_id':lane['query_id'],'query':lane['query'],
            'recommendation':next(x for x in audit['lanes'] if x['query']==lane['query']),
            'reused':list(reusable.values()),'collect':missing,
            'new_locations':sum(key(p) not in old for p in missing),
            'refresh_locations':sum(key(p) in old for p in missing)})
    count=sum(len(l['collect']) for l in lanes)
    return {'schema':'geogrid-enhance/v1','created_at':now.isoformat(), 'source_run':str(Path(run).resolve()),
        'plan':plan,'config':cfg,'source_sha256':files,'review':audit,'lanes':lanes,
        'grid_size':len(xs),'previous_grid_size':int(math.sqrt(len(coords))),
        'max_age_hours':max_age_hours,'new_calls':count,'reused_observations':sum(len(l['reused']) for l in lanes),
        'estimated_incremental_usd':collector.estimate_scan_cost(count,plan['settings']['depth'],'live'),
        'method':'live','status':'ready' if count else 'no_additional_measurement_recommended',
        'scope':'Same-extent resolution refinement and refresh of stale/missing evidence. Extending territory requires separate relevance evidence.',
        'cost_policy':'Incremental ranking data only. Advisory estimate, not provider billing enforcement. Baseline costs are not charged again.'}


def preview(manifest, output):
    from report_design import html_styles
    m=manifest
    rows=''.join('<tr><td>'+escape(l['query'])+'</td><td>'+str(len(l['reused']))+'</td><td>'+str(l['new_locations'])+'</td><td>'+str(l['refresh_locations'])+'</td></tr>' for l in m['lanes'])
    html='<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>Enhance this study</title><style>'+html_styles()+'</style><main><h1>enhance this study</h1><p>'+escape(m['plan']['business']['name'])+'</p><h2>'+str(m['previous_grid_size'])+' × '+str(m['previous_grid_size'])+' → '+str(m['grid_size'])+' × '+str(m['grid_size'])+'</h2><p>'+escape(m['scope'])+'</p><table><tr><th>search keyword</th><th>reuse</th><th>new points</th><th>refresh</th></tr>'+rows+'</table><h2>Estimated additional data: $'+format(m['estimated_incremental_usd'],'.4f')+'</h2><p>'+escape(m['cost_policy'])+'</p><p>Reuse window: '+str(m['max_age_hours'])+' hours. Unknown timestamps are not fresh evidence. This is a plan, not new findings.</p><p>Say “enhance” to your agent to proceed within your approved budget. This saved HTML does not itself execute paid requests.</p></main></html>'
    decisions='<section><h2>why enhance these searches?</h2>'
    for lane in m['lanes']:
        rec=lane['recommendation']
        decisions+='<article class="query-ticket"><span class="query-token">'+escape(lane['query'])+'</span><p>'+escape(rec['boundary']['reason'])+'</p>'
        decisions+=''.join('<p>'+escape(direction)+': '+escape(data['reason'])+'</p>' for direction,data in rec['directions'].items())
        if m['grid_size']>m['previous_grid_size']:
            decisions+='<p>Interior detail uses shared locations across themes for comparison. This does not extend the measured territory. An NR perimeter can still surround useful interior visibility.</p>'
        decisions+='</article>'
    decisions+='<h2>the maps considered together</h2><p>'+escape(m['review']['collective_coverage']['policy'])+'</p>'
    for direction,pitch in m['review']['collective_coverage']['directions'].items():
        decisions+='<p>'+escape(direction)+': '+escape(pitch['explanation'])+' '+escape(pitch['execution'])+'</p>'
    html=html.replace('</main>',decisions+'</section></main>')
    (output/'enhance.html').write_text(html,encoding='utf-8')


def run(run_dir, output, execute=False, ceiling=0, vault=None, max_age_hours=24, target_spacing_km=.75):
    from study_library import bank_study
    output=Path(output).resolve(); source=Path(run_dir).resolve()
    require(not output.is_relative_to(source), 'enhancement must be a sibling run, not inside its baseline')
    if not output.exists():
        manifest=plan_enhancement(source,max_age_hours=max_age_hours,target_spacing_km=target_spacing_km)
        output.mkdir(parents=True)
        shutil.copytree(source/'evidence',output/'evidence')
        parent=bank_study(source/'evidence/study-plan.json',source,vault=vault,stage='enhancement-baseline')
        manifest['parent_study']=parent['study_id']
        write(output/'enhancement-plan.json',manifest)
        (output/'enhancement-plan.sha256').write_text(digest(output/'enhancement-plan.json'))
        preview(manifest,output)
        bank_study(output/'evidence/study-plan.json',output,vault=vault,stage='enhancement-proposed',parent_study=parent['study_id'],relationship='expansion')
    require(digest(output/'enhancement-plan.json')==(output/'enhancement-plan.sha256').read_text().strip(),'enhancement plan changed; create a new plan')
    manifest=read(output/'enhancement-plan.json')
    require(manifest['source_run']==str(source),'enhancement belongs to another baseline')
    receipt={k:manifest[k] for k in ('status','new_calls','reused_observations','estimated_incremental_usd','grid_size','scope')}
    receipt['preview']=str(output/'enhance.html')
    if not execute or not manifest['new_calls']:return receipt
    require(math.isfinite(ceiling) and ceiling>0 and manifest['estimated_incremental_usd']<=ceiling,'additional estimate exceeds approved ceiling')
    lock=output/'.enhance-lock'
    with lock.open('x') as f:f.write('Never retry an ambiguous paid request.')
    try:
        return execute_manifest(manifest, output, ceiling, vault)
    finally:
        lock.unlink()


def execute_manifest(m, output, ceiling, vault):
    from study_library import bank_study
    from strategy_report import build
    saved_plan,_=validate(output/'evidence/study-plan.json')
    require(saved_plan==m['plan'],'enhancement research plan mismatch')
    for name, expected in m['source_sha256'].items():
        require(Path(name).is_file() and digest(Path(name))==expected,'baseline changed; create a new enhancement plan')
    now=datetime.now(timezone.utc)
    require(all(fresh(r,now,m['max_age_hours']) for l in m['lanes'] for r in l['reused']), 'reuse window expired; create a new enhancement plan')
    ledger=output/'enhancement-ledger.jsonl'
    events=[json.loads(line) for line in ledger.read_text().splitlines()] if ledger.exists() else []
    def event(row):
        with ledger.open('a',encoding='utf-8') as f:f.write(json.dumps(row)+'\n')
        events.append(row)
    def bank(stage, report=None):
        return bank_study(output/'evidence/study-plan.json',output,report,vault=vault,stage=stage,parent_study=m['parent_study'],relationship='expansion')
    cfg=json.loads(json.dumps(m['config']))
    # Never carry baseline rank narratives or conclusions into the new edition.
    cfg.pop('decision_brief',None);cfg.pop('verification_notes',None)
    cfg['next_actions']=[]
    cfg['thesis']='Enhanced same-extent measurements; review the new results before prescribing an action.'
    cfg.setdefault('missing_evidence',[]).append('This edition combines eligible saved observations and new observations. It is spatial refinement, not a before/after ranking-change experiment. Business research remains dated; recommendations require agent review.')
    cfg['lanes']=[]
    unit=collector.estimate_scan_cost(1,m['plan']['settings']['depth'],'live')
    try:
        for li,lane in enumerate(m['lanes']):
            rows=list(lane['reused'])
            for pi,origin in enumerate(lane['collect']):
                ident=f'{li:02d}-{pi:04d}'
                point=collector.GridPoint(0,pi,origin['lat'],origin['lng'],'enhance-'+ident)
                folder=output/'acquisition'/ident;folder.mkdir(parents=True,exist_ok=True)
                response_path=folder/'dataforseo-response.raw.json'
                reserved=next((e for e in events if e['id']==ident and e['event']=='reserve'),None)
                completed=next((e for e in events if e['id']==ident and e['event']=='response'),None)
                if reserved:
                    require(completed is not None and response_path.exists(),'ambiguous or interrupted request '+ident+'; inspect saved response/task ID, never resubmit automatically')
                    require(digest(response_path)==completed['sha256'],'saved response integrity mismatch')
                    response=read(response_path)
                else:
                    spent=sum(e['estimate'] for e in events if e['event']=='reserve')
                    spent+=sum(max(0,e['cost']-unit) for e in events if e['event']=='response')
                    require(spent+unit<=ceiling+1e-9,'cumulative enhancement budget exhausted')
                    args=arguments(m['plan'],lane['query']); task=collector.build_tasks(args,[point])[0]
                    write(folder/'dataforseo-request-tasks.json',[task])
                    event({'id':ident,'event':'reserve','estimate':unit,'at':datetime.now(timezone.utc).isoformat()})
                    response=collector.call_dataforseo_live_task(task,args.timeout)
                    write(response_path,response)
                    cost=response.get('cost')
                    require(type(cost) in (int,float) and math.isfinite(cost) and cost>=0,'unknown provider cost; inspect response before continuing')
                    event({'id':ident,'event':'response','cost':cost,'sha256':digest(response_path)})
                require(response.get('status_code')==20000,'provider envelope failed; inspect saved response')
                tasks=response.get('tasks') or []
                require(len(tasks)==1,'enhancement expected one provider task')
                actual=tasks[0].get('data') or {}
                wanted=collector.build_tasks(arguments(m['plan'],lane['query']),[point])[0]
                for field in ('keyword','location_coordinate','depth','language_code','device','search_places','search_this_area','se_domain'):
                    require(actual.get(field)==wanted.get(field),'enhancement provider settings mismatch: '+field)
                row=normalized_response(response,point,m['plan'],lane)
                require(row['state'] in ('found','not_returned','empty'),'incomplete provider task; inspect saved response without resubmission')
                row['source']='enhancement response '+ident+' sha256:'+digest(response_path)
                rows.append(row)
            rows.sort(key=key)
            record_path=output/f'lane-{li+1}'/'enhanced-records.json';record_path.parent.mkdir(exist_ok=True)
            if record_path.exists():require(read(record_path)==rows,'existing enhanced records mismatch')
            else:write(record_path,rows)
            cfg['lanes'].append({'query_id':lane['query_id'],'query':lane['query'],'label':lane['query'],'records_path':str(record_path),'map':{'provider':'auto'}})
            bank('enhancement-lane-'+str(li+1))
        config=output/'report-config.json'
        cfg['map']={'provider':'auto'}
        total=sum(e['cost'] for e in events if e['event']=='response')
        cfg['verification_notes']=[f"Enhancement reused {m['reused_observations']} observations under a {m['max_age_hours']}-hour reuse policy and collected {m['new_calls']} additional observations. Provider-reported incremental cost: ${total:.6f}. Baseline cost is separate. Original baseline preserved.",
            'Collection used Maps Live with the original query, CID, language, device, depth, zoom and search-area controls. Dates remain attached to individual observations. Reused evidence and fresh evidence are not a synchronized monitoring comparison.']
        if config.exists():require(read(config)==cfg,'enhanced report config changed')
        else:write(config,cfg)
        report=output/'report'
        if not (report/'report-qa.json').exists():build(config,report,True,True)
        require(read(report/'report-qa.json').get('status')=='passed' and
                (report/'report.html').is_file() and (report/'report.pdf').is_file(),
                'enhanced report is incomplete or has not passed QA')
        done=output/'enhancement-complete.json'
        if not done.exists():
            files=[config,ledger,output/'enhancement-plan.json']+list((output/'acquisition').rglob('*.json'))+list(output.glob('lane-*/enhanced-records.json'))
            write(done,{'actual_incremental_usd':total,'reused_observations':m['reused_observations'],
                        'sha256':{p.relative_to(output).as_posix():digest(p) for p in files}})
        result=bank('enhancement-report-complete',report)
        return {'status':'enhanced','actual_incremental_usd':total,'report_html':str(report/'report.html'),'report_pdf':str(report/'report.pdf'),'library':result}
    except Exception:
        bank('enhancement-interrupted')
        raise


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run-dir',required=True);p.add_argument('--output-dir',required=True)
    p.add_argument('--execute',action='store_true');p.add_argument('--confirm-cost-usd',type=float,default=0)
    p.add_argument('--vault-dir');p.add_argument('--max-age-hours',type=float,default=24)
    p.add_argument('--target-spacing-km',type=float,default=.75)
    a=p.parse_args()
    print(json.dumps(run(a.run_dir,a.output_dir,a.execute,a.confirm_cost_usd,a.vault_dir,a.max_age_hours,a.target_spacing_km),indent=2))


if __name__=='__main__':main()

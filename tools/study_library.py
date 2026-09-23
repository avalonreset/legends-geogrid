"""Local immutable study bank, readable by Obsidian and ordinary Markdown tools."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
from datetime import datetime, timezone
from urllib.parse import quote


def sha(data):return hashlib.sha256(data).hexdigest()
def config_path():return Path.home()/'.config'/'legends-geogrid'/'library.json'
def root_path(value=None):
    configured=json.loads(config_path().read_text()).get('vault') if not value and not os.environ.get('GEOGRID_VAULT_DIR') and config_path().is_file() else None
    return Path(value or os.environ.get('GEOGRID_VAULT_DIR') or configured or Path.home()/'Documents'/'legends-geogrid-vault').expanduser().resolve()/'GeoGrid'
def configure(vault):
    if not vault:raise ValueError('--vault-dir required to configure library')
    path=Path(vault).expanduser().resolve();path.mkdir(parents=True,exist_ok=True)
    config=config_path();config.parent.mkdir(parents=True,exist_ok=True)
    with config.open('x',encoding='utf-8') as f:json.dump({'vault':str(path)},f)
    return {'status':'library_configured','vault':str(path),'config':str(config)}
def text(value):return str(value).replace('\n',' ').replace('[[','(').replace(']]',')').replace('<','&lt;').replace('>','&gt;')
def link(path):return quote(path.replace('\\','/'),safe='/.-')


def refresh_catalog(root):
    target=root/'catalog.md';stamp=root/'catalog.sha256'
    if target.exists() and (not stamp.exists() or sha(target.read_bytes())!=stamp.read_text().strip()):
        return 'catalog was edited; preserved, use business folders/backlinks'
    lines=['# study catalog','','Generated navigation; write personal notes in the business dossiers.','']
    for manifest in sorted((root/'businesses').glob('*/studies/*/*/manifest.json')):
        data=json.loads(manifest.read_text());note=manifest.parent/'study.md'
        lines+=['- '+('SUPERSEDED / REVIEW REQUIRED: ' if (manifest.parent/'REVIEW.md').exists() else '')+'['+text(data['run_id'])+' / '+text(data['stage'])+']('+link(note.relative_to(root).as_posix())+') - '+data['observed_at']]
    content='\n'.join(lines).encode('utf-8')
    temporary=root/'catalog.pending';temporary.write_bytes(content);os.replace(temporary,target)
    stamp.write_text(sha(content))
    return 'updated'


def save_checkpoint(files, *, vault=None, plan=None, run_id='research', stage='research', parent_study=None, relationship='baseline'):
    if relationship not in ('baseline','expansion','monitoring'):raise ValueError('unknown study relationship')
    if relationship!='baseline' and not parent_study:raise ValueError('expansion/monitoring requires parent study id')
    # Explicit file inventory only. Never sweep a user folder, env file or credential config.
    contents={}
    for name,source in files.items():
        rel=Path(name)
        if rel.is_absolute() or '..' in rel.parts or ':' in name or not rel.parts:raise ValueError('invalid archive path')
        src=Path(source)
        if src.is_symlink() or not src.is_file():raise ValueError('missing or linked artifact')
        if src.name.startswith('.env') or src.suffix.lower() not in ('.json','.jsonl','.md','.html','.pdf','.png','.csv','.ttf'):raise ValueError('unsupported artifact')
        contents[rel.as_posix()]=src.read_bytes()
    business=(plan or {}).get('business',{})
    bid=sha(str(business.get('cid','unassigned')).encode())[:20]
    sid=sha(json.dumps([bid,run_id],sort_keys=True).encode())[:24]
    identity=dict(business_id=bid,study_id=sid,stage=stage,run_id=run_id,parent_study=parent_study,relationship=relationship)
    hashes={name:sha(data) for name,data in sorted(contents.items())}
    revision=sha(json.dumps([identity,hashes],sort_keys=True).encode())[:24]
    root=root_path(vault);root.mkdir(parents=True,exist_ok=True)
    lock=root/'.bank.lock'
    try:fd=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
    except FileExistsError:raise ValueError('study bank busy; retry the local bank command only') from None
    os.close(fd)
    try:
        if parent_study:
            if len(parent_study)!=24 or any(c not in '0123456789abcdef' for c in parent_study):raise ValueError('invalid parent study id')
            if not (root/'businesses'/bid/'studies'/parent_study).is_dir():raise ValueError('parent study must exist for the same business')
        directory=root/'businesses'/bid/'studies'/sid;target=directory/revision
        receipt=dict(schema='geogrid-library/v1',**identity,revision=revision,sha256=hashes,observed_at=datetime.now(timezone.utc).isoformat(),provider_calls=0)
        if target.exists():
            previous=json.loads((target/'manifest.json').read_text())
            if previous['sha256']!=hashes or any(sha((target/'artifacts'/n).read_bytes())!=h for n,h in hashes.items()):raise ValueError('bank integrity mismatch; existing snapshot preserved')
            return dict(status='already_banked',study_id=sid,revision=revision,note=str(target/'study.md'),catalog=refresh_catalog(root))
        directory.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(dir=directory,prefix='.staging-') as tmp:
            staging=Path(tmp)
            for name,data in contents.items():
                dest=staging/'artifacts'/name;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(data)
            lines=['---','type: geogrid-study','study_id: '+sid,'stage: '+stage,'relationship: '+relationship,'---','', '# '+text(business.get('name','Unassigned research')), '', '[Business dossier](../../../business.md)', '', 'Stage: '+text(stage)+'. This is a saved checkpoint, not certification of completeness.','']
            if parent_study:
                parents=list((root/'businesses'/bid/'studies'/parent_study).glob('*/manifest.json'))
                latest=max(parents,key=lambda p:json.loads(p.read_text())['observed_at'])
                lines+=['[Parent study](../../'+parent_study+'/'+latest.parent.name+'/study.md) ('+relationship+').','']
            if plan:
                lines+=['## Identity and scope','',text(business.get('location_label','')),text(plan.get('identity',{}).get('reconciliation','')),text(plan.get('website_limitation','')),'','## Study decision','',text(plan.get('settings',{}).get('decision','')),'','## Selected searches','']
                lines += ['- '+text(q['query'])+': '+text(q.get('reason','')) for q in plan.get('queries',[]) if q.get('selected')]
            if 'report/report-model.json' in contents:
                model=json.loads(contents['report/report-model.json']);lines+=['','## Recorded findings','']
                for lane in model.get('lanes',[]):
                    m=lane['metrics'];lines+=['- '+text(lane['query'])+f": top 3 {m['top3']} of {m['measured']} measured origins; {m['sampled']} sampled."]
                lines+=['','## Proposed actions (not established outcomes)','']+[ '- '+text(x) for x in model.get('next_actions',[])]
                for action in model.get('decision_brief',{}).get('actions',[]):
                    lines += ['', '### '+text(action['title']), '', 'Proposed, not executed.']
                    lines += [text(key)+': '+text(action[key]) for key in ('why','next_step','owner','success_check','uncertainty')]
                    lines += ['Evidence: '+', '.join(text(x['pointer']) for x in action['evidence'])]
                lines+=['','## Unresolved evidence','']+['- '+text(x) for x in model.get('missing_evidence',[])]
            lines+=['','## Evidence and cost receipts','','Costs remain in their original receipts; checkpoints must not be summed as separate purchases.','']
            lines += ['- ['+text(name)+'](artifacts/'+link(name)+')' for name in hashes]
            (staging/'study.md').write_text('\n'.join(lines),encoding='utf-8')
            (staging/'manifest.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8')
            staging.rename(target)
        dossier=root/'businesses'/bid/'business.md'
        if not dossier.exists():
            dossier.write_text('# '+text(business.get('name','Unassigned research'))+'\n\nCID: '+text(business.get('cid','unassigned'))+'\n\nStudy checkpoints link here. Use Obsidian backlinks or [the study folders](studies/) to browse history. Identity assertions remain dated in each checkpoint; unresolved conflicts are not silently reconciled.\n',encoding='utf-8')
        index=root/'README.md'
        if not index.exists():index.write_text('# legends-geogrid study library\n\nOpen this folder in Obsidian, or include it inside an existing vault. Browse [the study catalog](catalog.md). Business dossiers live in `businesses/`; checkpoints link back to them. Records are local and private by default. No automatic syncing, provider requests or credential files.\n',encoding='utf-8')
        return dict(status='banked',study_id=sid,revision=revision,note=str(target/'study.md'),artifacts=len(hashes),catalog=refresh_catalog(root))
    finally:lock.unlink()


def bank_study(plan_path, run_dir=None, report_dir=None, *, vault=None, stage='saved', parent_study=None, relationship='baseline'):
    plan_path=Path(plan_path).resolve();plan=json.loads(plan_path.read_text(encoding='utf-8-sig'))
    files={'research/study-plan.json':plan_path}
    for src in plan.get('sources',[]):
        path=(plan_path.parent/src['file']).resolve()
        if not path.is_relative_to(plan_path.parent) or not path.is_file() or sha(path.read_bytes())!=src['sha256']:raise ValueError('source outside study or evidence hash mismatch')
        files['research/'+src['file']]=path
    run=Path(run_dir).resolve() if run_dir else None
    if run and run.is_dir():
        allowed={'dataforseo-response.raw.json','parsed-grid.json','dataforseo-request-tasks.json','collector-output.json','study-receipt.json','research-ledger.jsonl','cost-audit.json','sampling-review.json','report-config.json','observations.csv','analysis-summary.json','final-findings.md','acceptance-receipt.json'}
        for p in run.rglob('*'):
            enhancement_files={'enhancement-plan.json','enhancement-ledger.jsonl','enhancement-complete.json','enhanced-records.json','enhance.html'}
            if p.is_file() and p.name in allowed | enhancement_files:
                if not p.resolve().is_relative_to(run):raise ValueError('run artifact escapes folder')
                files['collection/'+p.relative_to(run).as_posix()]=p
    if report_dir:
        report=Path(report_dir).resolve()
        for p in report.iterdir():
            if p.is_file() and (p.name in {'report-model.json','report-qa.json','report.html','report.pdf','proposal.html','proposal.pdf','proposal-receipt.json','sampling-review.json','banner.png','legends-regular.ttf'} or p.name.startswith('map-') and p.suffix=='.png'):
                files['report/'+p.name]=p
    return save_checkpoint(files,vault=vault,plan=plan,run_id=run.name if run else sha(plan_path.read_bytes())[:16],stage=stage,parent_study=parent_study,relationship=relationship)

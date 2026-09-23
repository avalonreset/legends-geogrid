"""Required profile context derived from a lineage-validated study, without calls."""
import json


FIELDS = {'title': 'Listing name', 'category': 'Reported category',
          'address': 'Listed address', 'phone': 'Listed phone', 'url': 'Website',
          'additional_categories': 'Additional categories', 'rating': 'Review summary',
          'work_time': 'Opening hours', 'local_business_links': 'Customer links'}


def build(plan, item, source):
    base = plan['identity']['pointer']
    facts = []
    for key, label in FIELDS.items():
        value = item.get(key)
        known = value is not None and value != '' and value != [] and value != {}
        facts.append(dict(field=key, label=label, status='observed' if known else 'unknown',
                          value=value if known else None,
                          evidence=dict(source_id=source['id'], source_sha256=source['sha256'],
                                        pointer=base+'/'+key, observed_at=source['observed_at'],
                                        url=source['url']) if known else None))
    themes = [dict(query=q['query'], customer_need=q['theme']['customer_need'],
                   why=q['reason'], distinct_value=q['theme']['distinct_value'],
                   limitations=q['limitations'], evidence=q['offering_evidence'])
              for q in plan['queries'] if q['selected']]
    return dict(schema='geogrid-profile-review/v1', cid=plan['business']['cid'],
                profile_url='https://www.google.com/maps?cid='+plan['business']['cid'],
                observed_at=source['observed_at'], facts=facts, themes=themes,
                identity_assessment=plan['identity']['reconciliation'],
                website_assessment=plan.get('website_limitation') or
                    'Website evidence was retained in the study. This does not certify every customer link or transaction.',
                access='Public provider observations; no private owner performance data.',
                limitation='Profile fields are observations, not a profile quality score or an explanation of ranking. Missing fields are unknown. Opening hours, offerings and linked destinations may need owner confirmation.')


def validate(raw):
    if not isinstance(raw, dict) or raw.get('schema') != 'geogrid-profile-review/v1':
        raise ValueError('invalid profile review')
    from decision_brief import website_url
    for key in ('cid', 'observed_at', 'identity_assessment', 'website_assessment', 'access', 'limitation'):
        if not isinstance(raw.get(key), str) or not raw[key].strip():
            raise ValueError('profile review requires '+key)
    website_url(raw.get('profile_url'))
    facts=raw.get('facts')
    if not isinstance(facts,list) or {f.get('field') for f in facts if isinstance(f,dict)} != set(FIELDS) or len(facts)!=len(FIELDS):
        raise ValueError('profile review requires every field with observed or unknown status')
    for fact in facts:
        if fact.get('status') not in ('observed','unknown') or fact.get('label') != FIELDS[fact['field']]:
            raise ValueError('invalid profile field')
        if fact['status']=='unknown':
            if fact.get('value') is not None or fact.get('evidence') is not None:
                raise ValueError('unknown profile field cannot claim evidence')
        else:
            ref=fact.get('evidence')
            if not isinstance(ref,dict):
                raise ValueError('observed profile field needs provenance')
            if fact.get('value') is None or not all(isinstance(ref.get(k),str) and ref[k] for k in ('source_id','source_sha256','pointer','observed_at','url')):
                raise ValueError('observed profile field needs provenance')
    if not isinstance(raw.get('themes'),list) or not raw['themes']:
        raise ValueError('profile review requires search themes')
    for theme in raw['themes']:
        for key in ('query','customer_need','why','distinct_value','limitations'):
            if not isinstance(theme.get(key),str) or not theme[key].strip():
                raise ValueError('profile theme requires '+key)
        if not theme.get('evidence'):
            raise ValueError('profile theme requires offering evidence')
    # Deep copy preserves the source snapshot rather than sharing mutable caller data.
    return json.loads(json.dumps(raw,allow_nan=False))


def readable(fact):
    if fact['status']=='unknown':
        return 'Not available in the retained response; not established as missing from the profile.'
    value=fact['value']
    if fact['field']=='rating' and isinstance(value,dict):
        return f"Recorded rating: {value.get('value', 'unknown')}; review count: {value.get('votes_count', 'unknown')}. Not a review recency or sentiment analysis."
    if fact['field']=='work_time':
        return 'Opening-hours data was returned. Exact schedule is retained in the evidence; current service availability has not been confirmed.'
    if fact['field']=='local_business_links' and isinstance(value,list):
        return '; '.join(str(x.get('type','link'))+': '+str(x.get('url','unknown destination')) for x in value if isinstance(x,dict))
    return value if isinstance(value,str) else json.dumps(value,ensure_ascii=False)

"""Offline sampling adequacy heuristics, not statistical confidence or paid execution."""
import argparse
import json
import math
from pathlib import Path


def km(a,b):
    lat1,lat2=map(math.radians,(a[0],b[0]))
    dlat=lat2-lat1;dlng=math.radians(b[1]-a[1])
    return 6371*2*math.asin(min(1,math.sqrt(math.sin(dlat/2)**2+math.cos(lat1)*math.cos(lat2)*math.sin(dlng/2)**2)))


def boundary_review(rows):
    """Direction-level evidence, not permission to buy a larger square."""
    def kind(r):
        rank=r.get('rank')
        if r.get('state')=='found' and type(rank) in (int,float) and math.isfinite(rank) and rank>0:
            return 'green' if rank<=3 else 'yellow' if rank<=10 else 'red'
        depth=r.get('requested_depth')
        if (r.get('state')=='not_returned' and type(depth) is int and depth>0
                and set(range(1,depth+1)).issubset(r.get('observed_ranks',[]))):
            return 'confirmed_nr'
        return 'unknown'
    counts={k:sum(kind(r)==k for r in rows) for k in ('green','yellow','red','confirmed_nr','unknown')}
    if counts['confirmed_nr']==len(rows):
        action='hold_extent'
        reason='All sampled boundary points are confirmed not returned at the requested depth. Do not extend on this evidence; this is not proof of absence beyond the boundary.'
    elif counts['green'] or counts['yellow']:
        action='consider_directional_probe'
        reason='Top-ten visibility reaches this boundary. Consider a small outward probe only where populated territory, customer access or verified service scope makes it useful.'
    elif counts['red']:
        action='conditional_probe'
        reason='Lower-ranked visibility reaches this boundary. Probe only with an explicit relevant-territory question or supporting trend; red alone does not justify expansion.'
    else:
        action='repair_evidence'
        reason='Short result lists, errors, empty responses or missing measurements do not establish a negative boundary. Resolve uncertainty before extending.'
    return dict(counts=counts,action=action,reason=reason,uncertain=bool(counts['unknown']))


def collective_coverage(lanes):
    """Use the multi-query study, not a rigid color veto, to pitch the next probe."""
    directions={}
    for direction in ('north','south','east','west'):
        eligible=[l for l in lanes if direction in l.get('directions',{})]
        supporting=[l['query'] for l in eligible if l['directions'][direction]['action']=='consider_directional_probe']
        conditional=[l['query'] for l in eligible if l['directions'][direction]['action']=='conditional_probe']
        unknown=[l['query'] for l in eligible if l['directions'][direction]['uncertain']]
        threshold=max(2,math.ceil(len(lanes)*.6))
        cohort=len(supporting)>=threshold
        directions[direction]=dict(
            recommendation='shared_comparison_probe' if cohort else 'selective_probe_review' if supporting or conditional else 'hold_or_evidence_led_exception',
            supporting_themes=supporting,conditional_themes=conditional,uncertain_themes=unknown,
            comparison_themes=[l['query'] for l in eligible if l['query'] not in supporting] if cohort else [],
            explanation=('Most themes support investigating this direction. Subject to relevant geography, pitch a small shared outward band for all themes; an NR theme is a comparison/control, not an automatic veto.' if cohort else
                         'Use individual boundary evidence plus geography, interior trends and the study question. A small sentinel probe may test an evidence-backed exception; do not assume every NR boundary is final.'),
            execution='Proposal only: specify shared coordinates, incremental per-theme cost and a stop/reassess rule before collection.')
    return dict(policy='Information value first. Costs are disclosed, not minimized at the expense of a useful comparison. The 60%/two-theme threshold is an adjustable review heuristic, not an SEO law.',directions=directions)


def review(model, target_spacing_km=0.75):
    if not math.isfinite(target_spacing_km) or target_spacing_km<=0:
        raise ValueError('target spacing must be finite and positive')
    lanes=[]
    for lane in model['lanes']:
        rows=lane['records']; coords={(r['lat'],r['lng']):r for r in rows}
        ys=sorted({p[0] for p in coords});xs=sorted({p[1] for p in coords})
        regular=len(rows)==len(coords)==len(xs)*len(ys) and min(len(xs),len(ys))>1
        reasons=[]; result=dict(query=lane['query'],regular_rectangular_grid=regular)
        if not regular:
            reasons.append('Irregular or duplicate origins: review actual geographic gaps; square-grid heuristics do not apply.')
        else:
            pairs=[]
            for iy,y in enumerate(ys):
                for ix,x in enumerate(xs):
                    for other in ([(y,xs[ix+1])] if ix+1<len(xs) else [])+([(ys[iy+1],x)] if iy+1<len(ys) else []):
                        pairs.append(((y,x),other))
            gap=max(km(a,b) for a,b in pairs)
            edge=[r for (y,x),r in coords.items() if y in (ys[0],ys[-1]) or x in (xs[0],xs[-1])]
            valid=lambda r:r.get('state')=='found' and type(r.get('rank')) in (int,float) and r['rank']>0
            strong=sum(valid(r) and r['rank']<=3 for r in edge)
            boundary=boundary_review(edge)
            sides={name:boundary_review([r for (y,x),r in coords.items() if condition(y,x)])
                   for name,condition in [('north',lambda y,x:y==ys[-1]),('south',lambda y,x:y==ys[0]),
                                          ('east',lambda y,x:x==xs[-1]),('west',lambda y,x:x==xs[0])]}
            result.update(boundary=boundary,directions=sides)
            transitions=sum(valid(coords[a]) and valid(coords[b]) and abs(coords[a]['rank']-coords[b]['rank'])>=4 and any((coords[a]['rank']<=c)!=(coords[b]['rank']<=c) for c in (3,10)) for a,b in pairs)
            span=max(km((ys[0],xs[0]),(ys[-1],xs[0])),km((ys[len(ys)//2],xs[0]),(ys[len(ys)//2],xs[-1])))
            needed=max(3,math.ceil(span/target_spacing_km)+1)
            if needed%2==0:needed+=1
            result.update(max_neighbor_spacing_km=round(gap,3),edge_origins=len(edge),top3_edge_origins=strong,sharp_rank_transitions=transitions,suggested_same_extent_grid_size=needed)
            interior_signal=any(valid(r) for r in rows)
            top3_count=sum(valid(r) and r['rank']<=3 for r in rows)
            result['top3_share']=round(top3_count/len(rows),3) if rows else 0
            result['dominant_core']=bool(result['top3_share']>=0.50)
            if gap>target_spacing_km*1.05 and interior_signal:reasons.append('Densify: neighboring origins exceed the declared spatial resolution and measured visibility gives interior refinement a question to answer.')
            if transitions:reasons.append('Inspect/refine rank transitions: adjacent observed ranks cross a rank band with a gap of at least four positions.')
            reasons.append('Boundary decision: '+boundary['reason'])
        excluded=sum(r.get('state') in ('error','empty','unmeasured') for r in rows)
        if excluded:reasons.append('Resolve excluded measurements before interpreting apparent geographic gaps; more area is not the remedy for acquisition failure.')
        needs_review=bool(excluded or not regular or (regular and (gap>target_spacing_km*1.05 and interior_signal or transitions or boundary['action']!='hold_extent')))
        result.update(excluded_origins=excluded,reasons=reasons,status='review_required' if needs_review else 'no_automatic_trigger')
        lanes.append(result)
    return dict(schema='geogrid-sampling-review/v1',policy='Heuristic review, not proof of adequate coverage. Default 0.75 km is a declared planning preference, not a universal SEO threshold.',target_spacing_km=target_spacing_km,provider_calls=0,lanes=lanes,collective_coverage=collective_coverage(lanes),action='Resolve sampling recommendations before calling the study comprehensive. Keep paired queries comparable; preserve the original baseline. No automatic purchases.')


def summary(model):
    result=review(model)
    lines=['Planning review uses a 0.75 km spacing preference, not a universal SEO threshold. These are recommendations, not additional measurements.']
    lines.append('Multi-perspective strategy: The initial run dips a toe in the water with a high-resolution neighborhood baseline. Do not be cheap with DataForSEO tokens. A single baseline is step one; almost every business needs an outward enhancement, a regional zoom-out, or both to see the complete competitive picture across multiple zoom levels.')
    dominant_lanes=[l['query'] for l in result['lanes'] if l.get('dominant_core')]
    if dominant_lanes:
        lines.append(f"Regional zoom-out opportunity: {', '.join(dominant_lanes)} show dominant top-3 core visibility. When a business saturates its immediate neighborhood, the next strategic move is zooming out the provider viewport to a regional footprint (8-12 miles, provider zoom 11z-12z) to identify where county-wide competitors contest your service boundary.")
    active_edge_lanes=[l['query'] for l in result['lanes'] if l.get('boundary',{}).get('action')=='consider_directional_probe']
    if active_edge_lanes:
        lines.append(f"Directional expansion opportunity: {', '.join(active_edge_lanes)} show competitive near-miss positions reaching the boundary. The next strategic move is expanding outward at the same high spatial resolution in those active directions using enhance to map adjacent neighborhood conversion opportunities.")
    for lane in result['lanes']:
        if not lane['regular_rectangular_grid']:
            lines.append(lane['query']+': review the irregular sampling geometry before expanding.')
            continue
        parts=[f"{lane['query']}: maximum adjacent spacing {lane['max_neighbor_spacing_km']:.2f} km"]
        if any(r.startswith('Densify') for r in lane['reasons']):
            n=lane['suggested_same_extent_grid_size'];parts.append(f"consider {n} x {n} points over the same extent")
        parts.append(lane['boundary']['reason'])
        if lane['sharp_rank_transitions']:parts.append('inspect sharp neighboring rank transitions')
        if lane['excluded_origins']:parts.append('resolve excluded observations before interpreting gaps')
        lines.append('; '.join(parts)+'.')
    for direction,pitch in result['collective_coverage']['directions'].items():
        if pitch['recommendation']=='shared_comparison_probe':
            lines.append(direction.title()+': '+pitch['explanation']+' Additional comparison themes: '+', '.join(pitch['comparison_themes'])+'. Price a bounded first band and reassess, rather than repeatedly extending.')
    lines.append('Preserve this dated baseline. Reuse only compatible, sufficiently recent observations; estimate incremental collection before execution. No expansion has been collected by this report.')
    lines.append('Want more detail? Say enhance to your agent. It will assess these results, show the additional data cost, reuse eligible saved observations, and generate a new HTML report with a downloadable PDF within the approved budget. More area requires evidence that the territory is relevant; enhancement does not expand endlessly.')
    return lines


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--model',type=Path,required=True);p.add_argument('--target-spacing-km',type=float,default=.75);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    result=review(json.loads(a.model.read_text(encoding='utf-8')),a.target_spacing_km)
    with a.output.open('x',encoding='utf-8') as f:json.dump(result,f,indent=2)
    print(json.dumps(result,indent=2))

if __name__=='__main__':main()

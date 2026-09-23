"""Evidence-linked editorial layer. No provider calls or causal SEO diagnoses."""
from urllib.parse import urlsplit


def website_url(value):
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError('business.website must be a public HTTP(S) URL or domain')
    value = value.strip()
    if '://' not in value:
        value = 'https://' + value
    parsed = urlsplit(value)
    if (parsed.scheme not in ('http', 'https') or not parsed.hostname or
            '.' not in parsed.hostname or parsed.username or parsed.password or
            any(c.isspace() for c in value) or any(c in value for c in '<>"')):
        raise ValueError('business.website must be a public HTTP(S) URL without credentials')
    return value


def resolve(model, pointer):
    if not isinstance(pointer, str) or not pointer.startswith(('/lanes/', '/missing_evidence/', '/verification_notes/', '/business/', '/profile_review/')):
        raise ValueError('decision evidence must reference a report fact or disclosed limitation')
    current = model
    try:
        for part in pointer[1:].split('/'):
            key = part.replace('~1', '/').replace('~0', '~')
            current = current[int(key)] if isinstance(current, list) and key.isdigit() else current[key]
    except (IndexError, KeyError, TypeError, ValueError) as exc:
        raise ValueError('decision evidence reference does not exist: ' + pointer) from exc
    if current is None:
        raise ValueError('decision evidence reference is unknown: ' + pointer)
    return current


def build(model, supplied=None):
    findings = []
    for i, lane in enumerate(model['lanes']):
        m = lane['metrics']
        if not m['measured']:
            sentence = f"We cannot assess visibility for '{lane['query']}': no valid observations were collected."
        else:
            sentence = (f"For '{lane['query']}', the listing appeared among the first three results at "
                        f"{m['top3']} of {m['measured']} measured locations, and among the first ten at {m['top10']}.")
            if m['excluded']:
                sentence += f" Another {m['excluded']} locations could not be evaluated."
        findings.append({'query_id': lane['query_id'], 'text': sentence,
                         'evidence': f'/lanes/{i}/metrics', 'kind': 'computed_observation'})
    brief = {'schema': 'geogrid-decision-brief/v1', 'findings': findings,
             'reading_guide': 'Each dot represents a place someone could search from. Its number is the listing position returned for that search, not a customer count. Different searches can reveal different discovery gaps.',
             'boundary': 'These observations do not establish why rankings differ, how many people searched, or whether a change will generate sales.',
             'actions': [], 'authorship': 'Computed observations; recommendations, when supplied, are analyst judgments. Valid references do not prove an interpretation.'}
    if supplied is None:
        return brief
    if not isinstance(supplied, dict):
        raise ValueError('decision_brief must be an object')
    for key in ('headline', 'explanation'):
        value = supplied.get(key)
        if not isinstance(value, str) or not value.strip():
            raise ValueError('decision_brief requires ' + key)
        brief[key] = value.strip()
    actions = supplied.get('actions')
    if not isinstance(actions, list) or not 1 <= len(actions) <= 5:
        raise ValueError('decision_brief requires one to five prioritized actions')
    for i, raw in enumerate(actions):
        action = {'priority': i + 1, 'kind': 'analyst_recommendation', 'category': raw.get('category', 'investigation') if isinstance(raw, dict) else 'investigation'}
        if action['category'] not in ('business_information', 'measurement', 'investigation', 'maintain'):
            raise ValueError('invalid decision action category')
        for key in ('title', 'why', 'next_step', 'owner', 'success_check', 'uncertainty'):
            value = raw.get(key) if isinstance(raw, dict) else None
            if not isinstance(value, str) or not value.strip():
                raise ValueError('decision action requires ' + key)
            action[key] = value.strip()
        refs = raw.get('evidence')
        if not isinstance(refs, list) or not refs:
            raise ValueError('decision action requires evidence references')
        action['evidence'] = [{'pointer': ref, 'value': resolve(model, ref)} for ref in refs]
        brief['actions'].append(action)
    return brief

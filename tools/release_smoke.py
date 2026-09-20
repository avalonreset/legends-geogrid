"""Exercise the documented offline collection-to-report workflow for release QA.

No credentials or network calls are required. Every output is synthetic.
Artifacts go into a new child of runs/release-smoke (ignored by Git).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(script: str, *args: str) -> None:
    subprocess.run([sys.executable, str(ROOT / 'tools' / script), *args],
                   cwd=ROOT, check=True)


def read(path: Path):
    return json.loads(path.read_text(encoding='utf-8'))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-root', type=Path, default=ROOT / 'runs' / 'release-smoke')
    args = parser.parse_args()
    args.output_root.mkdir(parents=True, exist_ok=True)
    output = Path(tempfile.mkdtemp(prefix='candidate-', dir=args.output_root.resolve()))
    reports = []
    for name in ('urban-dentist', 'rural-mobile', 'georeferenced-mobile'):
        dest = output / name
        run('strategy_report.py', '--config', str(ROOT / 'examples' / 'reports' / f'{name}.json'),
            '--output-dir', str(dest), '--proof', '--require-pdf-qa')
        reports.append(dest)
    collected = output / 'replay'
    run('adaptive_geogrid.py', '--config', str(ROOT / 'examples' / 'adaptive' / 'sample.json'),
        '--replay', str(ROOT / 'examples' / 'adaptive' / 'replay.json'), '--output-dir', str(collected))
    config = {
        'schema_version': 1, 'synthetic': True,
        'business': {'name': 'Synthetic Example Restaurant', 'location': 'Fictional test location',
                     'lat': 40.0, 'lng': -100.0},
        'thesis': 'Test whether the recorded expansion supports a sampled stopping decision.',
        'objectives': ['Verify the collector and renderer share the same observations.'],
        'lanes': [{'query_id': q, 'label': q.title(), 'query': keyword,
                   'records_path': 'replay/observations.json'}
                  for q, keyword in [('pizza', 'pizza restaurant'), ('delivery', 'pizza delivery')]],
    }
    config_path = output / 'handoff.json'
    config_path.write_text(json.dumps(config), encoding='utf-8')
    dest = output / 'handoff-report'
    run('strategy_report.py', '--config', str(config_path), '--output-dir', str(dest),
        '--proof', '--require-pdf-qa')
    reports.append(dest)
    summaries = []
    for folder in reports:
        qa = read(folder / 'report-qa.json')
        model = read(folder / 'report-model.json')
        if qa['status'] != 'passed' or not model['synthetic'] or qa['network_calls'] != 0:
            raise ValueError(f'Synthetic report acceptance failed: {folder.name}')
        summaries.append({'example': folder.name, 'status': qa['status'],
                          'pdf_sha256': hashlib.sha256((folder / 'report.pdf').read_bytes()).hexdigest(),
                          'metrics': qa['metrics']})
    receipt = {'status': 'passed', 'synthetic': True, 'reports': summaries,
               'collector_observations': len(read(collected / 'observations.json'))}
    (output / 'release-smoke.json').write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'status': 'passed', 'artifact_directory': str(output)}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

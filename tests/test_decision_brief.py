import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
from decision_brief import build, website_url


class DecisionBriefTests(unittest.TestCase):
    def model(self):
        return {'lanes': [{'query_id': 'q1', 'query': 'restaurant', 'metrics':
                {'measured': 25, 'top3': 17, 'top10': 25, 'excluded': 0}}],
                'missing_evidence': ['Address unresolved.']}

    def brief(self):
        return {'headline': 'Check the address first', 'explanation': 'Directions require confirmation.',
                'actions': [dict(title='Confirm location', why='Sources disagree.',
                                next_step='Ask the operator.', owner='Business owner',
                                success_check='Sources agree with confirmed location.',
                                uncertainty='Neither source establishes current operations.',
                                evidence=['/missing_evidence/0'])]}

    def test_counts_computed_not_supplied(self):
        self.assertIn('17 of 25', build(self.model())['findings'][0]['text'])

    def test_no_observations_not_zero_visibility(self):
        model=self.model();model['lanes'][0]['metrics']['measured']=0
        self.assertIn('cannot assess', build(model)['findings'][0]['text'])

    def test_evidence_values_travel_with_actions(self):
        result=build(self.model(),self.brief())
        self.assertEqual(result['actions'][0]['evidence'][0]['value'],'Address unresolved.')

    def test_invented_reference_rejected(self):
        brief=self.brief();brief['actions'][0]['evidence']=['/missing_evidence/99']
        with self.assertRaises(ValueError):build(self.model(),brief)

    def test_success_check_required(self):
        brief=self.brief();del brief['actions'][0]['success_check']
        with self.assertRaises(ValueError):build(self.model(),brief)

    def test_domain(self):
        self.assertEqual(website_url('example.com'),'https://example.com')
        for bad in ('javascript:alert(1)', 'https://user:secret@example.com', 'https://example.com/<bad>'):
            with self.assertRaises(ValueError):website_url(bad)

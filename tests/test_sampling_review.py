import unittest
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from sampling_review import review

class SamplingTests(unittest.TestCase):
    def model(self,step=.0135):
        return {'lanes':[{'query':'restaurant','records':[dict(lat=40+i*step,lng=-75+j*step,rank=2,state='found') for i in range(5) for j in range(5)]}]}
    def test_coarse_and_strong_edge(self):
        lane=review(self.model())['lanes'][0]
        self.assertGreater(lane['suggested_same_extent_grid_size'],5)
        self.assertEqual(lane['top3_edge_origins'],16)
        self.assertTrue(any('Densify' in x for x in lane['reasons']))
    def test_small_extent_not_automatically_dense(self):
        m=self.model(.001)
        for r in m['lanes'][0]['records']:r['rank']=8
        lane=review(m)['lanes'][0]
        self.assertFalse(any(x.startswith('Densify') for x in lane['reasons']))
        self.assertEqual(lane['boundary']['action'],'consider_directional_probe')
    def test_errors_not_rank_opportunity(self):
        m=self.model(.001);m['lanes'][0]['records'][0].update(rank=None,state='error')
        self.assertEqual(review(m)['lanes'][0]['excluded_origins'],1)
    def test_duplicates_are_not_regular(self):
        m=self.model();m['lanes'][0]['records'].append(m['lanes'][0]['records'][0])
        self.assertFalse(review(m)['lanes'][0]['regular_rectangular_grid'])
    def test_invalid_spacing(self):
        for x in (0,-1,float('nan')):
            with self.assertRaises(ValueError):review(self.model(),x)
    def test_transition(self):
        m=self.model(.001);m['lanes'][0]['records'][12]['rank']=8
        self.assertEqual(review(m)['lanes'][0]['sharp_rank_transitions'],4)

    def test_full_nr_perimeter_holds_extent_but_preserves_interior_detail(self):
        m=self.model()
        for i,r in enumerate(m['lanes'][0]['records']):
            if i//5 in (0,4) or i%5 in (0,4):
                r.update(state='not_returned',rank=None,requested_depth=20,observed_ranks=list(range(1,21)))
        lane=review(m)['lanes'][0]
        self.assertEqual('hold_extent',lane['boundary']['action'])
        self.assertTrue(all(x['action']=='hold_extent' for x in lane['directions'].values()))
        self.assertTrue(any(x.startswith('Densify') for x in lane['reasons']))

    def test_short_nr_is_uncertainty_not_a_negative_boundary(self):
        m=self.model(.001)
        for r in m['lanes'][0]['records']:
            r.update(state='not_returned',rank=None,requested_depth=20,observed_ranks=[1,2,3])
        lane=review(m)['lanes'][0]
        self.assertEqual('repair_evidence',lane['boundary']['action'])
        self.assertEqual(16,lane['boundary']['counts']['unknown'])

    def test_red_is_conditional_and_directions_differ(self):
        m=self.model(.001)
        for r in m['lanes'][0]['records']:r['rank']=17
        self.assertEqual('conditional_probe',review(m)['lanes'][0]['boundary']['action'])
        for r in m['lanes'][0]['records'][-5:]:r['rank']=7
        lane=review(m)['lanes'][0]
        self.assertEqual('consider_directional_probe',lane['directions']['north']['action'])
        self.assertEqual('conditional_probe',lane['directions']['south']['action'])

    def test_three_strong_themes_include_nr_comparison_without_erasing_hold(self):
        import copy
        m=self.model(.001)
        m['lanes']=[dict(query='theme '+str(i),records=copy.deepcopy(m['lanes'][0]['records'])) for i in range(4)]
        for row in m['lanes'][3]['records']:
            row.update(state='not_returned',rank=None,requested_depth=20,observed_ranks=list(range(1,21)))
        result=review(m)
        self.assertEqual('hold_extent',result['lanes'][3]['boundary']['action'])
        for pitch in result['collective_coverage']['directions'].values():
            self.assertEqual('shared_comparison_probe',pitch['recommendation'])
            self.assertEqual(['theme 3'],pitch['comparison_themes'])

    def test_all_nr_allows_reasoned_exception_without_recommending_blind_growth(self):
        m=self.model()
        for row in m['lanes'][0]['records']:
            row.update(state='not_returned',rank=None,requested_depth=20,observed_ranks=list(range(1,21)))
        result=review(m)
        self.assertFalse(any(x.startswith('Densify') for x in result['lanes'][0]['reasons']))
        self.assertEqual('hold_or_evidence_led_exception',result['collective_coverage']['directions']['north']['recommendation'])

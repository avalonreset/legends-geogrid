import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))

import local_heatmap_poc as collector
from study import assemble_report
import study_enhance as enhance
from test_study import fixture


def response(task, stamp=None, rank=2):
    return {'status_code':20000,'cost':.002,'tasks':[{'status_code':20000,'data':task,
        'result':[{'datetime':stamp or datetime.now(timezone.utc).isoformat(),
                   'items':[{'type':'maps_search','rank_group':rank,'title':'Example Pizza','cid':'123'}]}]}]}


class EnhanceTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);src=self.root/'research';src.mkdir()
        path,self.plan=fixture(src)
        self.base=self.root/'baseline';evidence=self.base/'evidence'
        shutil.copytree(src,evidence);(evidence/'plan.json').rename(evidence/'study-plan.json')
        args=enhance.arguments(self.plan,'pizza restaurant')
        for k,v in self.plan['settings'].items():setattr(args,k,v)
        args.output_dir=str(self.base/'lane-1');args.location_label=self.plan['business']['location_label']
        points=collector.generate_grid(40,-75,3,1);tasks=collector.build_tasks(args,points)
        self.raw={'status_code':20000,'cost':.018,'tasks':[response(t)['tasks'][0] for t in tasks]}
        self.outputs=collector.write_outputs(args,tasks,self.raw,collector.parse_results(self.raw,points,args))
        assemble_report(self.base,self.base/'report-config.json')
        self.out=self.root/'enhanced';self.vault=self.root/'vault'

    def preview(self):
        return enhance.run(self.base,self.out,vault=self.vault)

    def test_nested_grid_reuses_exact_points_and_estimates_only_new_calls(self):
        with patch.object(collector,'call_dataforseo_live_task',side_effect=AssertionError('paid')):
            m=enhance.plan_enhancement(self.base)
            self.preview()
        self.assertEqual((5,16,9),(m['grid_size'],m['new_calls'],m['reused_observations']))
        self.assertAlmostEqual(collector.estimate_scan_cost(16,20,'live'),m['estimated_incremental_usd'])
        self.assertTrue((self.out/'enhance.html').is_file())
        self.assertIn('enhancement-proposed',(self.vault/'GeoGrid/catalog.md').read_text())

    def test_stale_or_unknown_dates_are_refreshed_not_invented(self):
        raw_path=Path(self.outputs['raw_payload'])
        for task in self.raw['tasks']:task['result'][0].pop('datetime')
        raw_path.write_text(json.dumps(self.raw))
        m=enhance.plan_enhancement(self.base)
        self.assertEqual(0,m['reused_observations']);self.assertEqual(25,m['new_calls'])
        self.assertEqual(9,m['lanes'][0]['refresh_locations'])

    def test_budget_gate_and_tampered_source_prevent_http(self):
        self.preview()
        with patch.object(collector,'call_dataforseo_live_task') as call:
            with self.assertRaisesRegex(ValueError,'ceiling'):
                enhance.run(self.base,self.out,True,.0001,self.vault)
            p=Path(self.outputs['raw_payload']);p.write_text(p.read_text()+' ')
            with self.assertRaisesRegex(ValueError,'baseline changed'):
                enhance.run(self.base,self.out,True,1,self.vault)
            call.assert_not_called()

    def test_ambiguous_post_is_never_retried(self):
        self.preview()
        with patch.object(collector,'call_dataforseo_live_task',side_effect=OSError('connection lost')) as call:
            with self.assertRaises(OSError):enhance.run(self.base,self.out,True,1,self.vault)
            with self.assertRaisesRegex(ValueError,'ambiguous'):
                enhance.run(self.base,self.out,True,1,self.vault)
            self.assertEqual(1,call.call_count)

    def test_complete_banks_and_rerender_never_recollects(self):
        before=Path(self.outputs['parsed_json']).read_bytes();self.preview()
        def render(config, report, *args):
            report.mkdir();(report/'report.html').write_text('report');(report/'report.pdf').write_bytes(b'fixture')
            (report/'report-qa.json').write_text('{"status":"passed"}')
        with patch.object(collector,'call_dataforseo_live_task',side_effect=lambda t,timeout:response(t)) as call, patch('strategy_report.build',side_effect=render):
            result=enhance.run(self.base,self.out,True,1,self.vault)
            self.assertEqual('enhanced',result['status']);self.assertEqual(16,call.call_count)
            enhance.run(self.base,self.out,True,1,self.vault)
            self.assertEqual(16,call.call_count)
        self.assertEqual(before,Path(self.outputs['parsed_json']).read_bytes())
        self.assertEqual(25,len(enhance.read(self.out/'lane-1/enhanced-records.json')))
        self.assertTrue((self.out/'enhancement-complete.json').exists())
        next_plan=enhance.plan_enhancement(self.out)
        self.assertEqual(0,next_plan['new_calls'])

    def test_report_failure_recovers_without_paid_recollection(self):
        self.preview()
        with patch.object(collector,'call_dataforseo_live_task',side_effect=lambda t,timeout:response(t)) as call, patch('strategy_report.build',side_effect=ValueError('map unavailable')):
            for _ in range(2):
                with self.assertRaisesRegex(ValueError,'map unavailable'):
                    enhance.run(self.base,self.out,True,1,self.vault)
            self.assertEqual(16,call.call_count)

    def test_provider_timestamp_propagates_without_using_export_time(self):
        data=enhance.read(self.outputs['parsed_json'])
        self.assertTrue(all(r['sampled_at'] for r in data['results']))
        self.assertIsNone(collector.provider_sampled_at({'result':[{}]}))
        self.assertIsNone(collector.provider_sampled_at({'result':[{'datetime':'2026-09-22T10:00:00'}]}))

    def test_expired_reuse_and_changed_plan_block_before_http(self):
        self.preview()
        with patch('study_enhance.datetime') as clock, patch.object(collector,'call_dataforseo_live_task') as call:
            clock.now.return_value=datetime.now(timezone.utc)+timedelta(days=2)
            clock.fromisoformat=datetime.fromisoformat
            with self.assertRaisesRegex(ValueError,'reuse window expired'):
                enhance.run(self.base,self.out,True,1,self.vault)
            call.assert_not_called()
        p=self.out/'enhancement-plan.json';p.write_text(p.read_text()+' ')
        with self.assertRaisesRegex(ValueError,'plan changed'):self.preview()

    def test_actual_cost_overage_stops_before_second_post(self):
        self.preview()
        def expensive(t,timeout):
            result=response(t);result['cost']=1.0;return result
        with patch.object(collector,'call_dataforseo_live_task',side_effect=expensive) as call:
            with self.assertRaisesRegex(ValueError,'budget exhausted'):
                enhance.run(self.base,self.out,True,.5,self.vault)
            self.assertEqual(1,call.call_count)

    def test_full_renderer_handoff_offline(self):
        from strategy_report import build
        self.preview()
        def offline(config, output, *args):
            return build(config,output,True,True,basemap_provider='schematic')
        with patch.object(collector,'call_dataforseo_live_task',side_effect=lambda t,timeout:response(t)), patch('strategy_report.build',side_effect=offline):
            result=enhance.run(self.base,self.out,True,1,self.vault)
        model=enhance.read(self.out/'report/report-model.json')
        self.assertEqual(25,model['lanes'][0]['metrics']['measured'])
        self.assertIn('report.pdf',Path(result['report_html']).read_text(encoding='utf-8'))
        self.assertEqual('passed',enhance.read(self.out/'report/report-qa.json')['status'])


if __name__=='__main__':unittest.main()

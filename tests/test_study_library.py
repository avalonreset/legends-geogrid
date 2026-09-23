import json
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from study_library import save_checkpoint,bank_study,root_path
from test_study import fixture

class LibraryTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name);self.vault=self.root/'vault';self.plan,self.data=fixture(self.root)
    def bank(self,**kw):return bank_study(self.plan,vault=self.vault,**kw)
    def test_immutable_idempotent_and_portable(self):
        first=self.bank();again=self.bank();self.assertEqual(again['status'],'already_banked')
        note=Path(first['note']);self.assertTrue((note.parent/'artifacts/research/study-plan.json').is_file());self.assertIn('Business dossier',note.read_text());self.assertNotIn(str(self.root),note.read_text())
        self.assertTrue((root_path(self.vault)/'catalog.md').is_file())
    def test_hash_tamper_rejected(self):
        (self.root/'site.json').write_text('{}')
        with self.assertRaisesRegex(ValueError,'hash mismatch'):self.bank()
    def test_history_and_parent_business(self):
        first=self.bank();next_run=self.root/'expansion';next_run.mkdir()
        child=self.bank(run_dir=next_run,parent_study=first['study_id'],relationship='expansion')
        self.assertNotEqual(child['study_id'],first['study_id']);self.assertIn(first['study_id'],Path(child['note']).read_text())
        with self.assertRaises(ValueError):self.bank(run_dir=next_run,parent_study='a'*24,relationship='expansion')
    def test_preserves_user_notes_and_catalog(self):
        first=self.bank();root=root_path(self.vault);catalog=root/'catalog.md';catalog.write_text('my notes')
        dossier=Path(first['note']).parents[2]/'business.md';dossier.write_text('owner notes')
        self.bank(stage='later');self.assertEqual(catalog.read_text(),'my notes');self.assertEqual(dossier.read_text(),'owner notes')
    def test_no_env_or_traversal(self):
        env=self.root/'.env';env.write_text('secret')
        for files in ({'x.json':env},{'../x.json':self.plan}):
            with self.assertRaises(ValueError):save_checkpoint(files,vault=self.vault)
    def test_collector_bank_excludes_unrelated_files(self):
        run=self.root/'run';run.mkdir();(run/'dataforseo-response.raw.json').write_text('{}');(run/'private.json').write_text('{}');(run/'.env').write_text('secret')
        result=self.bank(run_dir=run);files=json.loads((Path(result['note']).parent/'manifest.json').read_text())['sha256']
        self.assertIn('collection/dataforseo-response.raw.json',files);self.assertFalse(any('private' in n or '.env' in n for n in files))
    def test_stored_artifact_tamper_detected(self):
        r=self.bank();(Path(r['note']).parent/'artifacts/research/site.json').write_text('changed')
        with self.assertRaisesRegex(ValueError,'integrity mismatch'):self.bank()
    def test_lock_fails_before_mutation(self):
        root=root_path(self.vault);root.mkdir(parents=True);(root/'.bank.lock').touch()
        with self.assertRaisesRegex(ValueError,'busy'):self.bank()

    def test_cli_research_automatically_banks(self):
        from study import main
        from unittest.mock import patch
        (self.root/'research-ledger.jsonl').write_text('{"event":"response","actual_usd":0}\n')
        with patch('study.research',return_value={'source':{'file':'gbp.json'}}):
            status=main(['research','--request','unused.json','--output-dir',str(self.root),'--execute','--vault-dir',str(self.vault)])
        self.assertEqual(status,0)
        self.assertEqual(len(list(root_path(self.vault).rglob('manifest.json'))),1)
    def test_interrupted_collection_banks_checkpoint_without_retry(self):
        from study import run
        from unittest.mock import patch
        import subprocess
        stages=[]
        with patch('study.subprocess.run',side_effect=subprocess.CalledProcessError(1,['collector'])) as collector:
            with self.assertRaises(subprocess.CalledProcessError):run(self.plan,self.root/'failed',True,1,stages.append)
        self.assertEqual(stages,['collection-started','collection-interrupted'])
        collector.assert_called_once()

    def test_report_custom_config_does_not_bank_config_parent(self):
        from strategy_report import main
        from unittest.mock import patch
        with patch('strategy_report.build',return_value={'status':'passed'}),patch('study_library.bank_study',return_value={'status':'banked'}) as bank:
            code=main(['--config',str(self.root/'unrelated/config.json'),'--output-dir',str(self.root/'report'),'--study-plan',str(self.plan)])
        self.assertEqual(code,0);self.assertIsNone(bank.call_args.args[1])
    def test_report_standard_plan_banks_exact_run(self):
        from strategy_report import main
        from unittest.mock import patch
        evidence=self.root/'collection/evidence';evidence.mkdir(parents=True);plan=evidence/'study-plan.json';plan.write_text('{}')
        with patch('strategy_report.build',return_value={'status':'passed'}),patch('study_library.bank_study',return_value={'status':'banked'}) as bank:
            code=main(['--config',str(self.root/'elsewhere/config.json'),'--output-dir',str(self.root/'report'),'--study-plan',str(plan)])
        self.assertEqual(code,0);self.assertEqual(bank.call_args.args[1].resolve(),evidence.parent.resolve())

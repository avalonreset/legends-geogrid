"""Offline regression tests for street-map defaults and failure behavior."""
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from report_basemaps import (
    BasemapError,
    BasemapSession,
    base_record,
    google,
    google_key_status,
    load_dotenv_google_keys,
    provider_for,
    validate_image,
)
from report_model import load_config
from strategy_report import build
from test_strategy_report import config, observation


class BasemapTests(unittest.TestCase):
    def test_real_default_is_free_synthetic_default_is_offline(self):
        lane={'map':{}}
        self.assertEqual('openfreemap',provider_for({'synthetic':False},lane))
        self.assertEqual('schematic',provider_for({'synthetic':True},lane))
        self.assertEqual('google',provider_for({'synthetic':False},lane,'google'))
        self.assertEqual('schematic',provider_for({'synthetic':False},lane,'schematic'))
        self.assertEqual('supplied',provider_for({'synthetic':False},{'map':{'basemap':{'path':'local.png'}}}))
        with self.assertRaises(BasemapError):provider_for({'synthetic':False},lane,'supplied')

    def real_config(self,root):
        cfg=config([dict(observation(),source='user supplied observation')]);cfg['synthetic']=False
        path=root/'input.json';path.write_text(json.dumps(cfg),encoding='utf-8');return path

    def test_failed_default_map_never_publishes_a_schematic_report(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);path=self.real_config(root)
            with patch('report_basemaps.openfreemap',side_effect=BasemapError('offline')):
                with self.assertRaisesRegex(BasemapError,'offline'):build(path,root/'report')
            self.assertFalse(any((root/'report').iterdir()))
            self.assertEqual([],list(root.glob('.geogrid-report-*')))

    def test_explicit_schematic_stays_offline_for_real_observations(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);path=self.real_config(root)
            with patch('socket.socket',side_effect=AssertionError('unexpected network')):
                receipt=build(path,root/'report',basemap_provider='schematic')
            self.assertEqual(0,receipt['network_calls'])
            self.assertEqual(['schematic'],receipt['basemap_providers'])

    def test_google_requires_explicit_paid_opt_in_and_key(self):
        with patch('report_basemaps.urllib.request.urlopen',side_effect=AssertionError('must not call')):
            with self.assertRaisesRegex(BasemapError,'allow-google'):
                google([-76,39,-74,41],Path('unused'),'light',452)
            with patch.dict('os.environ',{},clear=True),self.assertRaisesRegex(BasemapError,'GOOGLE_MAPS_API_KEY'):
                google([-76,39,-74,41],Path('unused'),'light',452,True)

    def test_google_errors_never_echo_key_or_retry(self):
        from urllib.error import URLError
        with patch.dict('os.environ',{'GOOGLE_MAPS_API_KEY':'fixture-secret-not-real'}):
            with patch('report_basemaps.urllib.request.urlopen',side_effect=URLError('fixture-secret-not-real')) as call:
                with self.assertRaises(BasemapError) as err:
                    google([-76,39,-74,41],Path('unused'),'light',452,True)
                self.assertNotIn('fixture-secret',str(err.exception));self.assertEqual(1,call.call_count)

    def test_google_bounds_preserve_center_and_entire_image(self):
        from PIL import Image,ImageDraw
        image=Image.new('RGB',(1280,1122),'white');ImageDraw.Draw(image).line((0,0,1279,1121),fill='black',width=20)
        data=io.BytesIO();image.save(data,format='PNG')
        response=io.BytesIO(data.getvalue());response.headers={}
        with tempfile.TemporaryDirectory() as folder,patch.dict('os.environ',{'GOOGLE_MAPS_API_KEY':'fixture-key'}):
            with patch('report_basemaps.urllib.request.urlopen',return_value=response):
                base,calls=google([-75.02,39.98,-74.98,40.02],Path(folder)/'map.png','light',452,True)
            self.assertEqual(1,calls);self.assertEqual(64,base['protected_bottom_px'])
            w,s,e,n=base['bounds'];self.assertLess(w,-75.02);self.assertGreater(e,-74.98)
            self.assertLess(s,39.98);self.assertGreater(n,40.02)
            self.assertAlmostEqual(-75,(w+e)/2)

    def test_identical_views_are_acquired_once(self):
        with tempfile.TemporaryDirectory() as folder:
            session=BasemapSession(folder,'light')
            with patch('report_basemaps.openfreemap',return_value=({'bounds':[-76,39,-74,41]},7)) as fetch:
                session.acquire('openfreemap',[-76,39,-74,41],452)
                session.acquire('openfreemap',[-76,39,-74,41],452)
                session.acquire('openfreemap',[-76,39,-74,41],410)
            self.assertEqual(2,fetch.call_count);self.assertEqual(14,session.network_calls)

    def test_blank_or_wrong_size_maps_rejected(self):
        from PIL import Image
        data=io.BytesIO();Image.new('RGB',(32,32),'white').save(data,format='PNG')
        with self.assertRaises(BasemapError):validate_image(data.getvalue(),(32,32))
        with self.assertRaises(BasemapError):validate_image(b'not an image',(32,32))

    def test_street_html_default_and_script_safety(self):
        import local_heatmap_poc as local
        from report_street_html import street_map_panel
        args=local.parse_args(['--keyword','pizza','--target-name','</script><script>bad()</script>','--center-lat','40','--center-lng','-75'])
        points=local.generate_grid(40,-75,3,1)
        results=[local.PointResult(p,1,None,[],status='found') for p in points]
        fragment=street_map_panel(args,results)
        self.assertIn('tiles.openfreemap.org/styles/liberty',fragment)
        self.assertIn('Street map unavailable',fragment)
        self.assertNotIn('bad()',fragment)
        self.assertIn('visibility:hidden',fragment)
        document=local.render_html(args,results,Path('report.md'))
        self.assertLess(document.index('Rank origins on a street map'),document.index('Coordinate-only diagnostic'))

    def test_collector_writes_a_reusable_report_config(self):
        import local_heatmap_poc as local
        args=local.parse_args(['--keyword','pizza','--target-name','Example','--center-lat','40','--center-lng','-75'])
        points=local.generate_grid(40,-75,3,1)
        results=[local.PointResult(p,1,None,[],status='found',observed_ranks=(1,),returned_items_count=1,organic_items_count=1) for p in points]
        with tempfile.TemporaryDirectory() as folder:
            args.output_dir=folder
            outputs=local.write_outputs(args,[],{'tasks':[]},results)
            model=load_config(outputs['report_config'])
            self.assertFalse(model['synthetic'])
            self.assertEqual('openfreemap',provider_for(model,model['lanes'][0]))

    def test_persistent_google_key_lookup_order_and_symlink_refusal(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            home = root / 'home'
            repo = root / 'repo'
            secrets_dir = home / '.cto-legends' / 'secrets'
            secrets_dir.mkdir(parents=True)
            repo.mkdir(parents=True)

            explicit_file = root / 'explicit.env'
            user_secrets_file = secrets_dir / 'geogrid.env'
            env_local_file = repo / '.env.local'
            env_file = repo / '.env'

            with patch.dict('os.environ', {}, clear=True):
                self.assertEqual({'present': False, 'source': 'missing'}, google_key_status(root_dir=repo, user_home=home, env_file=''))

                env_file.write_text('GOOGLE_MAP_TILES_API_KEY=repo-dotenv-key\n', encoding='utf-8')
                self.assertEqual('repo-dotenv-key', load_dotenv_google_keys(root_dir=repo, user_home=home, env_file='')['GOOGLE_MAP_TILES_API_KEY'])
                self.assertEqual({'present': True, 'source': 'repo_dotenv'}, google_key_status(root_dir=repo, user_home=home, env_file=''))

                env_local_file.write_text('GOOGLE_MAP_TILES_API_KEY=repo-local-key\n', encoding='utf-8')
                self.assertEqual('repo-local-key', load_dotenv_google_keys(root_dir=repo, user_home=home, env_file='')['GOOGLE_MAP_TILES_API_KEY'])

                user_secrets_file.write_text('GOOGLE_MAP_TILES_API_KEY=user-secrets-key\n', encoding='utf-8')
                self.assertEqual('user-secrets-key', load_dotenv_google_keys(root_dir=repo, user_home=home, env_file='')['GOOGLE_MAP_TILES_API_KEY'])
                self.assertEqual({'present': True, 'source': 'user_secrets_env'}, google_key_status(root_dir=repo, user_home=home, env_file=''))

                explicit_file.write_text('GOOGLE_MAP_TILES_API_KEY=explicit-env-key\n', encoding='utf-8')
                self.assertEqual('explicit-env-key', load_dotenv_google_keys(root_dir=repo, user_home=home, env_file=explicit_file)['GOOGLE_MAP_TILES_API_KEY'])
                self.assertEqual({'present': True, 'source': 'explicit_env_file'}, google_key_status(root_dir=repo, user_home=home, env_file=explicit_file))

            with patch.dict('os.environ', {'GOOGLE_MAP_TILES_API_KEY': 'proc-env-key'}, clear=True):
                self.assertEqual({'present': True, 'source': 'env'}, google_key_status(root_dir=repo, user_home=home, env_file=explicit_file))

            # Explicit dotenv_path override still works
            self.assertEqual('repo-dotenv-key', load_dotenv_google_keys(dotenv_path=env_file)['GOOGLE_MAP_TILES_API_KEY'])

            # Symlinked env file is refused when OS allows creating one
            link_env = root / 'link.env'
            try:
                link_env.symlink_to(explicit_file)
            except OSError:
                return
            with patch.dict('os.environ', {}, clear=True):
                self.assertEqual({}, load_dotenv_google_keys(dotenv_path=link_env))

    def test_doctor_reports_google_key_source_without_leaking_value(self):
        from contextlib import redirect_stdout
        import geogrid_doctor

        secret = 'fixture-never-print-google-key-998877'
        buf = io.StringIO()
        with patch.dict('os.environ', {'GOOGLE_MAP_TILES_API_KEY': secret}), \
             patch('sys.argv', ['geogrid_doctor.py', '--json']), \
             redirect_stdout(buf):
            rc = geogrid_doctor.main()
        self.assertEqual(rc, 0)
        output = buf.getvalue()
        self.assertNotIn(secret, output)
        payload = json.loads(output)
        self.assertEqual(payload['google_maps_key'], {'present': True, 'source': 'env'})

if __name__=='__main__':unittest.main()

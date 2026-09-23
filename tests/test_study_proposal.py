"""The proposal must preserve validated scope, not invent or overwrite evidence."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from test_study import fixture
from study_proposal import render_proposal


class ProposalTests(unittest.TestCase):
    def test_both_themes_preserve_scope_and_frozen_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);path,plan=fixture(root)
            original=path.read_bytes()
            for theme in ('geogrid','light'):
                out=root/theme
                with patch('urllib.request.urlopen',side_effect=AssertionError('no network')):
                    result=render_proposal(path,out,theme)
                self.assertEqual(result['pdf']['status'],'passed')
                self.assertEqual(result['provider_calls'],0)
                html=(out/'proposal.html').read_text(encoding='utf-8')
                self.assertIn(plan['identity']['reconciliation'],html)
                self.assertIn(plan['selection']['fewer_themes']['reason'],html)
                self.assertIn('not an all-in total',html)
                self.assertIn('pizza category',html.lower())
                self.assertIn('class="study-overview"',html)
                self.assertIn('<details>',html)
                frozen=(out/'proposal.pdf').read_bytes()
                with self.assertRaisesRegex(ValueError,'output exists'):
                    render_proposal(path,out,theme)
                self.assertEqual(frozen,(out/'proposal.pdf').read_bytes())
            self.assertEqual(original,path.read_bytes())

    def test_invalid_evidence_fails_before_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);path,plan=fixture(root)
            (root/'site.json').write_text('{}')
            with self.assertRaisesRegex(ValueError,'hash mismatch'):
                render_proposal(path,root/'out')
            self.assertFalse((root/'out').exists())

    def test_copy_is_escaped_and_long_sections_paginate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);path,plan=fixture(root)
            plan['identity']['reconciliation']='<script>not executable</script> '+('Unresolved identity detail. '*220)
            path.write_text(json.dumps(plan))
            result=render_proposal(path,root/'out')
            html=(root/'out/proposal.html').read_text(encoding='utf-8')
            self.assertNotIn('<script>',html)
            self.assertIn('&lt;script&gt;',html)
            self.assertGreater(len(result['pdf']['pages']),1)

import json
import tempfile
import unittest
from pathlib import Path
from test_study import fixture
from study_contract import validate
from profile_review import validate as validate_review, readable


class ProfileReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.path,self.plan=fixture(Path(self.temp.name))

    def review(self):
        return validate(self.path)[1]['profile_review']

    def test_every_valid_study_includes_profile_review(self):
        review=self.review()
        self.assertEqual(review['cid'],'123')
        self.assertEqual(review['themes'][0]['query'],'pizza restaurant')
        category=next(f for f in review['facts'] if f['field']=='category')
        self.assertEqual(category['value'],'Pizza restaurant')
        self.assertEqual(category['evidence']['pointer'],'/tasks/0/result/0/items/0/category')
        self.assertEqual(validate_review(review),review)

    def test_missing_phone_is_unknown_not_profile_defect(self):
        phone=next(f for f in self.review()['facts'] if f['field']=='phone')
        self.assertEqual(phone['status'],'unknown')
        self.assertIsNone(phone['evidence'])
        self.assertIn('not established as missing',readable(phone))

    def test_observation_requires_provenance(self):
        review=self.review();review['facts'][0]['evidence']=None
        with self.assertRaises(ValueError):
            validate_review(review)

    def test_required_fields_cannot_be_dropped(self):
        review=self.review();review['facts'].pop()
        with self.assertRaises(ValueError):validate_review(review)

    def test_review_does_not_export_arbitrary_provider_fields(self):
        root=self.path.parent;p=root/'gbp.json';doc=json.loads(p.read_text())
        doc['tasks'][0]['result'][0]['items'][0]['unrelated_private_field']='never-export'
        p.write_text(json.dumps(doc))
        from study_contract import digest
        next(s for s in self.plan['sources'] if s['id']=='gbp')['sha256']=digest(p)
        self.path.write_text(json.dumps(self.plan))
        self.assertNotIn('never-export',json.dumps(self.review()))

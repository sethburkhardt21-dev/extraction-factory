import tempfile
import unittest
from pathlib import Path

from hermes_factory.ingest import parse_page_spec, ingest_pdf
from hermes_factory.source import load_source_units


class PageSpecTests(unittest.TestCase):
    def test_page_ranges(self):
        self.assertEqual(parse_page_spec("1-3,5", 10), [1,2,3,5])

    def test_bad_page_range(self):
        with self.assertRaises(ValueError): parse_page_spec("5-2", 10)
        with self.assertRaises(ValueError): parse_page_spec("11", 10)


class RealPdfIngestionTests(unittest.TestCase):
    def test_machines_three_page_ingestion_if_source_available(self):
        src=Path('/mnt/data/Machines Textbook.pdf')
        if not src.exists(): self.skipTest('Machines source not mounted')
        with tempfile.TemporaryDirectory() as td:
            out=Path(td)/'units.jsonl'
            r=ingest_pdf(src,out,page_spec='299-301',source_id='MACHINES-TEST')
            self.assertEqual(r['pdf_pages_selected'],[299,300,301])
            units=load_source_units(out)
            self.assertTrue(units)
            self.assertTrue(all(u.source_sha256==r['source_sha256'] for u in units))
            self.assertTrue(all(u.content for u in units))

if __name__=='__main__': unittest.main()

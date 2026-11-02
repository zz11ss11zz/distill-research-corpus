"""Offline regressions for the bundled literature-intake subskill."""
import csv
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from pypdf import PdfWriter

HELPERS = Path(__file__).resolve().parents[1] / 'skills/organize-literature/scripts'


class LiteratureOrganizationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / 'downloads'
        self.source.mkdir()
        self.pdf = self.source / 'download.pdf'
        writer = PdfWriter()
        writer.add_blank_page(width=300, height=300)
        writer.write(self.pdf)
        with self.pdf.open('ab') as f:
            f.write(b'\n%' + b'fixture-padding' * 1000)
        self.original = self.pdf.read_bytes()
        self.metadata = self.root / 'metadata.json'
        self.metadata.write_text(json.dumps({
            'title': 'Synthetic literature fixture', 'authors': ['Example Author'],
            'year': 2026, 'venue': 'Fixture Journal', 'doi': '10.1234/fixture',
        }), encoding='utf-8')
        self.overrides = self.root / 'overrides.json'
        self.overrides.write_text(json.dumps({'download.pdf': {
            'category': 'paper', 'venue': 'Fixture Journal', 'year': 2026,
            'title': 'Synthetic literature fixture', 'doi': '10.1234/fixture',
        }}), encoding='utf-8')

    def run_helper(self, name, args, expected=0):
        result = subprocess.run([sys.executable, str(HELPERS / name), *map(str, args)],
                                capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
        return result

    def test_organize_preview_apply_and_repeat(self):
        output = self.root / 'organized'
        args = ['--source', self.source, '--output', output,
                '--overrides', self.overrides, '--no-crossref']
        self.run_helper('organize_academic_pdfs.py', args)
        self.assertFalse(output.exists())
        self.run_helper('organize_academic_pdfs.py', [*args, '--apply'])
        target = output / 'paper/Fixture Journal - 2026 - Synthetic literature fixture.pdf'
        self.assertEqual(target.read_bytes(), self.original)
        self.assertEqual(self.pdf.read_bytes(), self.original)
        self.run_helper('organize_academic_pdfs.py', [*args, '--apply'])
        self.assertEqual(len(list(output.rglob('*.pdf'))), 1)

    def test_registration_preview_catalog_and_duplicate(self):
        project = self.root / 'project'
        project.mkdir()
        args = ['--root', project, '--metadata', self.metadata, '--pdf', self.pdf]
        self.run_helper('ingest_literature.py', args)
        self.assertEqual(list(project.iterdir()), [])
        result = self.run_helper('ingest_literature.py', [*args, '--apply'])
        plan = json.loads(result.stdout)
        self.assertEqual(plan['id'], 'R001')
        target = project / plan['pdf']['target']
        self.assertEqual(hashlib.sha256(target.read_bytes()).hexdigest(),
                         hashlib.sha256(self.original).hexdigest())
        with (project / 'literature/library.csv').open(encoding='utf-8-sig', newline='') as f:
            rows = list(csv.DictReader(f))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['doi'], '10.1234/fixture')
        self.run_helper('ingest_literature.py', [*args, '--apply'], expected=3)
        self.assertEqual(self.pdf.read_bytes(), self.original)

    def test_filename_conflict_preserves_existing_bytes(self):
        output = self.root / 'organized'
        target = output / 'paper/Fixture Journal - 2026 - Synthetic literature fixture.pdf'
        target.parent.mkdir(parents=True)
        target.write_bytes(b'existing different edition')
        self.run_helper('organize_academic_pdfs.py', [
            '--source', self.source, '--output', output, '--overrides', self.overrides,
            '--no-crossref', '--apply'], expected=2)
        self.assertEqual(target.read_bytes(), b'existing different edition')
        self.assertFalse((output / '_organization_manifest.json').exists())

    def test_default_layout_excel_and_incremental_retention(self):
        from openpyxl import load_workbook
        args = ['--root', self.root, '--overrides', self.overrides, '--no-crossref']
        self.run_helper('organize_academic_pdfs.py', args)
        output = self.root / 'literature'
        self.assertFalse(output.exists())
        self.run_helper('organize_academic_pdfs.py', [*args, '--apply'])
        self.assertTrue(all((output / category).is_dir() for category in ('paper', 'patent', 'thesis')))
        book = load_workbook(output / '文献总账.xlsx')
        self.assertEqual(book.active.max_row, 2)
        self.assertEqual(book.active['H2'].value, 'paper/Fixture Journal - 2026 - Synthetic literature fixture.pdf')
        self.assertEqual(book.active['I2'].value, hashlib.sha256(self.original).hexdigest())
        book.close()
        self.pdf.unlink()  # later run sees no source; preserve existing ledger
        result = self.run_helper('organize_academic_pdfs.py', [*args, '--apply'])
        self.assertEqual(json.loads(result.stdout)['scanned'], 0)
        book = load_workbook(output / '文献总账.xlsx')
        self.assertEqual(book.active.max_row, 2)
        book.close()

    def test_thesis_and_patent_filenames(self):
        for category, metadata, relative in [
            ('thesis', {'school': 'Example University', 'year': 2026, 'title': 'Fixture thesis'},
             'thesis/Example University - 2026 - Fixture thesis.pdf'),
            ('patent', {'patent_number': 'CN123456789A', 'year': 2026},
             'patent/CN123456789A - 2026.pdf'),
        ]:
            with self.subTest(category=category):
                self.overrides.write_text(json.dumps({'download.pdf': {'category': category, **metadata}}), encoding='utf-8')
                output = self.root / category
                self.run_helper('organize_academic_pdfs.py', [
                    '--source', self.source, '--output', output, '--overrides', self.overrides,
                    '--no-crossref', '--apply'])
                self.assertEqual((output / relative).read_bytes(), self.original)


if __name__ == '__main__':
    unittest.main()

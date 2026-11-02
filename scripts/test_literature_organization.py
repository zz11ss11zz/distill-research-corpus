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
        book = load_workbook(output / 'literature-ledger.xlsx')
        self.assertEqual(book.active.max_row, 2)
        self.assertEqual(book.active['H2'].value, 'paper/Fixture Journal - 2026 - Synthetic literature fixture.pdf')
        self.assertEqual(book.active['I2'].value, hashlib.sha256(self.original).hexdigest())
        book.close()
        (output / "literature-ledger.xlsx").rename(output / "文献总账.xlsx")
        self.pdf.unlink()  # exercise legacy-ledger migration without source files
        result = self.run_helper('organize_academic_pdfs.py', [*args, '--apply'])
        self.assertEqual(json.loads(result.stdout)['scanned'], 0)
        book = load_workbook(output / 'literature-ledger.xlsx')
        self.assertEqual(book.active.max_row, 2)
        book.close()

    def test_si_files_preserve_formats_main_and_incremental_names(self):
        import zipfile
        from openpyxl import Workbook, load_workbook
        (self.source / 'SI-info.pdf').write_bytes(self.original)  # even identical bytes must not replace main
        (self.source / 'SI-info-copy.pdf').write_bytes(self.original)
        book = Workbook()
        book.active.append(['fixture', 1])
        book.save(self.source / 'SI-data.xlsx')
        book.close()
        with zipfile.ZipFile(self.source / 'SI-package.zip', 'w') as archive:
            archive.writestr('fixture.txt', 'synthetic attachment')
        metadata = {'category': 'paper', 'venue': 'Fixture Journal', 'year': 2026,
                    'title': 'Synthetic literature fixture', 'doi': '10.1234/fixture'}
        overrides = {p.name: metadata for p in self.source.iterdir()}
        self.overrides.write_text(json.dumps(overrides), encoding='utf-8')
        output = self.root / 'literature'
        args = ['--source', self.source, '--output', output, '--overrides', self.overrides, '--no-crossref', '--apply']
        result = self.run_helper('organize_academic_pdfs.py', args)
        self.assertEqual(json.loads(result.stdout)['planned_unique'], 4)
        names = {p.name for p in (output / 'paper').iterdir()}
        self.assertIn('Fixture Journal - 2026 - Synthetic literature fixture.pdf', names)
        self.assertEqual(len([n for n in names if n.startswith('SI - ')]), 3)
        self.assertTrue(any(n.endswith('01.xlsx') for n in names))
        self.assertTrue(any(n.endswith('02.pdf') for n in names))
        self.assertTrue(any(n.endswith('03.zip') for n in names))
        book = load_workbook(output / 'literature-ledger.xlsx')
        si_rows = [row for row in book.active.values if row[10] == '补充材料']
        self.assertEqual(len(si_rows), 3)
        self.assertTrue(all(row[11] == 'paper/Fixture Journal - 2026 - Synthetic literature fixture.pdf' for row in si_rows))
        book.close()
        (self.source / 'SI-z-extra.csv').write_text('fixture,2\n', encoding='utf-8')
        overrides['SI-z-extra.csv'] = metadata
        self.overrides.write_text(json.dumps(overrides), encoding='utf-8')
        self.run_helper('organize_academic_pdfs.py', args)
        updated = {p.name for p in (output / 'paper').iterdir()}
        self.assertTrue(names <= updated)
        self.assertTrue(any(n.endswith('04.csv') for n in updated))

    def test_unlinked_si_remains_pending(self):
        (self.source / 'SI-unknown.zip').write_bytes(b'fixture attachment')
        output = self.root / 'literature'
        self.run_helper('organize_academic_pdfs.py', [
            '--source', self.source, '--output', output, '--overrides', self.overrides,
            '--no-crossref', '--apply'], expected=2)
        self.assertFalse(output.exists())

    def test_legacy_ten_column_ledger_is_upgraded(self):
        from openpyxl import Workbook, load_workbook
        output = self.root / 'literature'
        output.mkdir()
        book = Workbook()
        book.active.title = '文献总账'
        book.active.append(['分类', '标题', '作者', '年份', '期刊或学校', 'DOI', '专利号', '文件路径', 'SHA256', '原始路径'])
        book.active.append(['paper', 'Older fixture', '', 2025, 'Fixture', '', '', 'paper/old.pdf', 'old-hash', 'old-source'])
        book.save(output / 'literature-ledger.xlsx')
        book.close()
        self.run_helper('organize_academic_pdfs.py', [
            '--source', self.source, '--output', output, '--overrides', self.overrides, '--no-crossref', '--apply'])
        book = load_workbook(output / 'literature-ledger.xlsx')
        self.assertEqual(book.active.max_column, 12)
        self.assertEqual(book.active.max_row, 3)
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

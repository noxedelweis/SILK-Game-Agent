"""Prevent shipping ZIP files that older SILK installations reject."""
import io
import stat
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'desktop'))
from updater import safe_extract

class ReleaseZipCompatibilityTests(unittest.TestCase):
    def test_real_release_matches_installed_updater_validation(self):
        base=Path(__file__).resolve().parents[1]
        version=(base/'release/version.txt').read_text(encoding='ascii').strip()
        release=base/'dist'/f'SILK_Game_Agent_v{version}.zip'
        with zipfile.ZipFile(release) as archive:
            self.assertTrue(archive.namelist())
            self.assertIsNone(archive.testzip())
            for member in archive.infolist():
                mode=member.external_attr>>16
                self.assertTrue(stat.S_ISREG(mode) or (member.is_dir() and stat.S_ISDIR(mode)),member.filename)
        with tempfile.TemporaryDirectory() as folder:
            path=safe_extract(release,Path(folder),f'SILK_Game_Agent_v{version}')
            self.assertTrue((path/'start_without_ai.bat').is_file())
            self.assertTrue((path/'knowledge_cli.py').is_file())

    def test_reject_permission_only_zip_reproduces_old_failure(self):
        base=Path(__file__).resolve().parents[1]
        version=(base/'release/version.txt').read_text(encoding='ascii').strip()
        with tempfile.TemporaryDirectory() as folder:
            archive=Path(folder)/'bad.zip'
            with zipfile.ZipFile(archive,'w') as z:
                entry=zipfile.ZipInfo(f'SILK_Game_Agent_v{version}/start_without_ai.bat')
                entry.create_system=3
                entry.external_attr=0o600<<16
                z.writestr(entry,b'echo hello')
            with self.assertRaisesRegex(ValueError,'Ссылки и специальные'):
                safe_extract(archive,Path(folder),f'SILK_Game_Agent_v{version}')

if __name__=='__main__':unittest.main()

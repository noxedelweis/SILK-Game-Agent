import stat
import tempfile
import unittest
import zipfile
from pathlib import Path
from safe_zip_packager import rebuild


class SafeReleasePackageTests(unittest.TestCase):
    def test_bad_0600_permissions_become_regular_file(self):
        with tempfile.TemporaryDirectory() as dirname:
            folder=Path(dirname)
            inputzip=folder/'bad.zip'
            with zipfile.ZipFile(inputzip,'w') as z:
                for name in ('start_without_ai.bat','knowledge_cli.py'):
                    x=zipfile.ZipInfo('SILK_Game_Agent_v0.5.1/'+name)
                    x.create_system=3
                    x.external_attr=0o600<<16
                    z.writestr(x,b'untouched bytes')
            target=folder/'fixed.zip'
            rebuild(inputzip,target,'SILK_Game_Agent_v0.5.1','SILK_Game_Agent_v0.5.2')
            with zipfile.ZipFile(target) as z:
                self.assertEqual(len(z.infolist()),2)
                self.assertTrue(all(stat.S_ISREG(i.external_attr>>16) for i in z.infolist()))
                self.assertEqual(z.read('SILK_Game_Agent_v0.5.2/start_without_ai.bat'),b'untouched bytes')

    def test_refuses_links_and_traversal(self):
        for name,mode in [('SILK_Game_Agent_v0.5.1/evil',stat.S_IFLNK|0o777),
                          ('SILK_Game_Agent_v0.5.1/../evil',stat.S_IFREG|0o644)]:
            with self.subTest(name=name),tempfile.TemporaryDirectory() as dirname:
                folder=Path(dirname)
                with zipfile.ZipFile(folder/'bad.zip','w') as z:
                    info=zipfile.ZipInfo(name)
                    info.create_system=3
                    info.external_attr=mode<<16
                    z.writestr(info,b'evil')
                with self.assertRaises(ValueError):
                    rebuild(folder/'bad.zip',folder/'fixed.zip','SILK_Game_Agent_v0.5.1','SILK_Game_Agent_v0.5.2')

if __name__=='__main__':unittest.main()

import io
import json
import hashlib
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'desktop'))
from host_update import valid_pe_file, find_host_release, download_host
from host_update_helper import swap_host


def fake_pe(payload=b'payload'):
    data=bytearray(b'\0'*2048)
    data[:2]=b'MZ'
    data[0x3c:0x40]=(128).to_bytes(4,'little')
    data[128:134]=b'PE\0\0\x64\x86'
    data[500:500+len(payload)]=payload
    return bytes(data)


class FauxResp(io.BytesIO):
    def __enter__(self): return self
    def __exit__(self,*a): self.close()


class Client:
    def __init__(self, release, data): self.release=release;self.data=data; self.opener=self
    def latest(self): return {'version':(0,4,5)}
    def _request(self,url): return url
    def open(self,request, timeout=15):
        return FauxResp(json.dumps(self.release).encode('utf-8') if '/api.github.com/' in request else self.data)


class HostUpdateTests(unittest.TestCase):
    def test_reject_bad_pe(self):
        with tempfile.TemporaryDirectory() as t:
            f=Path(t)/'x.exe';f.write_bytes(b'suspicious')
            with self.assertRaises(ValueError): valid_pe_file(f)
    def test_git_release_asset_and_sha(self):
        data=fake_pe()
        sha=hashlib.sha256(data).hexdigest()
        asset={'name':'SILK_Game_Agent.exe','size':len(data),'digest':'sha256:'+sha,
               'browser_download_url':'https://github.com/noxedelweis/SILK-Game-Agent/releases/download/v0.4.5/SILK_Game_Agent.exe','state':'uploaded'}
        client=Client({'tag_name':'v0.4.5','assets':[asset]},data)
        version=find_host_release(client=client)
        with tempfile.TemporaryDirectory() as t:
            path=download_host(version,Path(t),client=client)
            self.assertEqual(path.read_bytes(),data)
            self.assertEqual(download_host(version,Path(t),client=client),path)
        self.assertEqual(version['sha256'],sha)
    def test_no_binary_is_agent_only_release(self):
        client=Client({'tag_name':'v0.4.5','assets':[]},b'')
        self.assertIsNone(find_host_release(client=client))
    def test_bad_digest_rejected(self):
        asset={'name':'SILK_Game_Agent.exe','size':2048,'digest':'bogus',
            'browser_download_url':'https://github.com/noxedelweis/SILK-Game-Agent/releases/download/v0.4.5/SILK_Game_Agent.exe'}
        with self.assertRaises(ValueError): find_host_release(client=Client({'tag_name':'v0.4.5','assets':[asset]},b''))
    def test_success_swap_keeps_backup(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);target=root/'SILK_Game_Agent.exe';target.write_bytes(fake_pe(b'OLD'))
            staged=root/'incoming.exe';staged.write_bytes(fake_pe(b'NEW'))
            old=target.read_bytes();new=staged.read_bytes()
            called=[]
            result=swap_host(target,staged,hashlib.sha256(new).hexdigest(),root,launcher=lambda x: called.append(x) or object())
            self.assertEqual(result['status'],'launched')
            self.assertEqual(target.read_bytes(),new)
            self.assertEqual((root/'_system'/'host_backups'/'previous_host.exe').read_bytes(),old)
            self.assertEqual(len(called),1)
            self.assertTrue(os.path.samefile(called[0],target))
    def test_failure_rolls_back(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);target=root/'SILK_Game_Agent.exe';target.write_bytes(fake_pe(b'OLD'))
            staged=root/'incoming.exe';staged.write_bytes(fake_pe(b'NEW'))
            old=target.read_bytes()
            with self.assertRaises(OSError):
                swap_host(target,staged,hashlib.sha256(staged.read_bytes()).hexdigest(),root,
                          launcher=lambda x: (_ for _ in ()).throw(OSError('exec failed')))
            self.assertEqual(target.read_bytes(),old)
    def test_hash_mismatch_does_not_mutate(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);target=root/'SILK_Game_Agent.exe';target.write_bytes(fake_pe(b'OLD'))
            staged=root/'incoming.exe';staged.write_bytes(fake_pe(b'NEW'))
            with self.assertRaises(ValueError): swap_host(target,staged,'1'*64,root)
            self.assertTrue(target.exists())
    def test_windows_locked_file_exhaustion_never_replaces(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);target=root/'SILK_Game_Agent.exe';target.write_bytes(fake_pe(b'OLD'))
            staged=root/'incoming.exe';staged.write_bytes(fake_pe(b'NEW'))
            old=target.read_bytes()
            with mock.patch('host_update_helper.os.replace',side_effect=PermissionError('Windows locked')):
                with self.assertRaises(PermissionError):
                    swap_host(target,staged,hashlib.sha256(staged.read_bytes()).hexdigest(),root,
                              launcher=lambda x: object(),sleep=lambda x:None,attempts=2)
            self.assertEqual(target.read_bytes(),old)

if __name__=='__main__':unittest.main()

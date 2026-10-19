import gzip
import io
from pathlib import Path
import sys
import tarfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import install_uart_swap_data as install


class Tests(unittest.TestCase):
    def test_exact_delta_reconstruction_and_no_hardware(self):
        before=b'base-image';after=b'next-image'
        delta=dict(base_sha256=install.sha(before),target_sha256=install.sha(after),bytes=len(before))
        difference=bytes(a^b for a,b in zip(before,after))
        with patch.object(install,'BASE_SHA',install.sha(before)):
            self.assertEqual(install.apply_delta(before,gzip.compress(difference),delta),after)
            for bad in (difference[:-1],difference+b'\0',b'\xff'*len(before)):
                with self.assertRaises(ValueError):
                    install.apply_delta(before,gzip.compress(bad),delta)
            with self.assertRaises(ValueError):
                install.apply_delta(b'other-base',gzip.compress(difference),delta)

    def test_archive_rejects_paths_links_duplicates_and_large_members(self):
        for names in (['../escape'],['/absolute'],['a\\b'],['same','same']):
            raw=io.BytesIO()
            with tarfile.open(fileobj=raw,mode='w') as output:
                for name in names:output.addfile(tarfile.TarInfo(name),io.BytesIO(b''))
            with tarfile.open(fileobj=io.BytesIO(raw.getvalue()),mode='r') as source:
                with self.assertRaises(ValueError):install.checked_members(source)
        for kind in (tarfile.SYMTYPE,tarfile.LNKTYPE,tarfile.DIRTYPE):
            raw=io.BytesIO()
            with tarfile.open(fileobj=raw,mode='w') as output:
                m=tarfile.TarInfo('item');m.type=kind;m.linkname='target';output.addfile(m)
            with tarfile.open(fileobj=io.BytesIO(raw.getvalue()),mode='r') as source:
                with self.assertRaises(ValueError):install.checked_members(source)
        fake=type('Archive',(),{'getmembers':lambda self:[type('Member',(),{'name':'large','size':16000001})()]})()
        with self.assertRaises(ValueError):install.checked_members(fake)


if __name__=='__main__':unittest.main()

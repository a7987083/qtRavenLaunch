"""Python 3.14 synthetic archive tests for B-mode generator."""
import marshal
from pathlib import Path
import sys
import tempfile
import unittest
import zlib

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from cn_generator_core import (COOKIE, ENTRY, MAGIC, BOOTSTRAP_SOURCE,
                               read_carchive, decode_script, generate, sha256)


def fixture():
    code = compile('import ichalaunch\nfrom ichalaunch.app import main\nmain()\n',
                   'run.py', 'exec')
    raw = marshal.dumps(code)
    payload = zlib.compress(raw)
    name = b'run\x00'
    toc = ENTRY.pack(ENTRY.size + len(name), 0, len(payload), len(raw), 1, b's') + name
    cookie = COOKIE.pack(MAGIC, len(payload) + len(toc) + COOKIE.size,
                         len(payload), len(toc), 314,
                         b'python314.dll'.ljust(64, b'\x00'))
    return b'MZ' + b'\0' * 32 + payload + toc + cookie


class GeneratorTests(unittest.TestCase):
    def test_core_repack_and_embedded_original_code(self):
        with tempfile.TemporaryDirectory() as tmp:
            src, dst = Path(tmp) / 'launcher.exe', Path(tmp) / 'cn.exe'
            binary = fixture()
            src.write_bytes(binary)
            output = generate(src, dst)
            self.assertTrue(output['static_verified'])
            self.assertEqual(src.read_bytes(), binary)
            self.assertNotEqual(sha256(dst.read_bytes()), sha256(binary))
            _prefix, _footer, entries = read_carchive(dst.read_bytes())
            script = decode_script(entries[0])
            self.assertEqual(script.co_filename, '<raven-cn-bootstrap>')
            original = [c for c in script.co_consts if hasattr(c, 'co_code')]
            self.assertTrue(any('ichalaunch' in c.co_names for c in original))

    def test_source_never_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / 'launcher.exe'
            src.write_bytes(fixture())
            with self.assertRaisesRegex(ValueError, 'overwrite'):
                generate(src, src)

    def test_existing_output_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            src, dst = Path(tmp) / 'launcher.exe', Path(tmp) / 'cn.exe'
            src.write_bytes(fixture())
            dst.write_bytes(b'keep')
            with self.assertRaises(FileExistsError):
                generate(src, dst)
            self.assertEqual(dst.read_bytes(), b'keep')

    def test_invalid_exe_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / 'launcher.exe'
            src.write_bytes(b'wrong')
            with self.assertRaises(ValueError):
                generate(src, Path(tmp) / 'cn.exe')


if __name__ == '__main__':
    unittest.main()

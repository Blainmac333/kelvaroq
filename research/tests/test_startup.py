"""End-to-end probes using PE bytes authored for this repository."""

import hashlib
import json
import os
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from unicorn import UC_ARCH_X86, UC_MODE_64, UC_PROT_READ, UC_PROT_WRITE, Uc
from unicorn.x86_const import UC_X86_REG_R8, UC_X86_REG_RCX, UC_X86_REG_RDX

from kelvaroq_reference.crt import fill_memory
from kelvaroq_reference.memory import GuestFault

ROOT = Path(__file__).resolve().parents[2]
CLI = Path(os.environ.get("KELVAROQ_BIN", ROOT / "target" / "release" / "kelvaroq.exe"))
BASE = 0x140000000


def fixture(with_import=False, executable=True):
    """One code section, optionally importing a deliberately unknown symbol."""
    image = bytearray(0x600)
    image[:2] = b"MZ"
    struct.pack_into("<I", image, 0x3C, 0x80)
    image[0x80:0x84] = b"PE\0\0"
    struct.pack_into("<HHIIIHH", image, 0x84, 0x8664, 1, 0, 0, 0, 0xF0, 0x22)
    opt = 0x98
    struct.pack_into("<H", image, opt, 0x20B)
    struct.pack_into("<II", image, opt + 16, 0x1000, 0x1000)
    struct.pack_into("<QII", image, opt + 24, BASE, 0x1000, 0x200)
    struct.pack_into("<II", image, opt + 56, 0x2000, 0x200)
    struct.pack_into("<H", image, opt + 68, 3)
    struct.pack_into("<I", image, opt + 108, 16)
    flags = 0x60000020 if executable else 0x40000040
    struct.pack_into(
        "<8sIIIIIIHHI",
        image,
        opt + 0xF0,
        b".text",
        0x400,
        0x1000,
        0x400,
        0x200,
        0,
        0,
        0,
        0,
        flags,
    )
    code = bytes.fromhex("b8 2a 00 00 00 c3")  # return 42
    if with_import:
        # sub rsp, 40; call [rip + displacement]; add rsp, 40; ret
        code = (
            bytes.fromhex("48 83 ec 28 ff 15")
            + struct.pack("<i", 0x11A0 - 0x100A)
            + bytes.fromhex("48 83 c4 28 c3")
        )
        struct.pack_into("<II", image, opt + 120, 0x1100, 40)
        struct.pack_into("<IIIII", image, 0x300, 0x1190, 0, 0, 0x1160, 0x11A0)
        image[0x360:0x36A] = b"probe.dll\0"
        struct.pack_into("<Q", image, 0x390, 0x11B0)
        struct.pack_into("<Q", image, 0x3A0, 0x11B0)
        image[0x3B2:0x3BF] = b"UnknownProbe\0"
    image[0x200 : 0x200 + len(code)] = code
    return bytes(image)


class StartupTests(unittest.TestCase):
    def invoke(self, contents, command, *args):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "fixture.exe"
            path.write_bytes(contents)
            return subprocess.run(
                [str(CLI), command, str(path), *args],
                capture_output=True,
                check=False,
                text=True,
                encoding="utf8",
                timeout=15,
            )

    def test_inspect_identifies_fixture(self):
        sample = fixture()
        result = self.invoke(sample, "inspect", "--json")
        self.assertEqual(result.returncode, 0, result.stderr)
        plan = json.loads(result.stdout)
        self.assertEqual(plan["sha256"], hashlib.sha256(sample).hexdigest())
        self.assertEqual((plan["base"], plan["entry"]), (BASE, 0x1000))

    def test_real_instructions_return_42(self):
        result = self.invoke(fixture(), "boot", "--python", sys.executable)
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual((report["stage"], report["result"]), ("returned", 42))

    def test_unknown_import_identifies_guest_caller(self):
        result = self.invoke(
            fixture(with_import=True), "boot", "--python", sys.executable
        )
        self.assertEqual(result.returncode, 2, result.stderr)
        stop = json.loads(result.stdout)["stop"]
        self.assertEqual(
            stop,
            {
                "reason": "unimplemented import",
                "symbol": "UnknownProbe",
                "dll": "probe.dll",
                "return_rva": "0x100a",
            },
        )

    def test_entry_requires_executable_section(self):
        result = self.invoke(fixture(executable=False), "inspect")
        self.assertEqual(result.returncode, 1)
        self.assertIn("outside executable sections", result.stderr)


class MemoryTests(unittest.TestCase):
    def setUp(self):
        self.cpu = Uc(UC_ARCH_X86, UC_MODE_64)
        self.cpu.mem_map(0x1000, 4096, UC_PROT_READ | UC_PROT_WRITE)
        self.cpu.mem_map(0x2000, 4096, UC_PROT_READ)
        self.cpu.reg_write(UC_X86_REG_RCX, 0x1FFC)
        self.cpu.reg_write(UC_X86_REG_RDX, 0xABCD)

    def test_fill_returns_destination(self):
        self.cpu.reg_write(UC_X86_REG_R8, 4)
        self.assertEqual(fill_memory(self.cpu), 0x1FFC)
        self.assertEqual(bytes(self.cpu.mem_read(0x1FFC, 4)), bytes([0xCD]) * 4)

    def test_denied_span_preserves_first_page(self):
        self.cpu.reg_write(UC_X86_REG_R8, 5)
        with self.assertRaises(GuestFault):
            fill_memory(self.cpu)
        self.assertEqual(bytes(self.cpu.mem_read(0x1FFC, 4)), bytes(4))


if __name__ == "__main__":
    unittest.main()

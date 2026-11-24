"""Test the vector data path with distinctive upper lanes and unaligned memory."""

import unittest

from unicorn import (
    UC_ARCH_X86,
    UC_MODE_64,
    UC_PROT_EXEC,
    UC_PROT_READ,
    UC_PROT_WRITE,
    Uc,
)
from unicorn.x86_const import (
    UC_X86_REG_RCX,
    UC_X86_REG_YMM0,
    UC_X86_REG_YMM1,
    UC_X86_REG_YMM15,
)

from kelvaroq_reference.memory import GuestFault
from kelvaroq_reference.vector import VectorMoves


class VectorTests(unittest.TestCase):
    def setUp(self):
        self.cpu = Uc(UC_ARCH_X86, UC_MODE_64)
        self.cpu.mem_map(0x1000, 4096, UC_PROT_READ | UC_PROT_EXEC)
        self.cpu.mem_map(0x2000, 4096, UC_PROT_READ | UC_PROT_WRITE)
        self.moves = VectorMoves()
        self.payload = bytes(range(32))
        self.number = int.from_bytes(self.payload, "little")
        self.cpu.reg_write(UC_X86_REG_YMM0, self.number)

    def execute(self, code):
        self.cpu.mem_write(0x1000, bytes.fromhex(code))
        return self.moves.execute(self.cpu, 0x1000)

    def test_unaligned_store_and_rip_relative_load(self):
        self.cpu.reg_write(UC_X86_REG_RCX, 0x2001)
        self.assertEqual(self.execute("c5 fc 11 01"), 0x1004)
        self.assertEqual(bytes(self.cpu.mem_read(0x2001, 32)), self.payload)
        self.assertEqual(self.execute("c5 fc 10 0d f9 0f 00 00"), 0x1008)
        self.assertEqual(self.cpu.reg_read(UC_X86_REG_YMM1), self.number)

    def test_vex_128_move_zeroes_upper_half(self):
        self.cpu.reg_write(UC_X86_REG_YMM1, (1 << 256) - 1)
        self.execute("c5 f8 10 c8")
        self.assertEqual(
            self.cpu.reg_read(UC_X86_REG_YMM1), self.number & ((1 << 128) - 1)
        )

    def test_integer_move_preserves_every_bit(self):
        self.cpu.reg_write(UC_X86_REG_RCX, 0x2011)
        self.execute("c5 fe 7f 01")
        self.execute("c5 fe 6f 09")
        self.assertEqual(self.cpu.reg_read(UC_X86_REG_YMM1), self.number)

    def test_zero_upper_preserves_low_lanes(self):
        self.cpu.reg_write(UC_X86_REG_YMM15, self.number)
        self.execute("c5 f8 77")
        for reg in (UC_X86_REG_YMM0, UC_X86_REG_YMM15):
            self.assertEqual(self.cpu.reg_read(reg), self.number & ((1 << 128) - 1))

    def test_store_honours_page_permissions(self):
        self.cpu.reg_write(UC_X86_REG_RCX, 0x1100)
        with self.assertRaises(GuestFault):
            self.execute("c5 fc 11 01")
        self.assertEqual(bytes(self.cpu.mem_read(0x1100, 32)), bytes(32))

    def test_unknown_instruction_stays_with_cpu(self):
        self.assertIsNone(self.execute("0f 0b"))

"""Reservations exclude address ranges without making guest pages accessible."""

import struct
import unittest

from unicorn import UC_ARCH_X86, UC_MODE_64, Uc, UcError
from unicorn.x86_const import (
    UC_X86_REG_R8,
    UC_X86_REG_R9,
    UC_X86_REG_RCX,
    UC_X86_REG_RDX,
    UC_X86_REG_RSP,
)

from kelvaroq_reference.graphics_memory import (
    ADDRESS_LIMIT,
    FIRST_HIGH_ADDRESS,
    GRANULARITY,
    GraphicsMemory,
)
from kelvaroq_reference.memory import GuestFault


class GraphicsMemoryTests(unittest.TestCase):
    def setUp(self):
        self.cpu = Uc(UC_ARCH_X86, UC_MODE_64)
        self.cpu.mem_map(0x1000, 0x1000)
        self.cpu.reg_write(UC_X86_REG_RCX, 0x1000)
        self.cpu.reg_write(UC_X86_REG_RSP, 0x1100)
        self.cpu.mem_write(0x1128, struct.pack("<I", 4))
        self.input = struct.pack("<IIII", 0, 4, 0, 0xAABBCCDD)
        self.cpu.mem_write(0x1000, self.input)
        self.memory = GraphicsMemory()
        self.assertEqual(self.memory.configure(self.cpu), 0)

    def allocate(self, size, base=0, kind=0x20402000):
        self.cpu.reg_write(UC_X86_REG_RCX, base)
        self.cpu.reg_write(UC_X86_REG_RDX, size)
        self.cpu.reg_write(UC_X86_REG_R8, kind)
        self.cpu.reg_write(UC_X86_REG_R9, 0x21)
        return self.memory.allocate(self.cpu)

    def test_configuration_writes_only_its_two_outputs(self):
        self.assertEqual(bytes(self.cpu.mem_read(0x1000, 16)), self.input)
        self.assertEqual(
            struct.unpack("<QQ", self.cpu.mem_read(0x1010, 16)),
            (GRANULARITY, ADDRESS_LIMIT - 1),
        )

    def test_large_sparse_reservations_skip_existing_pages(self):
        self.cpu.mem_map(FIRST_HIGH_ADDRESS + GRANULARITY, 4096)
        mappings = list(self.cpu.mem_regions())
        size = 24 << 30
        first = self.allocate(size)
        second = self.allocate(size)
        self.assertEqual(first, FIRST_HIGH_ADDRESS + 2 * GRANULARITY)
        self.assertEqual(second, first + size)
        self.assertEqual(list(self.cpu.mem_regions()), mappings)
        with self.assertRaises(UcError):
            self.cpu.mem_read(first, 1)

    def test_collision_and_overflow_leave_existing_allocations_intact(self):
        first = self.allocate(1)
        self.assertEqual(self.allocate(1, first), 0)
        self.assertEqual(self.allocate(2 * GRANULARITY, ADDRESS_LIMIT - GRANULARITY), 0)
        self.assertEqual(len(self.memory.reservations), 1)
        self.assertEqual(self.memory.reservations[0].size, GRANULARITY)

    def test_commit_cannot_succeed_as_a_reservation(self):
        with self.assertRaises(GuestFault):
            self.allocate(GRANULARITY, kind=0x20003000)
        self.assertEqual(self.memory.reservations, [])

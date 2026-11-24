"""Guest virtual addresses used by graphics reservations before page binding."""

import struct
from dataclasses import dataclass

from unicorn.x86_const import (
    UC_X86_REG_R8,
    UC_X86_REG_R9,
    UC_X86_REG_RCX,
    UC_X86_REG_RDX,
    UC_X86_REG_RSP,
)

from .memory import DWORD, GuestFault, read_guest, write_guest

GRANULARITY = 1 << 16
FIRST_HIGH_ADDRESS = 1 << 32
ADDRESS_LIMIT = 1 << 40
RESERVE = 0x2000
PAGES_64K = 0x20400000


@dataclass(frozen=True)
class Reservation:
    start: int
    size: int
    flags: int
    protection: int


def aligned(value):
    return (value + GRANULARITY - 1) & -GRANULARITY


class GraphicsMemory:
    def __init__(self):
        self.reservations = []
        self.table_pages = None

    def configure(self, cpu):
        address = cpu.reg_read(UC_X86_REG_RCX)
        if not address:
            return 0x80070057  # E_INVALIDARG
        flags, pages, preserved = struct.unpack("<III", read_guest(cpu, address, 12))
        if flags or preserved:
            raise GuestFault("unsupported graphics memory configuration")
        # Both ends are inclusive in the guest structure. Input fields stay intact.
        write_guest(
            cpu, address + 16, struct.pack("<QQ", GRANULARITY, ADDRESS_LIMIT - 1)
        )
        self.table_pages = pages
        return 0

    def allocate(self, cpu):
        requested = cpu.reg_read(UC_X86_REG_RCX)
        size = cpu.reg_read(UC_X86_REG_RDX)
        kind = cpu.reg_read(UC_X86_REG_R8) & 0xFFFFFFFF
        flags = cpu.reg_read(UC_X86_REG_R9)
        stack = cpu.reg_read(UC_X86_REG_RSP)
        protection = DWORD.unpack(read_guest(cpu, stack + 40, 4))[0]
        if kind != (PAGES_64K | RESERVE):
            raise GuestFault(f"unsupported XMem allocation kind {kind:#x}")
        if flags not in (0x21, 3):
            raise GuestFault(f"unsupported XMem reservation flags {flags:#x}")
        if self.table_pages is None:
            raise GuestFault("graphics aperture is not configured")
        return self.reserve(cpu, requested, size, flags, protection)

    def reserve(self, cpu, requested, size, flags, protection):
        # A reservation excludes addresses. Backing and access permissions are
        # established separately when the guest binds physical pages.
        size = aligned(size)
        candidate = requested or FIRST_HIGH_ADDRESS
        if not size or candidate < FIRST_HIGH_ADDRESS or candidate % GRANULARITY:
            return 0
        occupied = [(lo, hi + 1) for lo, hi, _ in cpu.mem_regions()]
        occupied.extend((r.start, r.start + r.size) for r in self.reservations)
        for start, end in sorted(occupied):
            if end <= candidate:
                continue
            if candidate + size <= start:
                break
            if requested:
                return 0
            candidate = aligned(end)
        if candidate + size > ADDRESS_LIMIT:
            return 0
        self.reservations.append(Reservation(candidate, size, flags, protection))
        return candidate

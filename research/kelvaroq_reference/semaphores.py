"""Private semaphore handles for the single-threaded CPU reference."""

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

MODIFY = 0x2
SYNCHRONIZE = 0x100000
WAIT_FAILED = 0xFFFFFFFF


@dataclass
class Semaphore:
    count: int
    maximum: int
    access: int


class Semaphores:
    def __init__(self):
        self.handles = {}
        self.next_handle = 0x20000

    def invoke(self, cpu, name):
        """Return (ABI result, last-error update); None leaves last error unchanged."""
        handle = cpu.reg_read(UC_X86_REG_RCX)
        if name == "CreateSemaphoreExW":
            initial = cpu.reg_read(UC_X86_REG_RDX) & 0xFFFFFFFF
            maximum = cpu.reg_read(UC_X86_REG_R8) & 0xFFFFFFFF
            if handle or cpu.reg_read(UC_X86_REG_R9):
                raise GuestFault("named or explicitly secured semaphore is unsupported")
            stack = cpu.reg_read(UC_X86_REG_RSP)
            flags, access = struct.unpack("<I4xI", read_guest(cpu, stack + 40, 12))
            if flags or not 0 < maximum <= 0x7FFFFFFF or initial > maximum:
                return 0, 87
            if access & ~0x1F0003:
                raise GuestFault("unsupported semaphore access rights")
            handle = self.next_handle
            self.next_handle += 1
            self.handles[handle] = Semaphore(initial, maximum, access)
            return handle, None
        if name not in (
            "ReleaseSemaphore",
            "WaitForSingleObject",
            "WaitForSingleObjectEx",
            "CloseHandle",
        ):
            return NotImplemented, None
        semaphore = self.handles.get(handle)
        if semaphore is None:
            return (WAIT_FAILED if name.startswith("Wait") else 0), 6
        if name == "CloseHandle":
            del self.handles[handle]
            return 1, None
        if name == "ReleaseSemaphore":
            if not semaphore.access & MODIFY:
                return 0, 5
            amount = cpu.reg_read(UC_X86_REG_RDX) & 0xFFFFFFFF
            if not 0 < amount <= 0x7FFFFFFF:
                return 0, 87
            if amount > semaphore.maximum - semaphore.count:
                return 0, 298  # ERROR_TOO_MANY_POSTS
            previous = cpu.reg_read(UC_X86_REG_R8)
            if previous:
                write_guest(cpu, previous, DWORD.pack(semaphore.count))
            semaphore.count += amount
            return 1, None
        if not semaphore.access & SYNCHRONIZE:
            return WAIT_FAILED, 5
        if name.endswith("Ex") and cpu.reg_read(UC_X86_REG_R8) & 0xFFFFFFFF:
            raise GuestFault("alertable wait requires guest APC delivery")
        if semaphore.count:
            semaphore.count -= 1
            return 0, None
        if cpu.reg_read(UC_X86_REG_RDX) & 0xFFFFFFFF:
            raise GuestFault("blocking wait requires guest scheduling")
        return 258, None

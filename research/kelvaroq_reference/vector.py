"""VEX-encoded unaligned vector moves and upper-lane clearing on x64."""

from capstone import CS_ARCH_X86, CS_MODE_64, Cs
from capstone.x86_const import (
    X86_INS_VMOVDQU,
    X86_INS_VMOVUPS,
    X86_INS_VXORPS,
    X86_INS_VZEROUPPER,
    X86_OP_MEM,
    X86_OP_REG,
    X86_REG_RIP,
)
from unicorn import UC_PROT_EXEC, x86_const

from .memory import read_guest, write_guest


def ymm(index):
    return getattr(x86_const, f"UC_X86_REG_YMM{index}")


def vector_register(insn, operand):
    name = insn.reg_name(operand.reg)
    if operand.type != X86_OP_REG or not name.startswith(("xmm", "ymm")):
        raise ValueError("expected an x86 vector register")
    return ymm(int(name[3:]))


def effective_address(cpu, insn, mem):
    def read(reg):
        if not reg:
            return 0
        if reg == X86_REG_RIP:
            return insn.address + insn.size
        name = insn.reg_name(reg).upper()
        return cpu.reg_read(getattr(x86_const, f"UC_X86_REG_{name}"))

    address = read(mem.base) + read(mem.index) * mem.scale + mem.disp
    segment = insn.reg_name(mem.segment) if mem.segment else None
    if segment in ("fs", "gs"):
        address += cpu.reg_read(
            getattr(x86_const, f"UC_X86_REG_{segment.upper()}_BASE")
        )
    return address & ((1 << 64) - 1)


class VectorMoves:
    def __init__(self):
        self.decoder = Cs(CS_ARCH_X86, CS_MODE_64)
        self.decoder.detail = True

    def execute(self, cpu, pc):
        # Decode only accessible instruction bytes, including across page boundaries.
        code = bytearray()
        for low, high, flags in sorted(cpu.mem_regions()):
            current = pc + len(code)
            if high < current:
                continue
            if low > current or not flags & UC_PROT_EXEC:
                break
            code.extend(cpu.mem_read(current, min(15 - len(code), high - current + 1)))
            if len(code) == 15:
                break
        insn = next(self.decoder.disasm(bytes(code), pc, count=1), None)
        if not insn or insn.id not in (
            X86_INS_VMOVUPS,
            X86_INS_VMOVDQU,
            X86_INS_VZEROUPPER,
            X86_INS_VXORPS,
        ):
            return None
        # Capstone also names EVEX instructions VMOVUPS. Masked and 512-bit
        # forms have different semantics and must stay with another implementation.
        if insn.encoding.modrm_offset and insn.addr_size != 8:
            return None
        if not code or code[0] not in (0xC4, 0xC5):
            return None
        if insn.id == X86_INS_VZEROUPPER:
            lower = (1 << 128) - 1
            for index in range(16):
                reg = ymm(index)
                cpu.reg_write(reg, cpu.reg_read(reg) & lower)
        elif insn.id == X86_INS_VXORPS:
            destination, left, right = insn.operands
            size = destination.size
            first = cpu.reg_read(vector_register(insn, left))
            if right.type == X86_OP_MEM:
                second = int.from_bytes(
                    read_guest(cpu, effective_address(cpu, insn, right.mem), size),
                    "little",
                )
            else:
                second = cpu.reg_read(vector_register(insn, right))
            cpu.reg_write(
                vector_register(insn, destination),
                (first ^ second) & ((1 << (size * 8)) - 1),
            )
        else:
            self.move(cpu, insn)
        return pc + insn.size

    @staticmethod
    def move(cpu, insn):
        destination, source = insn.operands
        size = source.size
        if size not in (16, 32) or destination.size != size:
            raise ValueError("unexpected VEX operand size")
        if source.type == X86_OP_MEM:
            value = read_guest(cpu, effective_address(cpu, insn, source.mem), size)
        else:
            number = cpu.reg_read(vector_register(insn, source))
            value = number.to_bytes(32, "little")[:size]
        if destination.type == X86_OP_MEM:
            write_guest(cpu, effective_address(cpu, insn, destination.mem), value)
        else:
            # VEX.128 clears the upper half of its destination.
            cpu.reg_write(
                vector_register(insn, destination), int.from_bytes(value, "little")
            )

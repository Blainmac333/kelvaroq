"""Verified VEX vector operations for the startup reference."""

import operator
import struct

from capstone import CS_ARCH_X86, CS_MODE_64, Cs
from capstone import x86_const as instructions
from capstone.x86_const import (
    X86_INS_VBROADCASTF128,
    X86_INS_VBROADCASTI128,
    X86_INS_VBROADCASTSD,
    X86_INS_VBROADCASTSS,
    X86_INS_VMOVAPD,
    X86_INS_VMOVAPS,
    X86_INS_VMOVDQA,
    X86_INS_VMOVDQU,
    X86_INS_VMOVUPD,
    X86_INS_VMOVUPS,
    X86_INS_VPADDQ,
    X86_INS_VPBROADCASTB,
    X86_INS_VPBROADCASTD,
    X86_INS_VPBROADCASTQ,
    X86_INS_VPBROADCASTW,
    X86_INS_VPERMQ,
    X86_INS_VXORPS,
    X86_INS_VZEROUPPER,
    X86_OP_IMM,
    X86_OP_MEM,
    X86_OP_REG,
    X86_REG_RIP,
)
from unicorn import UC_PROT_EXEC, x86_const

from . import fma
from .memory import GuestFault, read_guest, write_guest
from .vector_extra import (
    FLOAT128_OPS,
    INT128_OPS,
    LANE_SELECT_OPS,
    SCALAR_FMA_OPS,
    integer_lanes,
    packed_float,
    scalar_fma,
    select_lanes,
)

FMA_OPS = {
    getattr(instructions, f"X86_INS_V{family}{order}PS"): op
    for op, (family, order) in enumerate(
        (family, order)
        for family in ("FMADD", "FMSUB", "FNMADD", "FNMSUB")
        for order in (132, 213, 231)
    )
}

ALIGNED_MOVES = (X86_INS_VMOVAPS, X86_INS_VMOVAPD, X86_INS_VMOVDQA)

BROADCAST_BYTES = {
    X86_INS_VBROADCASTF128: 16,
    X86_INS_VBROADCASTI128: 16,
    X86_INS_VBROADCASTSS: 4,
    X86_INS_VBROADCASTSD: 8,
    X86_INS_VPBROADCASTB: 1,
    X86_INS_VPBROADCASTW: 2,
    X86_INS_VPBROADCASTD: 4,
    X86_INS_VPBROADCASTQ: 8,
}


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


def operand_bytes(cpu, insn, operand, width):
    if operand.type == X86_OP_MEM:
        return read_guest(cpu, effective_address(cpu, insn, operand.mem), width)
    number = cpu.reg_read(vector_register(insn, operand))
    return number.to_bytes(32, "little")[:width]


def packed_qwords(cpu, insn):
    destination, *sources = insn.operands
    width = destination.size
    if insn.id == X86_INS_VPERMQ:
        lanes = struct.unpack("<4Q", operand_bytes(cpu, insn, sources[0], 32))
        control = sources[1].imm
        result = struct.pack(
            "<4Q", *(lanes[(control >> shift) & 3] for shift in (0, 2, 4, 6))
        )
    else:
        layout = struct.Struct("<" + "Q" * (width // 8))
        left, right = (
            layout.unpack(operand_bytes(cpu, insn, source, width)) for source in sources
        )
        arithmetic = (
            operator.sub if insn.id == instructions.X86_INS_VPSUBQ else operator.add
        )
        result = layout.pack(
            *(arithmetic(a, b) & 0xFFFFFFFFFFFFFFFF for a, b in zip(left, right))
        )
    cpu.reg_write(vector_register(insn, destination), int.from_bytes(result, "little"))


def execute_packed128(cpu, insn):
    destination, first, *rest = insn.operands
    if destination.size != 16:
        return False
    if insn.id == instructions.X86_INS_VPSRAD and rest[-1].type != X86_OP_IMM:
        return False
    first_value = operand_bytes(cpu, insn, first, 16)
    control = rest.pop().imm if rest and rest[-1].type == X86_OP_IMM else 0
    second_value = operand_bytes(cpu, insn, rest[0], 16) if rest else bytes(16)
    if insn.id in FLOAT128_OPS:
        mxcsr = cpu.reg_read(x86_const.UC_X86_REG_MXCSR)
        value, mxcsr = packed_float(
            FLOAT128_OPS[insn.id], first_value, second_value, mxcsr
        )
        cpu.reg_write(x86_const.UC_X86_REG_MXCSR, mxcsr)
    else:
        value = integer_lanes(insn.id, first_value, second_value, control)
    cpu.reg_write(vector_register(insn, destination), int.from_bytes(value, "little"))
    return True


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
            X86_INS_VMOVUPD,
            *ALIGNED_MOVES,
            X86_INS_VMOVDQU,
            X86_INS_VZEROUPPER,
            X86_INS_VXORPS,
            X86_INS_VPADDQ,
            instructions.X86_INS_VPSUBQ,
            instructions.X86_INS_VPCMPEQD,
            instructions.X86_INS_VPMOVSXBQ,
            *BROADCAST_BYTES,
            *FMA_OPS,
            *SCALAR_FMA_OPS,
            *LANE_SELECT_OPS,
            *FLOAT128_OPS,
            *INT128_OPS,
            X86_INS_VPERMQ,
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
        elif insn.id in FMA_OPS or insn.id in SCALAR_FMA_OPS:
            destination, second, third = insn.operands
            width = destination.size
            control = cpu.reg_read(x86_const.UC_X86_REG_MXCSR)
            if insn.id in SCALAR_FMA_OPS:
                value, control = scalar_fma(
                    SCALAR_FMA_OPS[insn.id],
                    operand_bytes(cpu, insn, destination, 16),
                    operand_bytes(cpu, insn, second, 4),
                    operand_bytes(cpu, insn, third, 4),
                    control,
                )
            else:
                operands = (
                    operand_bytes(cpu, insn, operand, width)
                    for operand in (destination, second, third)
                )
                value, control = fma.evaluate(FMA_OPS[insn.id], *operands, control)
            cpu.reg_write(
                vector_register(insn, destination), int.from_bytes(value, "little")
            )
            cpu.reg_write(x86_const.UC_X86_REG_MXCSR, control)
        elif insn.id in FLOAT128_OPS or insn.id in INT128_OPS:
            if not execute_packed128(cpu, insn):
                return None
        elif insn.id in LANE_SELECT_OPS:
            destination, first, second, control = insn.operands
            value = select_lanes(
                insn.id,
                operand_bytes(cpu, insn, first, first.size),
                operand_bytes(cpu, insn, second, second.size),
                operand_bytes(cpu, insn, control, control.size)
                if control.type == X86_OP_REG
                else control.imm,
            )
            cpu.reg_write(
                vector_register(insn, destination), int.from_bytes(value, "little")
            )
        elif insn.id in BROADCAST_BYTES:
            destination, source = insn.operands
            element_width = BROADCAST_BYTES[insn.id]
            element = operand_bytes(cpu, insn, source, element_width)
            value = element * (destination.size // element_width)
            cpu.reg_write(
                vector_register(insn, destination), int.from_bytes(value, "little")
            )
        elif insn.id == instructions.X86_INS_VPMOVSXBQ:
            destination, source = insn.operands
            count = destination.size // 8
            lanes = struct.unpack(f"<{count}b", operand_bytes(cpu, insn, source, count))
            value = struct.pack(f"<{count}q", *lanes)
            cpu.reg_write(
                vector_register(insn, destination), int.from_bytes(value, "little")
            )
        elif insn.id == instructions.X86_INS_VPCMPEQD:
            destination, first, second = insn.operands
            width = destination.size
            left = operand_bytes(cpu, insn, first, width)
            right = operand_bytes(cpu, insn, second, width)
            value = b"".join(
                b"\xff" * 4 if left[i : i + 4] == right[i : i + 4] else bytes(4)
                for i in range(0, width, 4)
            )
            cpu.reg_write(
                vector_register(insn, destination), int.from_bytes(value, "little")
            )
        elif insn.id in (X86_INS_VPADDQ, instructions.X86_INS_VPSUBQ, X86_INS_VPERMQ):
            packed_qwords(cpu, insn)
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
        if insn.id in ALIGNED_MOVES:
            for operand in (destination, source):
                if (
                    operand.type == X86_OP_MEM
                    and effective_address(cpu, insn, operand.mem) % size
                ):
                    raise GuestFault(
                        f"misaligned {insn.mnemonic} operand, requires {size} bytes"
                    )
        value = operand_bytes(cpu, insn, source, size)
        if destination.type == X86_OP_MEM:
            write_guest(cpu, effective_address(cpu, insn, destination.mem), value)
        else:
            # VEX.128 clears the upper half of its destination.
            cpu.reg_write(
                vector_register(insn, destination), int.from_bytes(value, "little")
            )

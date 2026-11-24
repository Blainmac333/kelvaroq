"""Bridge a fixed set of guest FMA operations to the local x64 arithmetic library."""

import ctypes
import os
from functools import cache

from .memory import GuestFault


class FmaBlock(ctypes.Structure):
    _fields_ = [(name, ctypes.c_uint32 * 4) for name in ("dst", "second", "third")] + [
        ("mxcsr", ctypes.c_uint32)
    ]


@cache
def native_library(path):
    if not path:
        raise GuestFault(
            "native arithmetic requires the library from the Kelvaroq build"
        )
    try:
        return ctypes.CDLL(path)
    except OSError as error:
        raise GuestFault("cannot load the Kelvaroq arithmetic library") from error


@cache
def native_fma(path):
    function = getattr(native_library(path), "kelvaroq_fma_ps", None)
    if function is None:
        raise GuestFault("FMA requires the x64 arithmetic backend")
    function.argtypes = [ctypes.c_uint32, ctypes.POINTER(FmaBlock)]
    function.restype = ctypes.c_uint32
    return function


def evaluate(op, dst, second, third, mxcsr):
    function = native_fma(os.environ.get("KELVAROQ_SIMD_LIB"))
    output = bytearray()
    for start in range(0, len(dst), 16):
        raw = b"".join(v[start : start + 16] for v in (dst, second, third))
        block = FmaBlock.from_buffer_copy(raw + mxcsr.to_bytes(4, "little"))
        status = function(op, ctypes.byref(block))
        if status == 2:
            raise GuestFault("host CPU does not support AVX/FMA")
        if status == 3:
            raise GuestFault(
                "guest FMA requires unsupported MXCSR or unmasked exceptions"
            )
        if status:
            raise GuestFault("invalid native FMA operation")
        output.extend(bytes(block.dst))
        mxcsr = block.mxcsr
    return bytes(output), mxcsr


class MathF32(ctypes.Structure):
    _fields_ = [
        ("value", ctypes.c_uint32),
        ("mxcsr", ctypes.c_uint32),
        ("error", ctypes.c_int32),
    ]


@cache
def native_tanf(path):
    function = getattr(native_library(path), "kelvaroq_tanf", None)
    if function is None:
        raise GuestFault("tanf requires the x64 Windows math backend")
    function.argtypes = [ctypes.POINTER(MathF32)]
    function.restype = ctypes.c_uint32
    return function


def tanf(value, mxcsr):
    state = MathF32(value, mxcsr, 0)
    if native_tanf(os.environ.get("KELVAROQ_SIMD_LIB"))(ctypes.byref(state)):
        raise GuestFault("guest tanf requires unsupported MXCSR or unmasked exceptions")
    return state

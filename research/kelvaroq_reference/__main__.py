"""Run the startup plan produced by the Rust PE inspector."""

import json
import sys
from pathlib import Path

from unicorn import UcError
from unicorn.x86_const import UC_X86_REG_RAX

from .cpu import Startup


def main():
    plan = json.load(sys.stdin)
    console = sys.argv[2]
    vm = Startup(plan, Path(sys.argv[1]).read_bytes(), console)
    completed = []
    stages = [("tls-attach", a) for a in plan["callbacks"]]
    stages.append(("entry", plan["base"] + plan["entry"]))
    for stage, address in stages:
        if not vm.call(address, stage == "tls-attach"):
            print(
                json.dumps(
                    {
                        "stage": stage,
                        "console": console,
                        "completed": completed,
                        "stop": vm.blocker,
                        "calls": vm.calls,
                        "virtual_reservations": [
                            vars(r) for r in vm.graphics_memory.reservations
                        ],
                        "initializers_entered": len(vm.initializers),
                        "last_initializer": vm.initializers[-1:],
                    }
                )
            )
            return 2
        completed.append({"stage": stage, "rva": hex(address - plan["base"])})
    print(
        json.dumps(
            {
                "stage": "returned",
                "console": console,
                "completed": completed,
                "result": vm.cpu.reg_read(UC_X86_REG_RAX),
                "calls": vm.calls,
            }
        )
    )
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, UcError, RecursionError) as error:
        print(f"reference CPU: {error}", file=sys.stderr)
        sys.exit(1)

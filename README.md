# cpuinfo
Tool to emulate /proc/cpuinfo in non Linux OS

## Keeping flags in sync with Linux

`cpuinfo_flags.h` is generated from the kernel source (`arch/x86/include/asm/cpufeatures.h` + `arch/x86/kernel/cpu/scattered.c`).

- Only CPUID-derived flags are included (leaves `0x1,0x7,0xD,0x80000001,0x80000008,0xC0000001` etc + scattered).
- Linux-synthesized flags (`constant_tsc, rep_good, nopl, xtopology, ...` in `CPUID_LNX_*` words) are omitted.
- Hidden raw flags (`osxsave, amd_ibpb, spec_ctrl, ...` where `x86_cap_flags[i]==NULL`) are kept — the tool reports raw CPUID bits, unlike `/proc/cpuinfo` which hides them.

Regenerate after a kernel update:

    make regen          # uses KERNEL_SRC=/path/to/linux
    # or
    python3 scripts/gen_cpuinfo_flags.py --kernel /path/to/linux --output cpuinfo_flags.h

`make` will auto-regenerate when kernel headers change.

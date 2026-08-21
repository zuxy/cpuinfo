#!/usr/bin/env python3

# Copyright (C) 2026 Zuxy Meng
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

"""
Generate cpuinfo_flags.h from Linux kernel source.

Keeps the little cpuinfo tool in sync with kernel CPUID flags.

- Parses arch/x86/include/asm/cpufeatures.h for X86_FEATURE_* definitions
- Parses arch/x86/kernel/cpu/scattered.c for scattered CPUID bits
- Filters to CPUID-derived flags only (ignores Linux-synthesized flags)
- Keeps raw flags even when kernel hides them (e.g., osxsave has no quoted name)

Usage:
    python3 scripts/gen_cpuinfo_flags.py [--kernel DIR] [--output FILE]
    default kernel: /path/to/linux
    default output: cpuinfo_flags.h

Generated header defines:
    struct cpuid_flag { unsigned leaf, subleaf, reg, bit; const char *name; };
    static const struct cpuid_flag cpuid_flags[] = { ... };
where reg: 0=EAX, 1=EBX, 2=ECX, 3=EDX
"""
import argparse, re, pathlib, sys

# Mapping of direct words to CPUID leaf info (from cpufeatures.h comments + common.c)
# word -> (leaf, subleaf, reg_name)
WORD_TO_CPUID = {
    0:  (0x00000001, 0, "EDX"),
    1:  (0x80000001, 0, "EDX"),
    2:  (0x80860001, 0, "EDX"),  # Transmeta
    4:  (0x00000001, 0, "ECX"),
    5:  (0xC0000001, 0, "EDX"),
    6:  (0x80000001, 0, "ECX"),
    9:  (0x00000007, 0, "EBX"),
    10: (0x0000000D, 1, "EAX"),
    12: (0x00000007, 1, "EAX"),
    13: (0x80000008, 0, "EBX"),
    14: (0x00000006, 0, "EAX"),
    15: (0x8000000A, 0, "EDX"),
    16: (0x00000007, 0, "ECX"),
    18: (0x00000007, 0, "EDX"),  # note subleaf 0, EDX
    19: (0x8000001F, 0, "EAX"),
    20: (0x80000021, 0, "EAX"),
    # words 3,7,8,11,17,21 are synthetic/LNX; handled via scattered table
}

REG_MAP = {"EAX":0, "EBX":1, "ECX":2, "EDX":3,
           "CPUID_EAX":0, "CPUID_EBX":1, "CPUID_ECX":2, "CPUID_EDX":3}

def parse_cpufeatures(feat_path):
    features = []  # (word, bit, macro, display_name, kernel_desc, line)
    pat = re.compile(r'#define\s+(X86_FEATURE_\w+)\s+\(\s*(\d+)\*32\+\s*(\d+)\)')
    with open(feat_path) as f:
        for line in f:
            m = pat.search(line)
            if not m:
                continue
            macro, w, b = m.groups()
            w=int(w); b=int(b)
            # Extract comment text inside /* ... */
            cmt = re.search(r'/\*\s*(.*?)\s*\*/', line)
            comment = cmt.group(1).strip() if cmt else ""
            q = re.search(r'"([^"]+)"', comment)
            disp = q.group(1).lower() if q else None
            if q:
                # Description is what follows the quoted string
                after = comment[q.end():].strip()
                # If no description after quoted (e.g. /* "sse" */), fallback to quoted text
                desc = after if after else q.group(1)
            else:
                desc = comment
            # fallback name = macro suffix lowercased
            fallback = macro[len("X86_FEATURE_"):].lower()
            # Clean desc for C comment (avoid */)
            desc = desc.replace("*/", "* /")
            if not desc:
                desc = fallback
            features.append((w,b,macro,disp, fallback, desc, line.strip()))
    return features

def parse_scattered(sc_path):
    text = pathlib.Path(sc_path).read_text()
    # { X86_FEATURE_xxx,  CPUID_REG, bit, level, sub_leaf }
    pat = re.compile(r'\{\s*(X86_FEATURE_\w+)\s*,\s*(CPUID_\w+)\s*,\s*(\d+)\s*,\s*(0x[0-9a-fA-F]+)\s*,\s*(\d+)\s*\}')
    entries = []
    for m in pat.finditer(text):
        feat, reg, bit, level, sub = m.groups()
        entries.append((feat, reg, int(bit), int(level,16), int(sub)))
    return entries

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--kernel", default="/path/to/linux")
    ap.add_argument("--output", default="cpuinfo_flags.h")
    args = ap.parse_args()
    kroot = pathlib.Path(args.kernel)
    feat_path = kroot / "arch/x86/include/asm/cpufeatures.h"
    sc_path = kroot / "arch/x86/kernel/cpu/scattered.c"
    if not feat_path.exists():
        print(f"missing {feat_path}", file=sys.stderr); sys.exit(1)
    if not sc_path.exists():
        print(f"missing {sc_path}", file=sys.stderr); sys.exit(1)

    features = parse_cpufeatures(feat_path)
    # index by macro
    by_macro = {macro: (w,b,macro,disp,fb,desc) for w,b,macro,disp,fb,desc,_ in features}
    scattered = parse_scattered(sc_path)
    # Build flag list
    # tuple: (leaf, subleaf, reg, cpuid_bit, name, macro, word, linux_bit, kernel_desc)
    # linux_bit is the bit within the kernel feature word (word*32+linux_bit),
    # used to match /proc/cpuinfo ordering (x86_cap_flags order).
    flags = []
    seen = set()  # (leaf,subleaf,reg,bit)

    # 1. Direct CPUID words
    for w,b,macro,disp,fb,desc,_ in features:
        if w not in WORD_TO_CPUID:
            continue
        leaf, sub, reg_name = WORD_TO_CPUID[w]
        reg = REG_MAP[reg_name]
        # name: quoted display if exists, else fallback lowercased macro
        name = disp if disp else fb
        key = (leaf, sub, reg, b)
        if key in seen:
            continue
        seen.add(key)
        # For direct words, CPUID bit == Linux feature bit
        flags.append((leaf, sub, reg, b, name, macro, w, b, desc))

    # 2. Scattered CPUID bits (even if word is synthetic, they are still CPUID)
    # For each scattered entry, lookup its display name
    for feat, reg_name, bit, level, sub in scattered:
        if feat not in by_macro:
            # feature may have been removed/renamed, skip with warning
            print(f"warning: scattered feature {feat} not in cpufeatures.h", file=sys.stderr)
            continue
        w,b2,macro,disp,fb,desc = by_macro[feat]
        # Note: scattered CPUID bit (in table) differs from X86_FEATURE word/bit
        # (Linux word placement). We use the CPUID bit, so no mismatch check.
        name = disp if disp else fb
        reg = REG_MAP[reg_name]
        leaf = level
        key = (leaf, sub, reg, bit)
        if key in seen:
            # Might duplicate with direct if a scattered feature also appears as direct word?
            # But direct words and scattered words are distinct, so shouldn't happen.
            # If duplicate, skip.
            continue
        seen.add(key)
        flags.append((leaf, sub, reg, bit, name, macro, w, b2, desc))

    # Sort to match /proc/cpuinfo order: by kernel feature number (word, linux_bit).
    # This puts legacy flags like fpu/pse first, newer flags like pni/ssse3 later,
    # exactly as x86_cap_flags[] is iterated in arch/x86/kernel/cpu/proc.c.
    flags.sort(key=lambda x: (x[6], x[7]))  # w, linux_bit

    # Also sort a second list for stable display order by kernel word/bit for comments?
    # We keep leaf order for efficient cpuid caching.

    out_path = pathlib.Path(args.output)
    # If output is relative and not absolute, make relative to cpuinfo dir
    if not out_path.is_absolute():
        # assume script is in scripts/, output default is cpuinfo_flags.h in parent
        base = pathlib.Path(__file__).parent.parent
        out_path = base / out_path
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with open(out_path, "w") as out:
        out.write("/* Generated by scripts/gen_cpuinfo_flags.py from Linux kernel source */\n")
        out.write(f"/* kernel: {kroot} */\n")
        out.write(f"/* Do not edit manually. Regenerate with: python3 scripts/gen_cpuinfo_flags.py --kernel {kroot} */\n")
        out.write("#pragma once\n\n")
        out.write("struct cpuid_flag {\n")
        out.write("    unsigned leaf;\n")
        out.write("    unsigned subleaf;\n")
        out.write("    unsigned reg; /* 0=EAX 1=EBX 2=ECX 3=EDX */\n")
        out.write("    unsigned bit;\n")
        out.write("    const char *name;\n")
        out.write("};\n\n")
        out.write(f"static const struct cpuid_flag cpuid_flags[] = {{\n")
        for leaf, sub, reg, bit, name, macro, w, _linux_bit, desc in flags:
            # Keep macro name plus kernel description, e.g. "X86_FEATURE_FPU Onboard FPU"
            out.write(f"    {{0x{leaf:08x}, {sub}, {reg}, {bit:2d}, \"{name}\"}}, /* {macro} {desc} */\n")
        out.write("};\n")
        out.write(f"static const unsigned cpuid_flags_count = {len(flags)};\n")
        # Also emit counts for info
        # Generate helper for availability check: we could also emit tables per leaf
        unique_leaves = sorted(set((f[0], f[1]) for f in flags))
        out.write(f"\n/* {len(flags)} CPUID-derived flags, {len(unique_leaves)} unique leaves */\n")
    print(f"Generated {out_path} with {len(flags)} flags ({len(unique_leaves)} leaves)")
    # For diagnostics, print breakdown
    # Count per leaf
    from collections import Counter
    cnt = Counter(f[0] for f in flags)
    for leaf in sorted(cnt):
        print(f" leaf 0x{leaf:08x}: {cnt[leaf]} flags")

if __name__ == "__main__":
    main()

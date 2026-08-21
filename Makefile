KERNEL_SRC ?= /path/to/linux
CC ?= gcc
CFLAGS ?= -O2 -Wall

all: cpuinfo

cpuinfo: cpuinfo.c cpuinfo_flags.h
	$(CC) $(CFLAGS) -o $@ cpuinfo.c

# Only regenerate when KERNEL_SRC exists; allow `make` to succeed on a
# fresh clone with the committed header when no kernel is present.
cpuinfo_flags.h: scripts/gen_cpuinfo_flags.py
	@if [ -f "$(KERNEL_SRC)/arch/x86/include/asm/cpufeatures.h" ]; then \
		python3 scripts/gen_cpuinfo_flags.py --kernel $(KERNEL_SRC) --output $@; \
	elif [ -f $@ ]; then \
		echo "KERNEL_SRC not found at $(KERNEL_SRC), using existing $@"; \
	else \
		echo "error: KERNEL_SRC not found at $(KERNEL_SRC) and $@ missing" >&2; exit 1; \
	fi

regen:
	@if [ ! -f "$(KERNEL_SRC)/arch/x86/include/asm/cpufeatures.h" ]; then echo "error: KERNEL_SRC not found at $(KERNEL_SRC)" >&2; exit 1; fi
	python3 scripts/gen_cpuinfo_flags.py --kernel $(KERNEL_SRC) --output cpuinfo_flags.h

clean:
	rm -f cpuinfo cpuinfo_flags.h

.PHONY: all regen clean

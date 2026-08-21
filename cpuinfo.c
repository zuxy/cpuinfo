/*
 * small utility to extract CPU information
 * Used by configure to set CPU optimization levels on some operating
 * systems where /proc/cpuinfo is non-existent or unreliable.
 *
 * This file is part of MPlayer.
 *
 * MPlayer is free software; you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation; either version 2 of the License, or
 * (at your option) any later version.
 *
 * MPlayer is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU General Public License for more details.
 *
 * You should have received a copy of the GNU General Public License along
 * with MPlayer; if not, write to the Free Software Foundation, Inc.,
 * 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.
 */

#include <stdio.h>
#include <time.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

#ifdef __MINGW32__
#define MISSING_USLEEP
#include <windows.h>
#define sleep(t) Sleep(1000*t);
#endif

#ifdef M_UNIX
typedef long long int64_t;
#define MISSING_USLEEP
#else
#include <inttypes.h>
#endif

#define CPUID_FEATURE_DEF(bit, desc, description) \
    { bit, desc }

#include "cpuinfo_flags.h"

typedef struct cpuid_regs {
    unsigned int eax;
    unsigned int ebx;
    unsigned int ecx;
    unsigned int edx;
} cpuid_regs_t;

static cpuid_regs_t __attribute__((const))
cpuid(int func, int sub)
{
    cpuid_regs_t regs;
    __asm__(
            "cpuid"
            : "=a" (regs.eax), "=b" (regs.ebx), "=c" (regs.ecx), "=d" (regs.edx)
            : "0" (func), "2" (sub));
    return regs;
}


static int64_t
rdtsc(void)
{
    uint32_t hi, lo;
    __asm__ volatile ("rdtsc" : "=a"(lo), "=d"(hi) : );
    return (uint64_t) hi << 32 | lo;
}

static const char*
brandname(int i)
{
    static const char* brandmap[] = {
        NULL,
        "Intel(R) Celeron(R) processor",
        "Intel(R) Pentium(R) III processor",
        "Intel(R) Pentium(R) III Xeon(tm) processor",
        "Intel(R) Pentium(R) III processor",
        NULL,
        "Mobile Intel(R) Pentium(R) III processor-M",
        "Mobile Intel(R) Celeron(R) processor"
    };

    if (i >= sizeof(brandmap))
        return NULL;
    else
        return brandmap[i];
}

static void
store32(char *d, unsigned int v)
{
#if 0
    d[0] =  v        & 0xff;
    d[1] = (v >>  8) & 0xff;
    d[2] = (v >> 16) & 0xff;
    d[3] = (v >> 24) & 0xff;
#else
    *(unsigned *)d = v;
#endif
}


int
main(void)
{
    cpuid_regs_t regs, regs_ext, regs_via;
    char idstr[13];
    unsigned max_cpuid;
    unsigned max_ext_cpuid;
    unsigned max_via_cpuid;
    const char *model_name = NULL;
    int i;
    char processor_name[49];

    regs = cpuid(0, 0);
    max_cpuid = regs.eax;
    /* printf("%d CPUID function codes\n", max_cpuid+1); */

    store32(idstr+0, regs.ebx);
    store32(idstr+4, regs.edx);
    store32(idstr+8, regs.ecx);
    idstr[12] = 0;
    printf("vendor_id\t: %s\n", idstr);

    regs_ext = cpuid((1<<31) + 0, 0);
    max_ext_cpuid = regs_ext.eax;
    if (max_ext_cpuid >= (1<<31) + 1) {
        if (max_ext_cpuid >= (1<<31) + 4) {
            for (i = 2; i <= 4; i++) {
                regs_ext = cpuid((1<<31) + i, 0);
                store32(processor_name + (i-2)*16, regs_ext.eax);
                store32(processor_name + (i-2)*16 + 4, regs_ext.ebx);
                store32(processor_name + (i-2)*16 + 8, regs_ext.ecx);
                store32(processor_name + (i-2)*16 + 12, regs_ext.edx);
            }
            processor_name[48] = 0;
            model_name = processor_name;
            while (*model_name == ' ') {
                model_name++;
            }
        }
    }

    regs_via = cpuid(0xc0000000, 0);
    max_via_cpuid = regs_via.eax;

    if (max_cpuid >= 1) {
        unsigned int family, model, stepping;
        unsigned max_transmeta = 0;
        {
            cpuid_regs_t rtrans = cpuid(0x80860000, 0);
            if ((rtrans.eax & 0xffff0000) == 0x80860000)
                max_transmeta = rtrans.eax;
        }

        regs = cpuid(1, 0);
        family = (regs.eax >> 8) & 0xf;
        model = (regs.eax >> 4) & 0xf;
        stepping = regs.eax & 0xf;

        if (family == 0xf || family == 6)
            model += ((regs.eax >> 16) & 0xf) << 4;
        if (family == 0xf)
            family += (regs.eax >> 20) & 0xff;

        printf("cpu family\t: %d\n"
               "model\t\t: %d\n"
               "stepping\t: %d\n"
               "cpuid level\t: %d\n",
               family,
               model,
               stepping,
               max_cpuid);

        if (strstr(idstr, "Intel") && !model_name) {
            if (family == 6 && model == 0xb && stepping == 1)
                model_name = "Intel (R) Celeron (R) processor";
            else
                model_name = brandname(regs.ebx & 0xf);
        }

        printf("flags\t\t:");
        {
            const char *printed[512];
            int printed_count = 0;
            for (i = 0; i < (int)cpuid_flags_count; i++) {
                const struct cpuid_flag *f = &cpuid_flags[i];
                int available = 0;
                if (f->leaf >= 0xC0000000) {
                    available = max_via_cpuid >= f->leaf;
                } else if (f->leaf >= 0x80860000) {
                    available = max_transmeta >= f->leaf;
                } else if (f->leaf >= 0x80000000) {
                    available = max_ext_cpuid >= f->leaf;
                } else {
                    available = max_cpuid >= f->leaf;
                }
                if (!available) continue;
                if (f->subleaf > 0) {
                    if (f->leaf == 0x7 || f->leaf == 0xF || f->leaf == 0x10 || f->leaf == 0x12 || f->leaf == 0x14) {
                        cpuid_regs_t r0 = cpuid(f->leaf, 0);
                        if (f->subleaf > r0.eax) continue;
                    }
                }
                cpuid_regs_t r = cpuid(f->leaf, f->subleaf);
                unsigned val;
                switch (f->reg) {
                    case 0: val = r.eax; break;
                    case 1: val = r.ebx; break;
                    case 2: val = r.ecx; break;
                    case 3: val = r.edx; break;
                    default: val = 0; break;
                }
                if (val & (1u << f->bit)) {
                    int dup = 0;
                    for (int j = 0; j < printed_count; j++) if (strcmp(printed[j], f->name)==0) {dup=1; break;}
                    if (dup) continue;
                    printed[printed_count++] = f->name;
                    printf(" %s", f->name);
                }
            }
        }
        /* k6_mtrr is supported by some AMD K6-2/K6-III CPUs but
           it is not indicated by a CPUID feature bit, so we
           have to check the family, model and stepping instead. */
        if (strstr(idstr, "AMD") &&
            family == 5 &&
            (model >= 9 || (model == 8 && stepping >= 8)))
            printf(" %s", "k6_mtrr");
        /* similar for cyrix_arr. */
        if (strstr(idstr, "Cyrix") &&
            (family == 5 && (model < 4 || family == 6)))
            printf(" %s", "cyrix_arr");
        /* as well as centaur_mcr. */
        if (strstr(idstr, "Centaur") &&
            family == 5)
            printf(" %s", "centaur_mcr");

        printf("\n");

        if (regs.edx & (1 << 4)) {
            int64_t tsc_start, tsc_end;
            struct timespec ts_start, ts_end;
            int usec_delay;

            tsc_start = rdtsc();
            timespec_get(&ts_start, TIME_UTC);
#ifdef  MISSING_USLEEP
            sleep(1);
#else
            usleep(100000);
#endif
            tsc_end = rdtsc();
            timespec_get(&ts_end, TIME_UTC);

            usec_delay = 1000000 * (ts_end.tv_sec - ts_start.tv_sec)
                + (ts_end.tv_nsec - ts_start.tv_nsec) / 1000;

            printf("cpu MHz\t\t: %.3f\n",
                   (double)(tsc_end-tsc_start) / usec_delay);
        }
    }

    printf("model name\t: ");
    if (model_name)
        printf("%s\n", model_name);
    else
        printf("Unknown %s CPU\n", idstr);
}

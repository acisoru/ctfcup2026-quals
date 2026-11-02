#ifndef GHOSTVECTOR_H
#define GHOSTVECTOR_H

#include <stdint.h>
#include <sys/ioctl.h>

#define GV_DEVICE "/dev/ghostvector"
#define GV_PAGE_SIZE 4096UL
#define GV_MAP_ADDRESS ((void *)0x40000000UL)

struct gv_register_flag {
    uint64_t user_address;
};

struct gv_layout {
    uint64_t user_address;
    uint64_t masked_pte_pa;
    uint64_t masked_flag_pa;
};

#define GV_IOC_MAGIC 'G'
#define GV_REGISTER_FLAG _IOW(GV_IOC_MAGIC, 0x01, struct gv_register_flag)
#define GV_GET_LAYOUT _IOWR(GV_IOC_MAGIC, 0x02, struct gv_layout)

/* CTF-only raw XGhostVector instruction, exact guest-side encoding. */
static inline void gv_store8(uint64_t physical_address, uint8_t byte)
{
    register uint64_t a0 __asm__("a0") = physical_address;
    register uint64_t a1 __asm__("a1") = byte;

    __asm__ volatile("vsetivli zero, 1, e8, m1, ta, ma\n\t"
                     ".word 0x00b5700b"
                 : "+r"(a0), "+r"(a1)
                 :
                 : "memory");
}

#endif

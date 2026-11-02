// patch-forkit нейтрализует песочницу coolforkit-caps, чтобы RCE в
// kit-процессе давал настоящий код в контейнере, а не в chroot-jail.
//
// Патчим на немедленный возврат (mov $1,%eax; ret): Seccomp::lockdown
// (убивает kit на chroot), dropCaps, Landlock::lock, setAllowedPaths.
// Возврат 1 обязателен — при false lokit_main делает forcedExit; ключей
// конфига, отключающих эти вызовы, нет. Все адреса лежат в единственном
// исполнимом LOAD, где file offset == virtual address.
package main

import (
	"fmt"
	"os"
	"syscall"
	"unsafe"
)

type patch struct {
	offset int64
	name   string
}

var patches = []patch{
	{0x3f1e40, "Seccomp::lockdown"},
	{0x311110, "dropCaps"},
	{0x3e1ff0, "Landlock::lock"},
	{0x3e0060, "Landlock::setAllowedPaths"},
}

var retOne = []byte{0xb8, 0x01, 0x00, 0x00, 0x00, 0xc3}

// xattr security.capability из базового образа (20 байт, v2, permitted =
// cap_chown|cap_fowner|cap_sys_chroot). Ядро снимает файловые caps при
// первой записи в файл, а прочитать их в build-контейнере нельзя (BuildKit
// прячет xattr — getxattr даёт ENODATA), поэтому вписываем заново.
var baseFileCaps = []byte{
	0x01, 0x00, 0x00, 0x02,
	0x09, 0x00, 0x04, 0x00,
	0x00, 0x00, 0x00, 0x00,
	0x00, 0x00, 0x00, 0x00,
	0x00, 0x00, 0x00, 0x00,
}

const capXattr = "security.capability"

func setFileCaps(path string) error {
	name := []byte(capXattr + "\x00")
	pathPtr := uintptr(unsafe.Pointer(unsafe.StringData(path)))
	_, _, errno := syscall.Syscall6(
		syscall.SYS_LSETXATTR, pathPtr,
		uintptr(unsafe.Pointer(&name[0])), uintptr(unsafe.Pointer(&baseFileCaps[0])),
		uintptr(len(baseFileCaps)), 0, 0)
	if errno != 0 {
		return errno
	}
	return nil
}

func main() {
	if len(os.Args) != 2 {
		fmt.Fprintln(os.Stderr, "usage: patch-forkit <coolforkit-caps>")
		os.Exit(2)
	}
	path := os.Args[1]

	image, err := os.OpenFile(path, os.O_RDWR, 0)
	if err != nil {
		fmt.Fprintf(os.Stderr, "open %s: %v\n", path, err)
		os.Exit(1)
	}

	patched := 0
	for _, p := range patches {
		original := make([]byte, len(retOne))
		if _, err := image.ReadAt(original, p.offset); err != nil {
			fmt.Fprintf(os.Stderr, "%s: read at %#x: %v (не та версия бинаря?)\n", p.name, p.offset, err)
			os.Exit(1)
		}
		if string(original) == string(retOne) {
			fmt.Printf("%s: already patched\n", p.name)
			patched++
			continue
		}
		if _, err := image.WriteAt(retOne, p.offset); err != nil {
			fmt.Fprintf(os.Stderr, "%s: write at %#x: %v\n", p.name, p.offset, err)
			os.Exit(1)
		}
		fmt.Printf("%s: patched at %#x\n", p.name, p.offset)
		patched++
	}
	image.Close()

	if err := setFileCaps(path); err != nil {
		fmt.Fprintf(os.Stderr, "restore %s: %v\n", capXattr, err)
		os.Exit(1)
	}
	fmt.Printf("%s: restored (%d bytes)\n", capXattr, len(baseFileCaps))

	if patched != len(patches) {
		os.Exit(1)
	}
}

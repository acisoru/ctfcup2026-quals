package mobilelib

import (
	"crypto/rand"
	"encoding/base64"
	"fmt"
	"math/big"
	"os"
	"os/exec"
	"strings"
)

const salt byte = 0x5a
const blockSize = 16

var (
	marks = [][]byte{
		{0x39, 0x1f, 0x1a},
		{0x39, 0x1e, 0x0c},
	}
	noiseParts = [][]byte{
		{0x2a, 0x0a, 0x0e, 0xee, 0xfb, 0xc3},
		{0x28, 0x04, 0x09, 0xf9, 0xfb},
		{0x29, 0x0e, 0x1d, 0xe1, 0xfb, 0xcb},
		{0x2a, 0x19, 0x19, 0xeb, 0xed},
		{0x0a, 0x3c, 0x32},
		{0x6b, 0x58, 0x4f, 0xba},
		{0x1c, 0x07, 0x1d, 0xea},
		{0x16, 0x0e, 0x19, 0xf9},
		{0x08, 0x5b, 0x4c, 0xf9},
	}
	seps = []byte{0x05, 0x4f, 0x51, 0xac, 0xde}
)

func openBox(box []byte) string {
	out := make([]byte, len(box))
	for i, b := range box {
		out[i] = b ^ byte(int(salt)+i*17)
	}
	return string(out)
}

func prefix() string {
	return openBox(marks[0]) + openBox(marks[1])
}

func sep() string {
	return string('_')
}

func randomChar(charset string) (byte, error) {
	num, err := rand.Int(rand.Reader, big.NewInt(int64(len(charset))))
	if err != nil {
		return 0, err
	}
	return charset[num.Int64()], nil
}

func decoyContent() (string, error) {
	parts := make([]string, 0, 4)
	for i := 0; i < 4; i++ {
		idx, err := rand.Int(rand.Reader, big.NewInt(int64(len(noiseParts))))
		if err != nil {
			return "", err
		}
		parts = append(parts, openBox(noiseParts[idx.Int64()]))
	}

	separator, err := randomChar(openBox(seps))
	if err != nil {
		return "", err
	}
	return strings.Join(parts, string(separator)), nil
}

func wrap(content string) string {
	return fmt.Sprintf("%s{%s}", prefix(), content)
}

func decoyFlag() string {
	content, _ := decoyContent()
	return wrap(content)
}

func FF1() string {
	return decoyFlag()
}

func FF2() string {
	return decoyFlag()
}

func FF3() string {
	return decoyFlag()
}

func FF4() string {
	return decoyFlag()
}

func FF5() string {
	return decoyFlag()
}

func FF6() string {
	return decoyFlag()
}

func FF7() string {
	return decoyFlag()
}

func FF8() string {
	return decoyFlag()
}

func FF9() string {
	return decoyFlag()
}

func FF10() string {
	return decoyFlag()
}

func FF11() string {
	return decoyFlag()
}

func FF12() string {
	return decoyFlag()
}

func IsRootedEnvironment(fingerprint, model, product, tags string) bool {
	return hasSuBinary() ||
		strings.Contains(tags, "test-keys") ||
		propertyEquals("ro.debuggable", "1") ||
		propertyEquals("ro.secure", "0") ||
		looksLikeEmulator(fingerprint, model, product)
}

func VerifySealedParcel(parcelB64, ivB64, keyB64 string) bool {
	ciphertext, err := base64.StdEncoding.DecodeString(parcelB64)
	if err != nil {
		return false
	}
	iv, err := base64.StdEncoding.DecodeString(ivB64)
	if err != nil {
		return false
	}
	key, err := base64.StdEncoding.DecodeString(keyB64)
	if err != nil {
		return false
	}

	if len(iv) != blockSize || len(key) != blockSize || len(ciphertext) == 0 || len(ciphertext)%blockSize != 0 {
		return false
	}

	previous := append([]byte(nil), iv...)
	block := make([]byte, blockSize)
	last := make([]byte, blockSize)
	prefixBytes := []byte(prefix() + "{")
	prefixOK := true

	for offset := 0; offset < len(ciphertext); offset += blockSize {
		for i := 0; i < blockSize; i++ {
			block[i] = (ciphertext[offset+i] ^ key[i]) ^ previous[i]
		}
		if offset == 0 {
			for i := range prefixBytes {
				prefixOK = prefixOK && block[i] == prefixBytes[i]
			}
		}
		copy(last, block)
		copy(previous, ciphertext[offset:offset+blockSize])
		for i := range block {
			block[i] = 0
		}
	}

	padLen := int(last[blockSize-1])
	if padLen <= 0 || padLen > blockSize {
		return false
	}
	for i := blockSize - padLen; i < blockSize; i++ {
		if int(last[i]) != padLen {
			return false
		}
	}

	lastPlainIndex := blockSize - padLen - 1
	return prefixOK && lastPlainIndex >= 0 && last[lastPlainIndex] == '}'
}

func hasSuBinary() bool {
	paths := []string{
		"/system/bin/su",
		"/system/xbin/su",
		"/sbin/su",
		"/su/bin/su",
		"/data/adb/magisk",
		"/data/local/tmp/su",
	}
	for _, path := range paths {
		if _, err := os.Stat(path); err == nil {
			return true
		}
	}
	return exec.Command("which", "su").Run() == nil
}

func propertyEquals(name, expected string) bool {
	out, err := exec.Command("getprop", name).Output()
	if err != nil {
		return false
	}
	return strings.TrimSpace(string(out)) == expected
}

func looksLikeEmulator(fingerprint, model, product string) bool {
	values := []string{
		strings.ToLower(fingerprint),
		strings.ToLower(model),
		strings.ToLower(product),
	}
	needles := []string{"generic", "ranchu", "sdk_gphone", "emulator", "sdk"}
	for _, value := range values {
		for _, needle := range needles {
			if strings.Contains(value, needle) {
				return true
			}
		}
	}
	return false
}

func main() {}

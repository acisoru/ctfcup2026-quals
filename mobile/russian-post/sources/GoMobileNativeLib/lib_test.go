package mobilelib

import (
	"encoding/base64"
	"testing"
)

func TestFlagFormat(t *testing.T) {
	open := string([]byte{0x63, 0x74, 0x66, 0x63, 0x75, 0x70, 0x7b})
	close := string([]byte{0x7d})
	flags := map[string]string{
		"FF1":  FF1(),
		"FF2":  FF2(),
		"FF3":  FF3(),
		"FF4":  FF4(),
		"FF5":  FF5(),
		"FF6":  FF6(),
		"FF7":  FF7(),
		"FF8":  FF8(),
		"FF9":  FF9(),
		"FF10": FF10(),
		"FF11": FF11(),
		"FF12": FF12(),
	}
	for name, value := range flags {
		if len(value) <= len(open+close) || value[:len(open)] != open || value[len(value)-1:] != close {
			t.Fatalf("%s returned flag in wrong format: %q", name, value)
		}
	}
}

func TestNoNativeFlagSlot(t *testing.T) {
	backendFlag := string([]byte{
		0x63, 0x74, 0x66, 0x63, 0x75, 0x70, 0x7b,
		0x70, 0x34, 0x72, 0x63, 0x65, 0x6c, 0x5f,
		0x76, 0x31, 0x5f, 0x75, 0x6e, 0x6c, 0x30,
		0x63, 0x6b, 0x33, 0x64, 0x7d,
	})
	flags := []string{FF1(), FF2(), FF3(), FF4(), FF5(), FF6(), FF7(), FF8(), FF9(), FF10(), FF11(), FF12()}
	for _, value := range flags {
		if value == backendFlag {
			t.Fatalf("native library returned backend flag")
		}
	}
}

func TestIsRootedEnvironmentBuildStrings(t *testing.T) {
	if !IsRootedEnvironment("google/sdk_gphone64/ranchu", "Android SDK built for arm64", "sdk_gphone64", "") {
		t.Fatalf("emulator build strings were not detected")
	}
}

func TestVerifySealedParcel(t *testing.T) {
	iv := []byte("0123456789abcdef")
	key := []byte("fedcba9876543210")
	parcel := sealForTest([]byte("ctfcup{server_side_only}"), iv, key)

	if !VerifySealedParcel(
		base64.StdEncoding.EncodeToString(parcel),
		base64.StdEncoding.EncodeToString(iv),
		base64.StdEncoding.EncodeToString(key),
	) {
		t.Fatalf("valid parcel was rejected")
	}
}

func sealForTest(plaintext, iv, key []byte) []byte {
	padded := pkcs7ForTest(plaintext)
	out := make([]byte, 0, len(padded))
	previous := iv
	for offset := 0; offset < len(padded); offset += blockSize {
		block := make([]byte, blockSize)
		for i := 0; i < blockSize; i++ {
			block[i] = (padded[offset+i] ^ previous[i]) ^ key[i]
		}
		out = append(out, block...)
		previous = block
	}
	return out
}

func pkcs7ForTest(data []byte) []byte {
	padLen := blockSize - len(data)%blockSize
	out := append([]byte(nil), data...)
	for i := 0; i < padLen; i++ {
		out = append(out, byte(padLen))
	}
	return out
}

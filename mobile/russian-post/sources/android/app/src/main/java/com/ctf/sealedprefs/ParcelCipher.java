package com.ctf.sealedprefs;

public final class ParcelCipher {
    private ParcelCipher() {
    }

    public static boolean verifySealedParcel(String parcelB64, String ivB64, String keyB64) {
        return NativeBridge.verifySealedParcel(parcelB64, ivB64, keyB64);
    }
}

package ru.ctf.meowsim.state;

import ru.ctf.meowsim.security.HashKit;

public final class SealVerifier {
    private SealVerifier() {
    }

    public static boolean verify(String snapshot, String observerToken, String seal) {
        if (snapshot == null || seal == null) {
            return false;
        }
        String expected = HashKit.sha256(snapshot + "|" + observerToken + "|restore-v1");
        return expected.equalsIgnoreCase(seal.trim());
    }
}

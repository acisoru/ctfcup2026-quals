package com.ctf.sealedprefs;

import java.lang.reflect.Method;

final class NativeBridge {
    private static final String MOBILELIB = "mobilelib.Mobilelib";

    private NativeBridge() {
    }

    static boolean isRootedEnvironment(String fingerprint, String model, String product, String tags) {
        return callBoolean(false,
                "isRootedEnvironment",
                new Class<?>[] {String.class, String.class, String.class, String.class},
                clean(fingerprint), clean(model), clean(product), clean(tags));
    }

    static boolean verifySealedParcel(String parcelB64, String ivB64, String keyB64) {
        return callBoolean(false,
                "verifySealedParcel",
                new Class<?>[] {String.class, String.class, String.class},
                clean(parcelB64), clean(ivB64), clean(keyB64));
    }

    private static boolean callBoolean(boolean fallback, String method, Class<?>[] types, Object... args) {
        try {
            Class<?> bridge = Class.forName(MOBILELIB);
            Method target = bridge.getMethod(method, types);
            Object result = target.invoke(null, args);
            return Boolean.TRUE.equals(result);
        } catch (Exception ignored) {
            return fallback;
        }
    }

    private static String clean(String value) {
        return value == null ? "" : value;
    }
}

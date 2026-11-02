package com.ctf.sealedprefs;

public final class ApiContract {
    public static final String CONFIG_ENDPOINT = "/api/config";
    public static final String PARCEL_ENDPOINT = "/api/parcel";
    public static final String KEY_ENDPOINT = "/api/key";

    public static final String[] KEY_REQUEST_FIELDS = new String[] {
            "package",
            "version",
            "challenge",
            "expires_at",
            "session",
            "rooted",
            "fingerprint",
            "model",
            "android_id",
            "receipt"
    };

    private ApiContract() {
    }
}

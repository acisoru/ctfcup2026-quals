package ru.ctf.meowsim.security;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;

public final class HashKit {
    private HashKit() {
    }

    public static byte[] sha256Bytes(String value) {
        return sha256Bytes(value.getBytes(StandardCharsets.UTF_8));
    }

    public static byte[] sha256Bytes(byte[] value) {
        try {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            return digest.digest(value);
        } catch (NoSuchAlgorithmException e) {
            throw new IllegalStateException(e);
        }
    }

    public static String sha256(String value) {
        return hex(sha256Bytes(value));
    }

    public static String hex(byte[] bytes) {
        StringBuilder out = new StringBuilder(bytes.length * 2);
        for (byte b : bytes) {
            out.append(String.format("%02x", b & 0xff));
        }
        return out.toString();
    }
}

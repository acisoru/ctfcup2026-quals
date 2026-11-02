package com.ctf.burntnote.crypto;

import javax.crypto.Cipher;
import javax.crypto.Mac;
import javax.crypto.SecretKeyFactory;
import javax.crypto.spec.GCMParameterSpec;
import javax.crypto.spec.PBEKeySpec;
import javax.crypto.spec.SecretKeySpec;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.SecureRandom;

/**
 * Message crypto for Burnt Note (seed schema v1).
 *
 * The device seed is built during onboarding from four entropy fragments
 * collected from other phone artifacts. SeedCollector normalizes every
 * fragment timestamp to UTC milliseconds, sorts fragments by time and joins
 * them with '-':
 *
 *     seed = "<frag_at_t1>-<frag_at_t2>-<frag_at_t3>-<frag_at_t4>"
 *
 * The salt is the ANDROID_ID string. Keys form a ratchet that grows out of
 * each message PLAINTEXT, so the chain cannot be skipped:
 *
 *     master = PBKDF2-HMAC-SHA256(seed, androidId, 100000, 32)
 *     key[1]  = HMAC-SHA256(master, "burnt-note/root")
 *     key[i]  = HMAC-SHA256(key[i-1],
 *                           paddedPlain[i-1] + "|burnt-note/step|" + i)
 *
 * Every message is zero-padded to exactly 1400 bytes before encryption and
 * sealed as AES-256-GCM with AAD "burnt-note/msg/<i>"; the 12-byte nonce is
 * stored next to the frame (ciphertext || tag).
 */
public final class BurntCrypto {

    public static final int PAD_LEN = 1400;
    public static final int PBKDF2_ITERATIONS = 100_000;
    public static final int KEY_LEN = 32;
    public static final int NONCE_LEN = 12;
    public static final int TAG_LEN = 16;

    private static final byte[] ROOT_INFO = ascii(join("burnt-", "note/root"));
    private static final String STEP_SUFFIX = join("|burnt-", "note/step|");
    private static final String AAD_PREFIX = join("burnt-", "note/msg/");

    private BurntCrypto() {
    }

    public static byte[] deriveMaster(String seedString, String androidId) {
        try {
            PBEKeySpec spec = new PBEKeySpec(
                    seedString.toCharArray(),
                    ascii(androidId),
                    PBKDF2_ITERATIONS,
                    KEY_LEN * 8);
            SecretKeyFactory f = SecretKeyFactory.getInstance(
                    join("PBKDF2WithHmac", "SHA256"));
            return f.generateSecret(spec).getEncoded();
        } catch (Exception e) {
            throw new IllegalStateException("master derivation failed", e);
        }
    }

    public static byte[] rootKey(byte[] master) {
        return hmac(master, ROOT_INFO);
    }

    public static byte[] stepKey(byte[] previousKey, byte[] previousPaddedPlain, int index) {
        byte[] suffix = ascii(STEP_SUFFIX + index);
        byte[] message = new byte[previousPaddedPlain.length + suffix.length];
        System.arraycopy(previousPaddedPlain, 0, message, 0, previousPaddedPlain.length);
        System.arraycopy(suffix, 0, message, previousPaddedPlain.length, suffix.length);
        return hmac(previousKey, message);
    }

    /** Zero-pads UTF-8 text to exactly PAD_LEN bytes. */
    public static byte[] pad(byte[] utf8Text) {
        if (utf8Text.length > PAD_LEN) {
            throw new IllegalArgumentException("message too long");
        }
        byte[] out = new byte[PAD_LEN];
        System.arraycopy(utf8Text, 0, out, 0, utf8Text.length);
        return out;
    }

    public static byte[] aadFor(int index) {
        return ascii(AAD_PREFIX + index);
    }

    /** Decoy legacy framing path kept in the dead client for forensic noise. */
    public static byte[] legacyAadFor(int index) {
        return ascii(join("burnt-", "note/legacy/") + index);
    }

    /** Decoy label; real frames never use this branch. */
    public static byte[] legacyRootInfo() {
        return ascii(join("burnt-", "note/archive"));
    }

    public static byte[] newNonce() {
        byte[] nonce = new byte[NONCE_LEN];
        new SecureRandom().nextBytes(nonce);
        return nonce;
    }

    /** Returns ciphertext || tag. */
    public static byte[] seal(byte[] key, byte[] nonce, int index, byte[] paddedPlain) {
        try {
            Cipher cipher = Cipher.getInstance(join("AES/", "GCM/NoPadding"));
            cipher.init(Cipher.ENCRYPT_MODE,
                    new SecretKeySpec(key, "AES"),
                    new GCMParameterSpec(TAG_LEN * 8, nonce));
            cipher.updateAAD(aadFor(index));
            return cipher.doFinal(paddedPlain);
        } catch (Exception e) {
            throw new IllegalStateException("seal failed", e);
        }
    }

    /** Verifies the tag and returns the padded plaintext. */
    public static byte[] open(byte[] key, byte[] nonce, int index, byte[] frame) {
        try {
            Cipher cipher = Cipher.getInstance(join("AES/", "GCM/NoPadding"));
            cipher.init(Cipher.DECRYPT_MODE,
                    new SecretKeySpec(key, "AES"),
                    new GCMParameterSpec(TAG_LEN * 8, nonce));
            cipher.updateAAD(aadFor(index));
            return cipher.doFinal(frame);
        } catch (Exception e) {
            throw new IllegalStateException("open failed: bad tag or damaged row", e);
        }
    }

    public static String buildSeed(Iterable<SeedFragment> fragments) {
        StringBuilder sb = new StringBuilder();
        for (SeedFragment fragment : fragments) {
            if (sb.length() > 0) {
                sb.append('-');
            }
            sb.append(fragment.fragment);
        }
        return sb.toString();
    }

    private static byte[] hmac(byte[] key, byte[] message) {
        try {
            Mac mac = Mac.getInstance("HmacSHA256");
            mac.init(new SecretKeySpec(key, "HmacSHA256"));
            return mac.doFinal(message);
        } catch (Exception e) {
            throw new IllegalStateException("hmac failed", e);
        }
    }

    private static byte[] ascii(String s) {
        return s.getBytes(StandardCharsets.US_ASCII);
    }

    private static String join(String left, String right) {
        return new StringBuilder(left.length() + right.length())
                .append(left).append(right).toString();
    }
}

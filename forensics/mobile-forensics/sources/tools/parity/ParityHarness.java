public class ParityHarness {
    // args: seed androidId text1 nonceHex
    public static void main(String[] args) throws Exception {
        String seed = args[0];
        String androidId = args[1];
        byte[] text1 = args[2].getBytes(java.nio.charset.StandardCharsets.UTF_8);
        byte[] nonce = hex(args[3]);

        byte[] master = com.ctf.burntnote.crypto.BurntCrypto.deriveMaster(seed, androidId);
        byte[] k1 = com.ctf.burntnote.crypto.BurntCrypto.rootKey(master);
        byte[] padded1 = com.ctf.burntnote.crypto.BurntCrypto.pad(text1);
        byte[] k2 = com.ctf.burntnote.crypto.BurntCrypto.stepKey(k1, padded1, 2);
        byte[] frame1 = com.ctf.burntnote.crypto.BurntCrypto.seal(k1, nonce, 1, padded1);
        // roundtrip to prove the java side is self-consistent
        byte[] back = com.ctf.burntnote.crypto.BurntCrypto.open(k1, nonce, 1, frame1);

        System.out.println(hex(master));
        System.out.println(hex(k1));
        System.out.println(hex(k2));
        System.out.println(hex(frame1));
        System.out.println(back == null ? "null" : String.valueOf(java.util.Arrays.equals(back, padded1)));
    }

    static byte[] hex(String s) {
        byte[] out = new byte[s.length() / 2];
        for (int i = 0; i < out.length; i++) {
            out[i] = (byte) Integer.parseInt(s.substring(i * 2, i * 2 + 2), 16);
        }
        return out;
    }

    static String hex(byte[] b) {
        StringBuilder sb = new StringBuilder(b.length * 2);
        for (byte x : b) {
            sb.append(String.format("%02x", x));
        }
        return sb.toString();
    }
}

package ru.ctf.meowsim.flag;

import java.io.ByteArrayOutputStream;
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;

import ru.ctf.meowsim.security.HashKit;
import ru.ctf.meowsim.state.QuantumState;

public final class FlagVault {
    private static final byte[] ENCRYPTED_FLAG = new byte[] {
        (byte)0xd9, (byte)0xdd, (byte)0x37, (byte)0x36, (byte)0x7f, (byte)0xa4, (byte)0x1f, (byte)0x61,
        (byte)0x17, (byte)0xc9, (byte)0x11, (byte)0x0b, (byte)0x0c, (byte)0xc1, (byte)0x2a, (byte)0x92,
        (byte)0x1d, (byte)0x08, (byte)0x8f, (byte)0x5b, (byte)0xa0, (byte)0x75, (byte)0x24
    };

    private FlagVault() {
    }

    public static String open(QuantumState state) {
        if (!state.canOpenFlagVault()) {
            return "Кот отказывается схлопываться во флаг.";
        }
        byte[] key = deriveKey(state);
        byte[] stream = stream(key, ENCRYPTED_FLAG.length);
        byte[] plain = new byte[ENCRYPTED_FLAG.length];
        for (int i = 0; i < ENCRYPTED_FLAG.length; i++) {
            plain[i] = (byte) (ENCRYPTED_FLAG[i] ^ stream[i]);
        }
        String flag = new String(plain, StandardCharsets.UTF_8);
        if (!flag.startsWith("ctfcup{")) {
            return "Коробка открылась, но флаг декогерировал.";
        }
        return flag;
    }

    private static byte[] deriveKey(QuantumState state) {
        String material = state.observer.observerToken
            + "|" + state.box.boxSeal
            + "|" + state.box.stability
            + "|" + state.pet.catAlive
            + "|" + state.box.catDead
            + "|" + state.box.superposition
            + "|" + state.observer.observed
            + "|meowsim-v1";
        return HashKit.sha256Bytes(material);
    }

    private static byte[] stream(byte[] seed, int length) {
        ByteArrayOutputStream output = new ByteArrayOutputStream();
        int counter = 0;
        while (output.size() < length) {
            ByteBuffer buffer = ByteBuffer.allocate(seed.length + 4);
            buffer.put(seed);
            buffer.putInt(counter++);
            output.write(HashKit.sha256Bytes(buffer.array()), 0, 32);
        }
        byte[] full = output.toByteArray();
        byte[] result = new byte[length];
        System.arraycopy(full, 0, result, 0, length);
        return result;
    }
}

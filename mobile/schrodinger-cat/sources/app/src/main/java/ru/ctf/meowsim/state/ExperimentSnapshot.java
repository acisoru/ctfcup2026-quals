package ru.ctf.meowsim.state;

import java.util.HashMap;
import java.util.Map;

public class ExperimentSnapshot {
    public final boolean catAlive;
    public final boolean catDead;
    public final boolean superposition;
    public final boolean observed;
    public final boolean restoreObserverState;
    public final int stability;

    public ExperimentSnapshot(boolean catAlive, boolean catDead, boolean superposition, boolean observed, boolean restoreObserverState, int stability) {
        this.catAlive = catAlive;
        this.catDead = catDead;
        this.superposition = superposition;
        this.observed = observed;
        this.restoreObserverState = restoreObserverState;
        this.stability = stability;
    }

    public static ExperimentSnapshot parse(String value) {
        Map<String, String> fields = new HashMap<>();
        for (String part : value.split(";")) {
            String[] pair = part.split("=", 2);
            if (pair.length == 2) {
                fields.put(pair[0].trim(), pair[1].trim());
            }
        }
        return new ExperimentSnapshot(
            bool(fields, "catAlive", true),
            bool(fields, "catDead", false),
            bool(fields, "superposition", true),
            bool(fields, "observed", false),
            bool(fields, "restoreObserverState", false),
            integer(fields, "stability", 35)
        );
    }

    public PetState toPetState(PetState current) {
        return new PetState(catAlive, current.hunger, current.mood, current.energy, current.health, current.cleanliness);
    }

    public BoxState toBoxState(BoxState current) {
        int safeStability = Math.max(0, Math.min(100, stability));
        return new BoxState(current.boxClosed, catDead, superposition, safeStability, BoxStore.sealFor(catDead, superposition, safeStability));
    }

    public ObserverState toObserverState(ObserverState current) {
        return new ObserverState(observed, current.observerToken, observed ? "RESTORED" : current.lastMeasurement);
    }

    private static boolean bool(Map<String, String> fields, String key, boolean fallback) {
        if (!fields.containsKey(key)) {
            return fallback;
        }
        return Boolean.parseBoolean(fields.get(key));
    }

    private static int integer(Map<String, String> fields, String key, int fallback) {
        try {
            return Integer.parseInt(fields.get(key));
        } catch (Exception ignored) {
            return fallback;
        }
    }
}

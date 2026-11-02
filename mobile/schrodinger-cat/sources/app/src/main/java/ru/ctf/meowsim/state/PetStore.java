package ru.ctf.meowsim.state;

import android.content.Context;
import android.content.SharedPreferences;

public class PetStore {
    private final SharedPreferences prefs;

    public PetStore(Context context) {
        prefs = context.getSharedPreferences("pet_state", Context.MODE_PRIVATE);
        if (!prefs.contains("initialized")) {
            save(new PetState(true, 55, 55, 60, 80, 65));
            prefs.edit().putBoolean("initialized", true).apply();
        }
    }

    public PetState load() {
        return new PetState(
            prefs.getBoolean("catAlive", true),
            prefs.getInt("hunger", 55),
            prefs.getInt("mood", 55),
            prefs.getInt("energy", 60),
            prefs.getInt("health", 80),
            prefs.getInt("cleanliness", 65)
        );
    }

    public void save(PetState state) {
        prefs.edit()
            .putBoolean("catAlive", state.catAlive)
            .putInt("hunger", clamp(state.hunger))
            .putInt("mood", clamp(state.mood))
            .putInt("energy", clamp(state.energy))
            .putInt("health", clamp(state.health))
            .putInt("cleanliness", clamp(state.cleanliness))
            .apply();
    }

    private int clamp(int value) {
        return Math.max(0, Math.min(100, value));
    }
}

package ru.ctf.meowsim.state;

import android.content.Context;
import android.content.SharedPreferences;

public class ObserverStore {
    public static final String DEFAULT_TOKEN = "ny4n-lab-token";
    private final SharedPreferences prefs;

    public ObserverStore(Context context) {
        prefs = context.getSharedPreferences("observer_state", Context.MODE_PRIVATE);
        if (!prefs.contains("observerToken")) {
            save(new ObserverState(false, DEFAULT_TOKEN, "none"));
        }
    }

    public ObserverState load() {
        return new ObserverState(
            prefs.getBoolean("observed", false),
            prefs.getString("observerToken", DEFAULT_TOKEN),
            prefs.getString("lastMeasurement", "none")
        );
    }

    public void save(ObserverState state) {
        prefs.edit()
            .putBoolean("observed", state.observed)
            .putString("observerToken", state.observerToken)
            .putString("lastMeasurement", state.lastMeasurement)
            .apply();
    }
}

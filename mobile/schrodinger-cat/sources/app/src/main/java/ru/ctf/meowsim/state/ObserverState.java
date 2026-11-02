package ru.ctf.meowsim.state;

public class ObserverState {
    public final boolean observed;
    public final String observerToken;
    public final String lastMeasurement;

    public ObserverState(boolean observed, String observerToken, String lastMeasurement) {
        this.observed = observed;
        this.observerToken = observerToken;
        this.lastMeasurement = lastMeasurement;
    }
}

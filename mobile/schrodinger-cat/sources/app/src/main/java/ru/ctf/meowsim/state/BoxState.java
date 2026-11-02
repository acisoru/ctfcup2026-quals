package ru.ctf.meowsim.state;

public class BoxState {
    public final boolean boxClosed;
    public final boolean catDead;
    public final boolean superposition;
    public final int stability;
    public final String boxSeal;

    public BoxState(boolean boxClosed, boolean catDead, boolean superposition, int stability, String boxSeal) {
        this.boxClosed = boxClosed;
        this.catDead = catDead;
        this.superposition = superposition;
        this.stability = stability;
        this.boxSeal = boxSeal;
    }
}

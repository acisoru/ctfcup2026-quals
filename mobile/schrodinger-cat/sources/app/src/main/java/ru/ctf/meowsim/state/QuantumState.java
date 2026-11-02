package ru.ctf.meowsim.state;

public class QuantumState {
    public final PetState pet;
    public final BoxState box;
    public final ObserverState observer;
    public final boolean tampered;

    public QuantumState(PetState pet, BoxState box, ObserverState observer, boolean tampered) {
        this.pet = pet;
        this.box = box;
        this.observer = observer;
        this.tampered = tampered;
    }

    public boolean canOpenFlagVault() {
        return pet.catAlive
            && box.catDead
            && box.superposition
            && box.stability >= 90
            && !observer.observed
            && !tampered;
    }
}

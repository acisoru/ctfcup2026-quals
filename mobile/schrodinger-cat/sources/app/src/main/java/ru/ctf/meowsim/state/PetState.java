package ru.ctf.meowsim.state;

public class PetState {
    public final boolean catAlive;
    public final int hunger;
    public final int mood;
    public final int energy;
    public final int health;
    public final int cleanliness;

    public PetState(boolean catAlive, int hunger, int mood, int energy, int health, int cleanliness) {
        this.catAlive = catAlive;
        this.hunger = hunger;
        this.mood = mood;
        this.energy = energy;
        this.health = health;
        this.cleanliness = cleanliness;
    }
}

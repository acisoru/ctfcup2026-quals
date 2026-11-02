package ru.ctf.meowsim.state;

import android.content.Context;

import ru.ctf.meowsim.security.TamperDetector;

public class StateRepository {
    private final PetStore petStore;
    private final BoxStore boxStore;
    private final ObserverStore observerStore;
    private final TamperDetector tamperDetector;

    public StateRepository(Context context) {
        petStore = new PetStore(context);
        boxStore = new BoxStore(context);
        observerStore = new ObserverStore(context);
        tamperDetector = new TamperDetector(context);
    }

    public PetState pet() {
        return petStore.load();
    }

    public BoxState box() {
        return boxStore.load();
    }

    public ObserverState observer() {
        return observerStore.load();
    }

    public QuantumState quantum() {
        return new QuantumState(pet(), box(), observer(), tamperDetector.isTampered());
    }

    public void feed() {
        PetState p = pet();
        petStore.save(new PetState(true, p.hunger + 18, p.mood + 4, p.energy - 3, p.health + 2, p.cleanliness - 4));
    }

    public void petCat() {
        PetState p = pet();
        petStore.save(new PetState(true, p.hunger - 2, p.mood + 14, p.energy + 2, p.health, p.cleanliness));
    }

    public void play() {
        PetState p = pet();
        petStore.save(new PetState(true, p.hunger - 8, p.mood + 20, p.energy - 12, p.health, p.cleanliness - 5));
    }

    public void sleep() {
        PetState p = pet();
        petStore.save(new PetState(true, p.hunger - 6, p.mood + 3, p.energy + 28, p.health + 4, p.cleanliness));
    }

    public void heal() {
        PetState p = pet();
        petStore.save(new PetState(true, p.hunger - 3, p.mood - 2, p.energy, p.health + 20, p.cleanliness));
    }

    public void cleanBox() {
        PetState p = pet();
        petStore.save(new PetState(true, p.hunger, p.mood + 5, p.energy, p.health + 1, p.cleanliness + 24));
    }

    public void stabilize() {
        PetState p = pet();
        int care = (p.hunger + p.mood + p.energy + p.health + p.cleanliness) / 5;
        int stability = Math.max(35, Math.min(92, care + 12));
        boolean superposition = stability >= 70;
        boolean catDead = false;
        boxStore.save(new BoxState(true, catDead, superposition, stability, BoxStore.sealFor(catDead, superposition, stability)));
    }

    public void observe() {
        ObserverState o = observer();
        BoxState b = box();
        boolean catDead = b.stability < 70;
        observerStore.save(new ObserverState(true, o.observerToken, catDead ? "DEAD" : "ALIVE"));
        boxStore.save(new BoxState(false, catDead, false, b.stability, BoxStore.sealFor(catDead, false, b.stability)));
    }

    public String openBox() {
        QuantumState state = quantum();
        if (state.canOpenFlagVault()) {
            return ru.ctf.meowsim.flag.FlagVault.open(state);
        }
        if (state.tampered) {
            return "TAMPERED_CAT: кот заметил патч и отказывается коллапсировать.";
        }
        if (state.observer.observed) {
            return "Волновая функция уже схлопнулась в состояние " + state.observer.lastMeasurement + ".";
        }
        return "Коробка тихо гудит. Кот все еще не определился.";
    }

    public void restore(ExperimentSnapshot snapshot) {
        petStore.save(snapshot.toPetState(pet()));
        boxStore.save(snapshot.toBoxState(box()));
        if (snapshot.restoreObserverState) {
            observerStore.save(snapshot.toObserverState(observer()));
        }
    }
}

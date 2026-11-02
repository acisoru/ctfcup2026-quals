package ru.ctf.meowsim.lab;

import android.app.Activity;
import android.os.Bundle;
import android.widget.TextView;

import ru.ctf.meowsim.state.ExperimentSnapshot;
import ru.ctf.meowsim.state.ObserverStore;
import ru.ctf.meowsim.state.SealVerifier;
import ru.ctf.meowsim.state.StateRepository;

public class RestoreExperimentActivity extends Activity {
    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);

        String mode = getIntent().getStringExtra("mode");
        String snapshot = getIntent().getStringExtra("snapshot");
        String seal = getIntent().getStringExtra("seal");

        TextView result = new TextView(this);
        result.setTextSize(18);
        result.setPadding(32, 32, 32, 32);
        setContentView(result);

        if (!"restore".equals(mode)) {
            result.setText("Лабораторный режим восстановления не выбран.");
            return;
        }

        ObserverStore observerStore = new ObserverStore(this);
        String token = observerStore.load().observerToken;
        if (!SealVerifier.verify(snapshot, token, seal)) {
            result.setText("Печать отклонена. Лабораторный кот вам не поверил.");
            return;
        }

        ExperimentSnapshot parsed = ExperimentSnapshot.parse(snapshot);
        new StateRepository(this).restore(parsed);
        result.setText("Эксперимент восстановлен. Теперь коробка помнит другого кота.");
    }
}

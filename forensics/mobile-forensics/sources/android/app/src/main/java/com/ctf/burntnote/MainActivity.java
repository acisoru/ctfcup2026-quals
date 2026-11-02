package com.ctf.burntnote;

import android.app.Activity;
import android.graphics.Color;
import android.graphics.Typeface;
import android.os.Bundle;
import android.view.Gravity;
import android.widget.LinearLayout;
import android.widget.TextView;

/**
 * Burnt Note client. The sync endpoint (sync.burntnote.onion) has been
 * decommissioned, so the app can only show its last known local state.
 */
public final class MainActivity extends Activity {

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);

        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setGravity(Gravity.CENTER);
        root.setPadding(64, 64, 64, 64);
        root.setBackgroundColor(Color.rgb(18, 18, 20));

        TextView title = new TextView(this);
        title.setText("Burnt Note");
        title.setTextSize(28);
        title.setTypeface(Typeface.DEFAULT_BOLD);
        title.setTextColor(Color.rgb(240, 208, 88));
        root.addView(title);

        TextView status = new TextView(this);
        status.setText("Нет соединения с sync.burntnote.onion");
        status.setTextSize(16);
        status.setPadding(0, 32, 0, 32);
        status.setTextColor(Color.rgb(220, 90, 70));
        root.addView(status);

        TextView meta = new TextView(this);
        meta.setText(
                "local session: sealed (4/4)\n" +
                "key material: unavailable\n" +
                "local db: messages.db (wal)\n" +
                "messages: 0 (wiped by self-destruct)");
        meta.setTextSize(13);
        meta.setTextColor(Color.rgb(168, 168, 168));
        root.addView(meta);

        TextView hint = new TextView(this);
        hint.setText("Онбординг завершён. Восстановление сессии невозможно: сервер ключей недоступен.");
        hint.setTextSize(12);
        hint.setPadding(0, 48, 0, 0);
        hint.setTextColor(Color.rgb(120, 120, 120));
        root.addView(hint);

        setContentView(root);
    }
}

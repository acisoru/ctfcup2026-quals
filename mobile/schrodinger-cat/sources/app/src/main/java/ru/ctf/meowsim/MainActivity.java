package ru.ctf.meowsim;

import android.app.Activity;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.Drawable;
import android.graphics.drawable.GradientDrawable;
import android.os.Bundle;
import android.view.Gravity;
import android.view.View;
import android.widget.FrameLayout;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;

import java.text.SimpleDateFormat;
import java.util.Date;
import java.util.Locale;

import ru.ctf.meowsim.state.BoxState;
import ru.ctf.meowsim.state.ObserverState;
import ru.ctf.meowsim.state.PetState;
import ru.ctf.meowsim.state.QuantumState;
import ru.ctf.meowsim.state.StateRepository;

public class MainActivity extends Activity {
    private enum Screen {
        CAT,
        CARE,
        LAB,
        DIARY
    }

    private StateRepository repository;
    private LinearLayout root;
    private LinearLayout sidebar;
    private LinearLayout screenContainer;
    private CatBoxView catView;
    private View scrim;
    private Screen currentScreen = Screen.CAT;
    private boolean sidebarOpen = false;
    private int openedStory = -1;
    private String lastBoxMessage = null;
    private final StringBuilder diary = new StringBuilder();

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        repository = new StateRepository(this);
        buildUi();
        log("симулятор запущен");
        render();
    }

    private void buildUi() {
        FrameLayout shell = new FrameLayout(this);
        shell.setBackgroundColor(Color.rgb(244, 238, 226));
        setContentView(shell);

        ScrollView scroll = new ScrollView(this);
        root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setPadding(dp(18), dp(18), dp(18), dp(24));
        root.setBackgroundColor(Color.rgb(244, 238, 226));
        scroll.addView(root);
        shell.addView(scroll, new FrameLayout.LayoutParams(
            FrameLayout.LayoutParams.MATCH_PARENT,
            FrameLayout.LayoutParams.MATCH_PARENT
        ));

        scrim = new View(this);
        scrim.setBackgroundColor(Color.argb(92, 20, 32, 34));
        scrim.setVisibility(View.GONE);
        scrim.setOnClickListener((View ignored) -> {
            sidebarOpen = false;
            render();
        });
        shell.addView(scrim, new FrameLayout.LayoutParams(
            FrameLayout.LayoutParams.MATCH_PARENT,
            FrameLayout.LayoutParams.MATCH_PARENT
        ));

        sidebar = new LinearLayout(this);
        sidebar.setOrientation(LinearLayout.VERTICAL);
        sidebar.setGravity(Gravity.CENTER_HORIZONTAL);
        sidebar.setPadding(dp(14), dp(22), dp(14), dp(18));
        sidebar.setBackground(sidebarBg());
        sidebar.setElevation(dp(8));
        sidebar.setVisibility(View.GONE);
        FrameLayout.LayoutParams sidebarParams = new FrameLayout.LayoutParams(
            dp(88),
            FrameLayout.LayoutParams.MATCH_PARENT
        );
        sidebarParams.gravity = Gravity.START;
        shell.addView(sidebar, sidebarParams);

        LinearLayout header = new LinearLayout(this);
        header.setOrientation(LinearLayout.HORIZONTAL);
        header.setGravity(Gravity.CENTER_VERTICAL);

        TextView menu = compactButton("☰", () -> {
            sidebarOpen = !sidebarOpen;
            render();
        });
        header.addView(menu);

        LinearLayout titleBlock = new LinearLayout(this);
        titleBlock.setOrientation(LinearLayout.VERTICAL);
        LinearLayout.LayoutParams titleParams = new LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1);
        titleParams.setMargins(dp(12), 0, 0, 0);
        titleBlock.setLayoutParams(titleParams);

        TextView title = text("МяуСим", 28, true);
        TextView subtitle = text("кот Шредингера в карманной лаборатории", 14, false);
        subtitle.setTextColor(Color.rgb(88, 95, 96));
        titleBlock.addView(title);
        titleBlock.addView(subtitle);
        header.addView(titleBlock);
        root.addView(heroCard(header));

        catView = new CatBoxView(this);
        LinearLayout.LayoutParams catParams = new LinearLayout.LayoutParams(
            LinearLayout.LayoutParams.MATCH_PARENT,
            LinearLayout.LayoutParams.WRAP_CONTENT
        );
        catParams.setMargins(0, dp(14), 0, dp(10));
        catView.setLayoutParams(catParams);
        root.addView(catView);

        screenContainer = new LinearLayout(this);
        screenContainer.setOrientation(LinearLayout.VERTICAL);
        root.addView(screenContainer);
    }

    private void render() {
        QuantumState q = repository.quantum();
        PetState p = q.pet;
        BoxState b = q.box;
        ObserverState o = q.observer;

        catView.setState(
            b.superposition,
            o.observed,
            b.catDead,
            p.hunger,
            p.mood,
            p.energy,
            p.health,
            p.cleanliness,
            b.stability
        );

        renderSidebar();
        screenContainer.removeAllViews();
        if (currentScreen == Screen.CAT) {
            renderCatScreen(q);
        } else if (currentScreen == Screen.CARE) {
            renderCareScreen(p);
        } else if (currentScreen == Screen.LAB) {
            renderLabScreen(q);
        } else {
            renderDiaryScreen();
        }
    }

    private void renderSidebar() {
        sidebar.removeAllViews();
        sidebar.setVisibility(sidebarOpen ? View.VISIBLE : View.GONE);
        scrim.setVisibility(sidebarOpen ? View.VISIBLE : View.GONE);

        sidebar.addView(navButton("Дом", Screen.CAT, R.drawable.ic_home));
        sidebar.addView(navButton("Уход", Screen.CARE, R.drawable.ic_care));
        sidebar.addView(navButton("Лаборатория", Screen.LAB, R.drawable.ic_lab));
        sidebar.addView(navButton("Дневник", Screen.DIARY, R.drawable.ic_diary));
    }

    private void renderCatScreen(QuantumState q) {
        PetState p = q.pet;
        BoxState b = q.box;
        ObserverState o = q.observer;

        screenContainer.addView(screenTitle("Дом кота", "текущее самочувствие и состояние коробки"));

        TextView summary = text(catMoodText(p, b, o), 16, false);
        screenContainer.addView(card(summary));

        if (lastBoxMessage != null) {
            screenContainer.addView(resultCard(lastBoxMessage));
        }

        LinearLayout stats = new LinearLayout(this);
        stats.setOrientation(LinearLayout.VERTICAL);
        stats.addView(meter("Сытость", p.hunger, Color.rgb(201, 78, 55)));
        stats.addView(meter("Настроение", p.mood, Color.rgb(236, 102, 116)));
        stats.addView(meter("Энергия", p.energy, Color.rgb(104, 164, 177)));
        stats.addView(meter("Здоровье", p.health, Color.rgb(96, 154, 106)));
        stats.addView(meter("Чистота", p.cleanliness, Color.rgb(145, 124, 207)));
        screenContainer.addView(card(stats));

        LinearLayout chips = row();
        chips.addView(chip(b.superposition ? "суперпозиция" : "схлопнуто", b.superposition));
        chips.addView(chip(o.observed ? "наблюдали" : "не наблюдали", !o.observed));
        chips.addView(chip("стабильность " + b.stability, b.stability >= 70));
        screenContainer.addView(chips);

        LinearLayout row = row();
        row.addView(primaryButton("Открыть коробку", this::openBox));
        screenContainer.addView(row);
    }

    private void renderCareScreen(PetState p) {
        screenContainer.addView(screenTitle("Уход", "действия меняют вид кота и параметры симуляции"));

        LinearLayout careRow1 = row();
        careRow1.addView(actionButton("Кормить", "сытость +", R.drawable.ic_feed, () -> action("кот поел и выглядит довольнее", repository::feed)));
        careRow1.addView(actionButton("Гладить", "настроение +", R.drawable.ic_pet, () -> action("кот замурчал", repository::petCat)));
        careRow1.addView(actionButton("Играть", "радость +", R.drawable.ic_play, () -> action("кот гонялся за квантовой ниткой", repository::play)));
        screenContainer.addView(careRow1);

        LinearLayout careRow2 = row();
        careRow2.addView(actionButton("Спать", "энергия +", R.drawable.ic_sleep, () -> action("кот восстановил энергию", repository::sleep)));
        careRow2.addView(actionButton("Лечить", "здоровье +", R.drawable.ic_heal, () -> action("здоровье кота стабилизировано", repository::heal)));
        careRow2.addView(actionButton("Убрать", "чистота +", R.drawable.ic_clean, () -> action("коробка стала чище", repository::cleanBox)));
        screenContainer.addView(careRow2);

        LinearLayout stats = new LinearLayout(this);
        stats.setOrientation(LinearLayout.VERTICAL);
        stats.addView(meter("Сытость", p.hunger, Color.rgb(201, 78, 55)));
        stats.addView(meter("Настроение", p.mood, Color.rgb(236, 102, 116)));
        stats.addView(meter("Энергия", p.energy, Color.rgb(104, 164, 177)));
        stats.addView(meter("Здоровье", p.health, Color.rgb(96, 154, 106)));
        stats.addView(meter("Чистота", p.cleanliness, Color.rgb(145, 124, 207)));
        screenContainer.addView(card(stats));
    }

    private void renderLabScreen(QuantumState q) {
        PetState p = q.pet;
        BoxState b = q.box;
        ObserverState o = q.observer;

        screenContainer.addView(screenTitle("Лаборатория", "квантовые датчики и управление измерением"));

        LinearLayout board = new LinearLayout(this);
        board.setOrientation(LinearLayout.VERTICAL);
        board.addView(labLine("кот_жив", String.valueOf(p.catAlive), p.catAlive));
        board.addView(labLine("кот_мертв", String.valueOf(b.catDead), !b.catDead));
        board.addView(labLine("суперпозиция", String.valueOf(b.superposition), b.superposition));
        board.addView(labLine("стабильность", String.valueOf(b.stability), b.stability >= 70));
        board.addView(labLine("наблюдали", String.valueOf(o.observed), !o.observed));
        board.addView(labLine("tampered", String.valueOf(q.tampered), !q.tampered));
        screenContainer.addView(darkCard(board));

        TextView lab = text(
            "boxSeal\n" + shortValue(b.boxSeal),
            13,
            false
        );
        lab.setTypeface(Typeface.MONOSPACE);
        screenContainer.addView(card(lab));

        if (lastBoxMessage != null) {
            screenContainer.addView(resultCard(lastBoxMessage));
        }

        LinearLayout labRow = row();
        labRow.addView(actionButton("Стабилизировать", "stability", R.drawable.ic_stabilize, () -> action("дрейф волновой функции снижен", repository::stabilize)));
        labRow.addView(actionButton("Наблюдать", "collapse", R.drawable.ic_observe, () -> action("запрошено измерение", repository::observe)));
        screenContainer.addView(labRow);

        LinearLayout openRow = row();
        openRow.addView(primaryButton("Открыть коробку", this::openBox));
        screenContainer.addView(openRow);
    }

    private void renderDiaryScreen() {
        screenContainer.addView(screenTitle("Дневник", "открывайте записи по одной"));
        screenContainer.addView(storyCard(
            0,
            "Запись 01. Коробка",
            "Кот появился в лаборатории вместе с картонной коробкой, на которой маркером было написано: \"не открывать без причины\". Сначала он просто спал внутри и сердито щурился на датчики. Потом приборы стали показывать два результата сразу."
        ));
        screenContainer.addView(storyCard(
            1,
            "Запись 02. Наблюдатель",
            "Ассистенты быстро заметили странность: если смотреть на кота слишком внимательно, он выбирал одно состояние и делал вид, что так было всегда. Если же оставить наблюдателя в покое, коробка продолжала помнить больше, чем должна."
        ));
        screenContainer.addView(storyCard(
            2,
            "Запись 03. Восстановление",
            "После первого сбоя лаборатория добавила режим восстановления эксперимента. Он должен был чинить поврежденные снимки состояния, но иногда восстанавливал кота и коробку отдельно от того, кто на них смотрел."
        ));
        screenContainer.addView(storyCard(
            3,
            "Запись 04. Правильная невозможность",
            "Кот не любит, когда его заставляют быть обычным. Ему нравится состояние, где коробка уверена в одном, питомец в другом, а наблюдатель честно утверждает, что еще ничего не видел."
        ));
    }

    private String catMoodText(PetState p, BoxState b, ObserverState o) {
        if (o.observed) {
            return "Кот выглядит так, будто его уже измерили. Атмосфера стала определенной.";
        }
        if (b.catDead) {
            return "С коробкой что-то не так. Лабораторные датчики нервно мигают.";
        }
        if (p.health < 35) {
            return "Коту нездоровится. Он просит лекарство и немного тишины.";
        }
        if (p.energy < 30) {
            return "Кот клюет носом. Пора отправить его спать.";
        }
        if (p.hunger < 30) {
            return "Кот смотрит на миску с философской тоской.";
        }
        if (p.cleanliness < 30) {
            return "Коробка уже подозрительно пахнет экспериментом.";
        }
        if (p.mood > 80) {
            return "Кот доволен и мурчит в нескольких состояниях сразу.";
        }
        return "Кот наблюдает за вами и делает вид, что он главный исследователь.";
    }

    private ImageView navButton(String label, Screen screen, int iconRes) {
        ImageView button = new ImageView(this);
        button.setContentDescription(label);
        int bg = currentScreen == screen ? Color.rgb(250, 220, 190) : Color.rgb(48, 79, 82);
        int stroke = currentScreen == screen ? Color.rgb(255, 190, 118) : Color.rgb(69, 105, 108);
        button.setBackground(round(bg, dp(12), stroke));
        Drawable icon = getDrawable(iconRes);
        if (icon != null) {
            icon.setTint(currentScreen == screen ? Color.rgb(35, 48, 49) : Color.rgb(235, 244, 242));
            button.setImageDrawable(icon);
        }
        button.setScaleType(ImageView.ScaleType.CENTER);
        button.setPadding(dp(14), dp(14), dp(14), dp(14));
        button.setOnClickListener((View ignored) -> {
            currentScreen = screen;
            sidebarOpen = false;
            render();
        });
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(
            dp(56),
            dp(56)
        );
        params.setMargins(0, 0, 0, dp(12));
        button.setLayoutParams(params);
        return button;
    }

    private void openBox() {
        String result = repository.openBox();
        lastBoxMessage = result;
        log("коробка открыта: " + result);
        render();
    }

    private void action(String message, Runnable runnable) {
        runnable.run();
        log(message);
        render();
    }

    private LinearLayout row() {
        LinearLayout row = new LinearLayout(this);
        row.setOrientation(LinearLayout.HORIZONTAL);
        row.setGravity(Gravity.CENTER);
        row.setPadding(0, dp(4), 0, dp(4));
        return row;
    }

    private TextView button(String label, Runnable onClick) {
        TextView button = text(label, 14, true);
        button.setText(label);
        button.setGravity(Gravity.CENTER);
        button.setOnClickListener((View ignored) -> onClick.run());
        button.setTextColor(Color.rgb(35, 48, 49));
        button.setBackground(round(Color.rgb(219, 241, 238), dp(12), Color.rgb(134, 188, 184)));
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(0, dp(50), 1);
        params.setMargins(dp(3), 0, dp(3), 0);
        button.setLayoutParams(params);
        return button;
    }

    private TextView primaryButton(String label, Runnable onClick) {
        TextView button = button(label, onClick);
        button.setTextColor(Color.rgb(255, 249, 238));
        button.setTextSize(15);
        button.setTypeface(Typeface.DEFAULT_BOLD);
        button.setBackground(round(Color.rgb(201, 78, 55), dp(14), Color.rgb(145, 84, 49)));
        return button;
    }

    private View actionButton(String title, String caption, int iconRes, Runnable onClick) {
        LinearLayout button = new LinearLayout(this);
        button.setOrientation(LinearLayout.VERTICAL);
        button.setGravity(Gravity.CENTER);
        button.setPadding(dp(8), dp(8), dp(8), dp(8));
        button.setContentDescription(title + ": " + caption);
        button.setBackground(round(Color.rgb(255, 249, 238), dp(16), Color.rgb(226, 212, 190)));
        button.setOnClickListener((View ignored) -> onClick.run());

        ImageView iconView = new ImageView(this);
        Drawable icon = getDrawable(iconRes);
        if (icon != null) {
            icon.setTint(Color.rgb(35, 48, 49));
            iconView.setImageDrawable(icon);
        }
        iconView.setScaleType(ImageView.ScaleType.CENTER);
        button.addView(iconView, new LinearLayout.LayoutParams(dp(34), dp(34)));

        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(0, dp(62), 1);
        params.setMargins(dp(4), dp(4), dp(4), dp(4));
        button.setLayoutParams(params);
        return button;
    }

    private TextView compactButton(String label, Runnable onClick) {
        TextView button = text(label, 22, true);
        button.setText(label);
        button.setGravity(Gravity.CENTER);
        button.setOnClickListener((View ignored) -> onClick.run());
        button.setTextColor(Color.rgb(255, 249, 238));
        button.setBackground(round(Color.rgb(32, 57, 60), dp(16), Color.rgb(69, 105, 108)));
        button.setLayoutParams(new LinearLayout.LayoutParams(dp(52), dp(52)));
        return button;
    }

    private TextView text(String value, int sp, boolean bold) {
        TextView text = new TextView(this);
        text.setText(value);
        text.setTextSize(sp);
        text.setTextColor(Color.rgb(27, 34, 36));
        text.setLineSpacing(dp(2), 1.0f);
        if (bold) {
            text.setTypeface(Typeface.DEFAULT_BOLD);
        }
        return text;
    }

    private View card(View content) {
        LinearLayout card = new LinearLayout(this);
        card.setOrientation(LinearLayout.VERTICAL);
        card.setPadding(dp(16), dp(14), dp(16), dp(14));
        card.setBackground(round(Color.rgb(255, 249, 238), dp(14), Color.rgb(226, 212, 190)));
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(
            LinearLayout.LayoutParams.MATCH_PARENT,
            LinearLayout.LayoutParams.WRAP_CONTENT
        );
        params.setMargins(0, dp(8), 0, dp(4));
        card.setLayoutParams(params);
        card.setElevation(dp(2));
        card.addView(content);
        return card;
    }

    private View darkCard(View content) {
        LinearLayout card = new LinearLayout(this);
        card.setOrientation(LinearLayout.VERTICAL);
        card.setPadding(dp(16), dp(14), dp(16), dp(14));
        card.setBackground(round(Color.rgb(32, 57, 60), dp(14), Color.rgb(69, 105, 108)));
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(
            LinearLayout.LayoutParams.MATCH_PARENT,
            LinearLayout.LayoutParams.WRAP_CONTENT
        );
        params.setMargins(0, dp(8), 0, dp(4));
        card.setLayoutParams(params);
        card.setElevation(dp(3));
        card.addView(content);
        return card;
    }

    private View resultCard(String message) {
        TextView result = text(message, message.startsWith("ctfcup{") ? 18 : 15, true);
        result.setGravity(Gravity.CENTER);
        result.setTextColor(message.startsWith("ctfcup{") ? Color.rgb(255, 249, 238) : Color.rgb(72, 55, 42));

        LinearLayout card = new LinearLayout(this);
        card.setOrientation(LinearLayout.VERTICAL);
        card.setPadding(dp(16), dp(16), dp(16), dp(16));
        int bg = message.startsWith("ctfcup{") ? Color.rgb(32, 57, 60) : Color.rgb(250, 220, 190);
        int stroke = message.startsWith("ctfcup{") ? Color.rgb(134, 188, 184) : Color.rgb(196, 126, 72);
        card.setBackground(round(bg, dp(16), stroke));
        card.setElevation(dp(3));
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(
            LinearLayout.LayoutParams.MATCH_PARENT,
            LinearLayout.LayoutParams.WRAP_CONTENT
        );
        params.setMargins(0, dp(8), 0, dp(4));
        card.setLayoutParams(params);
        card.addView(result);
        return card;
    }

    private View storyCard(int index, String title, String body) {
        boolean opened = openedStory == index;
        LinearLayout card = new LinearLayout(this);
        card.setOrientation(LinearLayout.VERTICAL);
        card.setPadding(dp(16), dp(14), dp(16), opened ? dp(14) : dp(12));
        card.setBackground(round(opened ? Color.rgb(255, 249, 238) : Color.rgb(250, 240, 224), dp(14), Color.rgb(226, 212, 190)));
        card.setElevation(dp(2));
        card.setOnClickListener((View ignored) -> {
            openedStory = opened ? -1 : index;
            render();
        });

        TextView titleView = text((opened ? "− " : "+ ") + title, 15, true);
        titleView.setTextColor(Color.rgb(72, 55, 42));
        card.addView(titleView);

        if (opened) {
            TextView bodyView = text(body, 14, false);
            bodyView.setTextColor(Color.rgb(61, 70, 72));
            LinearLayout.LayoutParams bodyParams = new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT
            );
            bodyParams.setMargins(0, dp(8), 0, 0);
            card.addView(bodyView, bodyParams);
        }

        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(
            LinearLayout.LayoutParams.MATCH_PARENT,
            LinearLayout.LayoutParams.WRAP_CONTENT
        );
        params.setMargins(0, dp(8), 0, dp(4));
        card.setLayoutParams(params);
        return card;
    }

    private View screenTitle(String title, String subtitle) {
        LinearLayout wrap = new LinearLayout(this);
        wrap.setOrientation(LinearLayout.VERTICAL);
        wrap.setPadding(dp(2), dp(8), dp(2), dp(4));
        TextView titleView = text(title, 22, true);
        TextView subtitleView = text(subtitle, 13, false);
        subtitleView.setTextColor(Color.rgb(88, 95, 96));
        wrap.addView(titleView);
        wrap.addView(subtitleView);
        return wrap;
    }

    private View chip(String label, boolean positive) {
        TextView chip = text(label, 12, true);
        chip.setGravity(Gravity.CENTER);
        chip.setTextColor(positive ? Color.rgb(35, 48, 49) : Color.rgb(255, 249, 238));
        int bg = positive ? Color.rgb(219, 241, 238) : Color.rgb(201, 78, 55);
        int stroke = positive ? Color.rgb(134, 188, 184) : Color.rgb(145, 84, 49);
        chip.setBackground(round(bg, dp(16), stroke));
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(0, dp(36), 1);
        params.setMargins(dp(3), dp(4), dp(3), dp(4));
        chip.setLayoutParams(params);
        return chip;
    }

    private View labLine(String label, String value, boolean ok) {
        LinearLayout line = new LinearLayout(this);
        line.setOrientation(LinearLayout.HORIZONTAL);
        line.setGravity(Gravity.CENTER_VERTICAL);
        line.setPadding(0, dp(5), 0, dp(5));

        TextView name = text(label, 14, false);
        name.setTypeface(Typeface.MONOSPACE);
        name.setTextColor(Color.rgb(219, 241, 238));
        line.addView(name, new LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1));

        TextView status = text(value, 14, true);
        status.setTypeface(Typeface.MONOSPACE);
        status.setGravity(Gravity.CENTER);
        status.setTextColor(ok ? Color.rgb(35, 48, 49) : Color.rgb(255, 249, 238));
        int bg = ok ? Color.rgb(219, 241, 238) : Color.rgb(201, 78, 55);
        int stroke = ok ? Color.rgb(134, 188, 184) : Color.rgb(145, 84, 49);
        status.setBackground(round(bg, dp(12), stroke));
        line.addView(status, new LinearLayout.LayoutParams(dp(92), dp(34)));
        return line;
    }

    private View heroCard(View content) {
        LinearLayout card = new LinearLayout(this);
        card.setOrientation(LinearLayout.VERTICAL);
        card.setPadding(dp(18), dp(16), dp(18), dp(16));
        card.setBackground(round(Color.rgb(255, 249, 238), dp(18), Color.rgb(226, 212, 190)));
        card.setElevation(dp(3));
        card.addView(content);
        return card;
    }

    private View meter(String label, int value, int color) {
        LinearLayout wrap = new LinearLayout(this);
        wrap.setOrientation(LinearLayout.VERTICAL);
        wrap.setPadding(0, dp(4), 0, dp(6));

        TextView caption = text(label + ": " + value, 13, true);
        wrap.addView(caption);

        LinearLayout track = new LinearLayout(this);
        track.setOrientation(LinearLayout.HORIZONTAL);
        track.setBackground(round(Color.rgb(235, 226, 210), dp(7), Color.rgb(222, 210, 190)));
        LinearLayout.LayoutParams trackParams = new LinearLayout.LayoutParams(
            LinearLayout.LayoutParams.MATCH_PARENT,
            dp(12)
        );
        trackParams.setMargins(0, dp(4), 0, 0);
        track.setLayoutParams(trackParams);

        View fill = new View(this);
        fill.setBackground(round(color, dp(7), color));
        track.addView(fill, new LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.MATCH_PARENT, Math.max(0, value)));
        View empty = new View(this);
        track.addView(empty, new LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.MATCH_PARENT, Math.max(0, 100 - value)));

        wrap.addView(track);
        return wrap;
    }

    private GradientDrawable round(int color, int radius, int stroke) {
        GradientDrawable drawable = new GradientDrawable();
        drawable.setColor(color);
        drawable.setCornerRadius(radius);
        drawable.setStroke(dp(1), stroke);
        return drawable;
    }

    private GradientDrawable sidebarBg() {
        GradientDrawable drawable = new GradientDrawable(
            GradientDrawable.Orientation.TOP_BOTTOM,
            new int[] {Color.rgb(32, 57, 60), Color.rgb(48, 79, 82)}
        );
        return drawable;
    }

    private void log(String message) {
        String time = new SimpleDateFormat("HH:mm:ss", Locale.US).format(new Date());
        diary.insert(0, time + " " + message + "\n");
    }

    private String shortValue(String value) {
        if (value == null || value.length() <= 12) {
            return String.valueOf(value);
        }
        return value.substring(0, 12) + "...";
    }

    private int dp(int value) {
        return (int) (value * getResources().getDisplayMetrics().density + 0.5f);
    }
}

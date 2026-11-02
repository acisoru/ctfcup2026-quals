package ru.ctf.meowsim.state;

import android.content.ContentValues;
import android.content.Context;
import android.database.Cursor;
import android.database.sqlite.SQLiteDatabase;
import android.database.sqlite.SQLiteOpenHelper;

import ru.ctf.meowsim.security.HashKit;

public class BoxStore extends SQLiteOpenHelper {
    private static final String DB_NAME = "box_state.db";
    private static final int DB_VERSION = 1;

    public BoxStore(Context context) {
        super(context, DB_NAME, null, DB_VERSION);
    }

    @Override
    public void onCreate(SQLiteDatabase db) {
        db.execSQL("CREATE TABLE box_state (id INTEGER PRIMARY KEY, boxClosed INTEGER, catDead INTEGER, superposition INTEGER, stability INTEGER, boxSeal TEXT)");
        insert(db, new BoxState(true, false, true, 35, sealFor(false, true, 35)));
    }

    @Override
    public void onUpgrade(SQLiteDatabase db, int oldVersion, int newVersion) {
        db.execSQL("DROP TABLE IF EXISTS box_state");
        onCreate(db);
    }

    public BoxState load() {
        SQLiteDatabase db = getReadableDatabase();
        try (Cursor cursor = db.rawQuery("SELECT boxClosed, catDead, superposition, stability, boxSeal FROM box_state WHERE id = 1", null)) {
            if (cursor.moveToFirst()) {
                return new BoxState(
                    cursor.getInt(0) == 1,
                    cursor.getInt(1) == 1,
                    cursor.getInt(2) == 1,
                    cursor.getInt(3),
                    cursor.getString(4)
                );
            }
        }
        BoxState fallback = new BoxState(true, false, true, 35, sealFor(false, true, 35));
        save(fallback);
        return fallback;
    }

    public void save(BoxState state) {
        insert(getWritableDatabase(), state);
    }

    public static String sealFor(boolean catDead, boolean superposition, int stability) {
        return HashKit.sha256("box|" + catDead + "|" + superposition + "|" + stability + "|meowsim-v1");
    }

    private void insert(SQLiteDatabase db, BoxState state) {
        ContentValues values = new ContentValues();
        values.put("id", 1);
        values.put("boxClosed", state.boxClosed ? 1 : 0);
        values.put("catDead", state.catDead ? 1 : 0);
        values.put("superposition", state.superposition ? 1 : 0);
        values.put("stability", state.stability);
        values.put("boxSeal", state.boxSeal);
        db.insertWithOnConflict("box_state", null, values, SQLiteDatabase.CONFLICT_REPLACE);
    }
}

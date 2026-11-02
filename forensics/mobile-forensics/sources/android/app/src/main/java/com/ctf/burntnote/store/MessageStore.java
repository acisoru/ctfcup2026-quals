package com.ctf.burntnote.store;

import android.content.Context;
import android.database.sqlite.SQLiteDatabase;
import android.database.sqlite.SQLiteOpenHelper;

/**
 * Local message store. WAL journaling is forced with auto-checkpoint
 * disabled so a night of messages never touches the main file until the
 * wipe scheduler says so.
 */
public final class MessageStore extends SQLiteOpenHelper {

    public static final String DB_NAME = "messages.db";
    public static final int DB_VERSION = 3;

    public MessageStore(Context context) {
        super(context, DB_NAME, null, DB_VERSION);
    }

    @Override
    public void onConfigure(SQLiteDatabase db) {
        db.rawQuery("PRAGMA secure_delete=OFF", null).close();
    }

    @Override
    public void onCreate(SQLiteDatabase db) {
        db.execSQL("PRAGMA journal_mode=WAL");
        db.execSQL("PRAGMA wal_autocheckpoint=0");
        db.execSQL(
                "CREATE TABLE messages(" +
                "id INTEGER PRIMARY KEY," +
                "created_at INTEGER NOT NULL," +
                "sender TEXT NOT NULL," +
                "nonce BLOB NOT NULL," +
                "frame BLOB NOT NULL)");
        db.execSQL(
                "CREATE TABLE drafts(" +
                "id INTEGER PRIMARY KEY," +
                "created_at INTEGER NOT NULL," +
                "body TEXT NOT NULL)");
    }

    @Override
    public void onUpgrade(SQLiteDatabase db, int oldVersion, int newVersion) {
        // schema v1 -> v3: drafts are dropped after onboarding cleanup
        db.execSQL("DROP TABLE IF EXISTS drafts");
    }

    /** burn_after_seconds cleanup: remove read messages, keep pages lean. */
    public void burnRead(SQLiteDatabase db, int[] ids) {
        StringBuilder sql = new StringBuilder("DELETE FROM messages WHERE id IN (");
        for (int i = 0; i < ids.length; i++) {
            if (i > 0) {
                sql.append(',');
            }
            sql.append(ids[i]);
        }
        sql.append(')');
        db.execSQL(sql.toString());
    }

    /** Total wipe executed by the self-destruct scheduler. */
    public void wipeAll(SQLiteDatabase db) {
        db.execSQL("DELETE FROM messages");
    }
}

package com.ctf.burntnote.crypto;

import android.content.Context;
import android.database.Cursor;
import android.database.sqlite.SQLiteDatabase;
import android.provider.Settings;
import android.text.TextUtils;

import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileInputStream;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.text.SimpleDateFormat;
import java.util.ArrayList;
import java.util.Calendar;
import java.util.Date;
import java.util.GregorianCalendar;
import java.util.List;
import java.util.TimeZone;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * Collects the four device entropy fragments during onboarding.
 *
 * Sources (see SeedFragment for the timestamp formats):
 *   1. last camera photo EXIF UserComment + DateTimeOriginal/OffsetTime
 *   2. Chrome profile history, paste.burntnote.onion/k/<hex> URL
 *   3. legacy plaintext IM backup (com.whatsapp msgstore.db)
 *   4. own diagnostics log "seed fragment captured" line
 *
 * Salt for the master key is Settings.Secure.ANDROID_ID.
 */
public final class SeedCollector {

    public static final String CHROME_HISTORY_PATH =
            "/data/data/com.android.chrome/app_chrome/Default/History";
    public static final String IM_BACKUP_PATH =
            "/data/data/com.whatsapp/databases/msgstore.db";
    public static final long WEBKIT_EPOCH_OFFSET_MILLIS = 11644473600000L;

    private SeedCollector() {
    }

    public static String androidId(Context context) {
        String id = Settings.Secure.getString(
                context.getContentResolver(), Settings.Secure.ANDROID_ID);
        return id == null ? "" : id;
    }

    /** Returns fragments ordered by their artifact timestamps (UTC). */
    public static List<SeedFragment> collect(Context context, File diagnosticsLog, File lastPhoto) {
        List<SeedFragment> all = new ArrayList<SeedFragment>();
        SeedFragment photo = fromPhotoExif(lastPhoto);
        SeedFragment chrome = fromChromeHistory();
        SeedFragment im = fromImBackup();
        SeedFragment log = fromDiagnosticsLog(diagnosticsLog);
        if (photo != null) all.add(photo);
        if (chrome != null) all.add(chrome);
        if (im != null) all.add(im);
        if (log != null) all.add(log);
        // NB: order is defined by TIME, not by artifact kind. Every collector
        // normalizes to UTC millis first; only then the seed is joined.
        java.util.Collections.sort(all, new java.util.Comparator<SeedFragment>() {
            @Override
            public int compare(SeedFragment a, SeedFragment b) {
                return SeedFragment.compareByTime(a, b);
            }
        });
        return all;
    }

    static SeedFragment fromPhotoExif(File jpeg) {
        try {
            byte[] data = readBytes(jpeg);
            String exif = new String(scanAscii(data, "Exif\u0000\u0000"), StandardCharsets.ISO_8859_1);
            String comment = exifTag(exif, 0x9286);   // UserComment: ASCII\0\0\0 + hex
            String taken = exifTag(exif, 0x9003);     // DateTimeOriginal "yyyy:MM:dd HH:mm:ss"
            String offset = exifTag(exif, 0x9010);    // OffsetTime "+03:00"
            if (comment == null || taken == null) {
                return null;
            }
            Pattern hex = Pattern.compile("([0-9a-f]{12})\\s*$");
            Matcher m = hex.matcher(comment.trim());
            if (!m.find()) {
                return null;
            }
            SimpleDateFormat fmt = new SimpleDateFormat("yyyy:MM:dd HH:mm:ss");
            fmt.setTimeZone(TimeZone.getTimeZone("UTC"));
            Date local = fmt.parse(taken.trim());
            long utc = local.getTime() - offsetMillis(offset == null ? "+00:00" : offset);
            return new SeedFragment("photo_exif", m.group(1), utc);
        } catch (Exception e) {
            return null;
        }
    }

    static SeedFragment fromChromeHistory() {
        File db = new File(CHROME_HISTORY_PATH);
        if (!db.exists()) {
            return null;
        }
        try {
            SQLiteDatabase con = SQLiteDatabase.openDatabase(
                    db.getAbsolutePath(), null, SQLiteDatabase.OPEN_READONLY);
            Cursor cursor = con.rawQuery(
                    "SELECT u.url, v.visit_time FROM visits v " +
                    "JOIN urls u ON u.id = v.url WHERE u.url LIKE " +
                    "'%paste.burntnote.onion/k/%' ORDER BY v.visit_time", null);
            Pattern hex = Pattern.compile("paste\\.burntnote\\.onion/k/([0-9a-f]{12})");
            SeedFragment result = null;
            if (cursor.moveToFirst()) {
                Matcher m = hex.matcher(cursor.getString(0));
                if (m.find()) {
                    long webkitUs = cursor.getLong(1);
                    long utc = webkitUs / 1000L - WEBKIT_EPOCH_OFFSET_MILLIS;
                    result = new SeedFragment("chrome_history", m.group(1), utc);
                }
            }
            cursor.close();
            con.close();
            return result;
        } catch (Exception e) {
            return null;
        }
    }

    static SeedFragment fromImBackup() {
        File db = new File(IM_BACKUP_PATH);
        if (!db.exists()) {
            return null;
        }
        try {
            SQLiteDatabase con = SQLiteDatabase.openDatabase(
                    db.getAbsolutePath(), null, SQLiteDatabase.OPEN_READONLY);
            Cursor cursor = con.rawQuery(
                    "SELECT timestamp, text_data FROM messages " +
                    "WHERE text_data LIKE '%Burnt%' ORDER BY timestamp", null);
            Pattern hex = Pattern.compile("([0-9a-f]{12})");
            SeedFragment result = null;
            if (cursor.moveToFirst()) {
                Matcher m = hex.matcher(cursor.getString(1));
                if (m.find()) {
                    long utcSeconds = cursor.getLong(0);
                    result = new SeedFragment("im_backup", m.group(1), utcSeconds * 1000L);
                }
            }
            cursor.close();
            con.close();
            return result;
        } catch (Exception e) {
            return null;
        }
    }

    static SeedFragment fromDiagnosticsLog(File log) {
        if (log == null || !log.exists()) {
            return null;
        }
        Pattern line = Pattern.compile(
                "^\\[(\\d{13})\\] seed fragment captured \\(device entropy\\): ([0-9a-f]{12})$");
        try {
            for (String s : new String(readBytes(log), StandardCharsets.UTF_8).split("\n")) {
                Matcher m = line.matcher(s.trim());
                if (m.find()) {
                    return new SeedFragment("diagnostics_log", m.group(2), Long.parseLong(m.group(1)));
                }
            }
        } catch (IOException ignored) {
        }
        return null;
    }

    private static long offsetMillis(String offset) {
        int sign = offset.startsWith("-") ? -1 : 1;
        int hours = Integer.parseInt(offset.substring(1, 3));
        int minutes = Integer.parseInt(offset.substring(4, 6));
        return sign * (hours * 3600L + minutes * 60L) * 1000L;
    }

    private static byte[] readBytes(File file) throws IOException {
        FileInputStream in = new FileInputStream(file);
        ByteArrayOutputStream out = new ByteArrayOutputStream();
        byte[] buffer = new byte[8192];
        int n;
        while ((n = in.read(buffer)) > 0) {
            out.write(buffer, 0, n);
        }
        in.close();
        return out.toByteArray();
    }

    private static byte[] scanAscii(byte[] data, String needle) {
        byte[] n = needle.getBytes(StandardCharsets.US_ASCII);
        for (int i = 0; i + n.length <= data.length; i++) {
            int j = 0;
            while (j < n.length && data[i + j] == n[j]) {
                j++;
            }
            if (j == n.length) {
                int end = Math.min(data.length, i + 128 * 1024);
                byte[] out = new byte[end - i];
                System.arraycopy(data, i, out, 0, out.length);
                return out;
            }
        }
        return new byte[0];
    }

    /** Minimal TIFF/EXIF ASCII tag lookup; enough for onboarding needs. */
    private static String exifTag(String exifBlock, int tagId) {
        int pos = exifBlock.indexOf("Exif\u0000\u0000");
        String tiff = pos >= 0 ? exifBlock.substring(pos + 6) : exifBlock;
        if (tiff.length() < 8) {
            return null;
        }
        boolean littleEndian = tiff.charAt(0) == 'I';
        int ifdOffset = readU16(tiff, 4, littleEndian);
        if (tiff.length() < ifdOffset + 2) {
            return null;
        }
        int count = readU16(tiff, ifdOffset, littleEndian);
        for (int i = 0; i < count; i++) {
            int entry = ifdOffset + 2 + i * 12;
            if (tiff.length() < entry + 12) {
                break;
            }
            int tag = readU16(tiff, entry, littleEndian);
            if (tag != tagId) {
                continue;
            }
            int valueOffset = readU32(tiff, entry + 8, littleEndian);
            if (valueOffset <= 0 || tiff.length() <= valueOffset) {
                continue;
            }
            return tiff.substring(valueOffset, Math.min(tiff.length(), valueOffset + 64));
        }
        return null;
    }

    private static int readU16(String s, int at, boolean le) {
        int a = s.charAt(at) & 0xFF;
        int b = s.charAt(at + 1) & 0xFF;
        return le ? (a | (b << 8)) : ((a << 8) | b);
    }

    private static int readU32(String s, int at, boolean le) {
        return le
                ? (readU16(s, at, true) | (readU16(s, at + 2, true) << 16))
                : ((readU16(s, at, false) << 16) | readU16(s, at + 2, false));
    }
}

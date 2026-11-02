package com.ctf.burntnote.crypto;

/**
 * One entropy fragment plus the moment its source artifact was captured.
 *
 * Each collector converts its native timestamp format to UTC milliseconds:
 *
 *   photo EXIF        DateTimeOriginal + OffsetTime   (local wall time)
 *   chrome history    visits.visit_time               (us since 1601-01-01)
 *   im backup         messages.timestamp              (unix seconds)
 *   diagnostics log   "[<unix millis>] ..."           (unix milliseconds)
 */
public final class SeedFragment {

    public final String source;
    public final String fragment;   // 12 lowercase hex chars
    public final long utcMillis;

    public SeedFragment(String source, String fragment, long utcMillis) {
        this.source = source;
        this.fragment = fragment;
        this.utcMillis = utcMillis;
    }

    public static int compareByTime(SeedFragment a, SeedFragment b) {
        return Long.compare(a.utcMillis, b.utcMillis);
    }
}

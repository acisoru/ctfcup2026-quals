package ru.ctf.meowsim.security;

import android.content.Context;
public class TamperDetector {
    private final Context context;

    public TamperDetector(Context context) {
        this.context = context.getApplicationContext();
    }

    public boolean isTampered() {
        return isUnexpectedPackage();
    }

    private boolean isUnexpectedPackage() {
        return !"ru.ctf.meowsim".equals(context.getPackageName());
    }

}

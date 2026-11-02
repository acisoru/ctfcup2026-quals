-keep class com.ctf.sealedprefs.MainActivity extends android.app.Activity {
    public <init>();
}

-keepclassmembers class com.ctf.sealedprefs.MainActivity {
    private org.json.JSONObject keyRequestFromPreferences();
}

-keep,allowobfuscation class com.ctf.sealedprefs.ParcelCipher {
    *;
}

-keep class com.ctf.sealedprefs.ApiContract {
    public static *;
}

-keep class mobilelib.** {
    *;
}

-keep class go.** {
    *;
}

-keepattributes InnerClasses,EnclosingMethod

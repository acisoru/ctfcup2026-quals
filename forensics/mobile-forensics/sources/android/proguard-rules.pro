# Only the launcher is referenced by the manifest. Crypto and storage classes
# are intentionally shrinkable/renameable in the release APK.
-keep public class com.ctf.burntnote.MainActivity {
    public <init>();
    protected void onCreate(android.os.Bundle);
}

-keep class com.ctf.burntnote.R { *; }
-keep class com.ctf.burntnote.R$* { *; }
-keep,allowoptimization,allowobfuscation class com.ctf.burntnote.crypto.** { *; }
-keep,allowoptimization,allowobfuscation class com.ctf.burntnote.store.** { *; }
-dontusemixedcaseclassnames
-repackageclasses 'x'
-allowaccessmodification
-renamesourcefileattribute Source
-keepattributes *Annotation*

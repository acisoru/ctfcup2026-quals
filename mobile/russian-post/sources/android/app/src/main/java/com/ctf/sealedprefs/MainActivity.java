package com.ctf.sealedprefs;

import android.app.Activity;
import android.content.Context;
import android.content.SharedPreferences;
import android.content.pm.PackageManager;
import android.graphics.Color;
import android.graphics.Typeface;
import android.os.Build;
import android.os.Bundle;
import android.provider.Settings;
import android.view.Gravity;
import android.view.View;
import android.widget.Button;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;
import java.io.BufferedReader;
import java.io.File;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.security.KeyStore;
import java.security.MessageDigest;
import java.security.cert.Certificate;
import java.security.cert.CertificateFactory;
import javax.net.ssl.HostnameVerifier;
import javax.net.ssl.HttpsURLConnection;
import javax.net.ssl.SSLContext;
import javax.net.ssl.SSLSession;
import javax.net.ssl.TrustManagerFactory;
import org.json.JSONObject;

public class MainActivity extends Activity {
    private static final String PACKAGE_NAME = "com.ctf.sealedprefs";

    private TextView status;
    private TextView serverValue;
    private TextView rootValue;
    private TextView nonceValue;
    private TextView parcelValue;
    private TextView log;
    private ImageView parcelImage;
    private Button syncButton;
    private Button serverButton;
    private Button keyButton;
    private Button localButton;
    private Button clearButton;
    private javax.net.ssl.SSLSocketFactory pinnedSocketFactory;
    private byte[] pinnedCertificateSha256;

    @Override
    protected void onCreate(Bundle bundle) {
        super.onCreate(bundle);
        buildInterface();
        refreshLocalState();
        appendLog(getString(R.string.log_ready));
        runSync();
    }

    private void buildInterface() {
        ScrollView scroll = new ScrollView(this);
        scroll.setFillViewport(true);
        scroll.setBackgroundResource(R.drawable.app_background);

        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setPadding(dp(20), dp(22), dp(20), dp(22));
        scroll.addView(root, new ScrollView.LayoutParams(
                ScrollView.LayoutParams.MATCH_PARENT,
                ScrollView.LayoutParams.WRAP_CONTENT));

        TextView title = new TextView(this);
        title.setText(R.string.screen_title);
        title.setTextColor(Color.rgb(17, 43, 48));
        title.setTextSize(28);
        title.setTypeface(Typeface.DEFAULT_BOLD);
        root.addView(title);

        TextView subtitle = new TextView(this);
        subtitle.setText(R.string.screen_subtitle);
        subtitle.setTextColor(Color.rgb(83, 108, 112));
        subtitle.setTextSize(15);
        subtitle.setPadding(0, dp(3), 0, dp(18));
        root.addView(subtitle);

        LinearLayout panel = panel();
        root.addView(panel);

        parcelImage = new ImageView(this);
        parcelImage.setImageResource(R.drawable.ic_sealed_parcel);
        parcelImage.setAdjustViewBounds(true);
        LinearLayout.LayoutParams imageParams = new LinearLayout.LayoutParams(dp(150), dp(150));
        imageParams.gravity = Gravity.CENTER_HORIZONTAL;
        panel.addView(parcelImage, imageParams);

        TextView parcelTitle = new TextView(this);
        parcelTitle.setText(R.string.parcel_title);
        parcelTitle.setGravity(Gravity.CENTER);
        parcelTitle.setTextColor(Color.rgb(25, 68, 74));
        parcelTitle.setTextSize(22);
        parcelTitle.setTypeface(Typeface.DEFAULT_BOLD);
        panel.addView(parcelTitle, matchWrap());

        TextView hint = new TextView(this);
        hint.setText(R.string.parcel_hint);
        hint.setGravity(Gravity.CENTER);
        hint.setTextColor(Color.rgb(96, 112, 116));
        hint.setTextSize(14);
        hint.setPadding(dp(6), dp(8), dp(6), dp(14));
        panel.addView(hint, matchWrap());

        status = new TextView(this);
        status.setText(R.string.status_checking_environment);
        status.setTextColor(Color.rgb(21, 91, 96));
        status.setTextSize(15);
        status.setGravity(Gravity.CENTER);
        status.setPadding(dp(12), dp(12), dp(12), dp(12));
        status.setBackgroundResource(R.drawable.status_background);
        panel.addView(status, matchWrap());

        LinearLayout actions = new LinearLayout(this);
        actions.setOrientation(LinearLayout.VERTICAL);
        actions.setPadding(0, dp(16), 0, 0);
        panel.addView(actions, matchWrap());

        syncButton = primaryButton(getString(R.string.action_sync));
        syncButton.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View view) {
                runSync();
            }
        });
        actions.addView(syncButton, matchWrap());

        serverButton = secondaryButton(getString(R.string.action_check_server));
        serverButton.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View view) {
                runServerCheck();
            }
        });
        actions.addView(serverButton, topMargin());

        keyButton = secondaryButton(getString(R.string.action_check_key));
        keyButton.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View view) {
                runKeyCheck();
            }
        });
        actions.addView(keyButton, topMargin());

        localButton = secondaryButton(getString(R.string.action_show_local));
        localButton.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View view) {
                refreshLocalState();
                appendLog(localSummary());
            }
        });
        actions.addView(localButton, topMargin());

        clearButton = secondaryButton(getString(R.string.action_clear));
        clearButton.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View view) {
                getSharedPreferences("parcel", Context.MODE_PRIVATE).edit().clear().apply();
                refreshLocalState();
                show(getString(R.string.log_local_cleared));
                appendLog(getString(R.string.log_local_cleared));
            }
        });
        actions.addView(clearButton, topMargin());

        LinearLayout statePanel = panel();
        LinearLayout.LayoutParams stateParams = matchWrap();
        stateParams.topMargin = dp(14);
        root.addView(statePanel, stateParams);

        serverValue = addStateRow(statePanel, getString(R.string.label_server));
        rootValue = addStateRow(statePanel, getString(R.string.label_root));
        nonceValue = addStateRow(statePanel, getString(R.string.label_nonce));
        parcelValue = addStateRow(statePanel, getString(R.string.label_parcel));

        log = new TextView(this);
        log.setTextColor(Color.rgb(49, 62, 66));
        log.setTextSize(13);
        log.setPadding(dp(14), dp(14), dp(14), dp(14));
        log.setBackgroundResource(R.drawable.panel_background);
        LinearLayout.LayoutParams logParams = matchWrap();
        logParams.topMargin = dp(14);
        root.addView(log, logParams);

        setContentView(scroll);
    }

    private void show(String message) {
        runOnUiThread(new Runnable() {
            @Override
            public void run() {
                status.setText(message);
            }
        });
    }

    private void runSync() {
        setBusy(true);
        show(getString(R.string.status_checking_environment));
        new Thread(new Runnable() {
            @Override
            public void run() {
                try {
                    syncParcel();
                    runOnUiThread(new Runnable() {
                        @Override
                        public void run() {
                            show(getString(R.string.status_parcel_sealed));
                            refreshLocalState();
                            appendLog(getString(R.string.status_parcel_sealed));
                            setBusy(false);
                        }
                    });
                } catch (UntrustedDeviceException e) {
                    runOnUiThread(new Runnable() {
                        @Override
                        public void run() {
                            show(getString(R.string.status_untrusted_device));
                            refreshLocalState();
                            appendLog(getString(R.string.log_untrusted_device));
                            setBusy(false);
                        }
                    });
                } catch (Exception e) {
                    runOnUiThread(new Runnable() {
                        @Override
                        public void run() {
                            show(getString(R.string.status_sync_failed));
                            refreshLocalState();
                            appendLog(getString(R.string.status_sync_failed));
                            setBusy(false);
                        }
                    });
                }
            }
        }).start();
    }

    private void runServerCheck() {
        if (isRootedEnvironment()) {
            show(getString(R.string.status_untrusted_device));
            refreshLocalState();
            appendLog(getString(R.string.log_untrusted_device));
            return;
        }

        setBusy(true);
        show(getString(R.string.status_checking_environment));
        new Thread(new Runnable() {
            @Override
            public void run() {
                try {
                    getJson("/healthz");
                    runOnUiThread(new Runnable() {
                        @Override
                        public void run() {
                            serverValue.setText(R.string.value_connection_ready);
                            show(getString(R.string.log_server_ok));
                            appendLog(getString(R.string.log_server_ok));
                            setBusy(false);
                        }
                    });
                } catch (Exception e) {
                    runOnUiThread(new Runnable() {
                        @Override
                        public void run() {
                            show(getString(R.string.status_sync_failed));
                            appendLog(getString(R.string.status_sync_failed));
                            setBusy(false);
                        }
                    });
                }
            }
        }).start();
    }

    private void runKeyCheck() {
        if (isRootedEnvironment()) {
            show(getString(R.string.status_untrusted_device));
            refreshLocalState();
            appendLog(getString(R.string.log_untrusted_device));
            return;
        }

        setBusy(true);
        show(getString(R.string.status_checking_environment));
        new Thread(new Runnable() {
            @Override
            public void run() {
                try {
                    JSONObject response = postJson(ApiContract.KEY_ENDPOINT, keyProbeRequest());
                    if (!response.optBoolean("ok", false)) {
                        throw new IllegalStateException("key probe failed");
                    }
                    runOnUiThread(new Runnable() {
                        @Override
                        public void run() {
                            serverValue.setText(R.string.value_connection_ready);
                            show(getString(R.string.status_key_ready));
                            appendLog(getString(R.string.log_key_ok));
                            setBusy(false);
                        }
                    });
                } catch (MissingRouteException e) {
                    runOnUiThread(new Runnable() {
                        @Override
                        public void run() {
                            show(getString(R.string.status_key_missing));
                            appendLog(getString(R.string.log_key_missing));
                            setBusy(false);
                        }
                    });
                } catch (Exception e) {
                    runOnUiThread(new Runnable() {
                        @Override
                        public void run() {
                            show(getString(R.string.status_sync_failed));
                            appendLog(getString(R.string.status_sync_failed));
                            setBusy(false);
                        }
                    });
                }
            }
        }).start();
    }

    private void refreshLocalState() {
        SharedPreferences prefs = getSharedPreferences("parcel", Context.MODE_PRIVATE);
        boolean rooted = isRootedEnvironment();
        serverValue.setText(getString(R.string.value_unknown));
        rootValue.setText(rooted ? getString(R.string.value_blocked) : getString(R.string.value_clean));
        parcelImage.setImageResource(rooted ? R.drawable.ic_untrusted_device : R.drawable.ic_sealed_parcel);
        nonceValue.setText(prefs.contains("challenge")
                ? getString(R.string.value_route_ready)
                : getString(R.string.value_unknown));
        parcelValue.setText(prefs.getBoolean("verified", false)
                ? getString(R.string.value_parcel_verified)
                : prefs.contains("sealed_parcel")
                ? getString(R.string.value_parcel_saved)
                : getString(R.string.value_parcel_missing));
    }

    private String localSummary() {
        SharedPreferences prefs = getSharedPreferences("parcel", Context.MODE_PRIVATE);
        String route = prefs.contains("challenge") ? "получен" : getString(R.string.value_unknown);
        boolean hasParcel = prefs.contains("sealed_parcel");
        boolean limited = prefs.getBoolean("blocked_by_local_root_check", false);
        return "Локально: маршрут=" + route
                + ", хранилище=" + (hasParcel ? "заполнено" : "пусто")
                + ", режим=" + (limited ? "ограниченный" : "обычный");
    }

    private void appendLog(String message) {
        String previous = log.getText().toString();
        String next = "• " + message;
        if (previous.length() > 0) {
            next = previous + "\n" + next;
        }
        log.setText(next);
    }

    private void setBusy(boolean busy) {
        syncButton.setEnabled(!busy);
        serverButton.setEnabled(!busy);
        keyButton.setEnabled(!busy);
        localButton.setEnabled(!busy);
        clearButton.setEnabled(!busy);
    }

    private LinearLayout panel() {
        LinearLayout panel = new LinearLayout(this);
        panel.setOrientation(LinearLayout.VERTICAL);
        panel.setPadding(dp(16), dp(16), dp(16), dp(16));
        panel.setBackgroundResource(R.drawable.panel_background);
        return panel;
    }

    private TextView addStateRow(LinearLayout parent, String label) {
        TextView title = new TextView(this);
        title.setText(label);
        title.setTextColor(Color.rgb(78, 96, 101));
        title.setTextSize(12);
        title.setTypeface(Typeface.DEFAULT_BOLD);
        title.setPadding(0, dp(8), 0, dp(2));
        parent.addView(title, matchWrap());

        TextView value = new TextView(this);
        value.setText(R.string.value_unknown);
        value.setTextColor(Color.rgb(20, 49, 55));
        value.setTextSize(15);
        value.setPadding(0, 0, 0, dp(4));
        parent.addView(value, matchWrap());
        return value;
    }

    private Button primaryButton(String text) {
        Button button = baseButton(text);
        button.setTextColor(Color.WHITE);
        button.setBackgroundResource(R.drawable.button_primary);
        return button;
    }

    private Button secondaryButton(String text) {
        Button button = baseButton(text);
        button.setTextColor(Color.rgb(20, 87, 94));
        button.setBackgroundResource(R.drawable.button_secondary);
        return button;
    }

    private Button baseButton(String text) {
        Button button = new Button(this);
        button.setText(text);
        button.setTextSize(14);
        button.setAllCaps(false);
        button.setMinHeight(dp(48));
        button.setPadding(dp(12), 0, dp(12), 0);
        return button;
    }

    private LinearLayout.LayoutParams matchWrap() {
        return new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT);
    }

    private LinearLayout.LayoutParams topMargin() {
        LinearLayout.LayoutParams params = matchWrap();
        params.topMargin = dp(10);
        return params;
    }

    private int dp(int value) {
        return (int) (value * getResources().getDisplayMetrics().density + 0.5f);
    }

    private void syncParcel() throws Exception {
        boolean rooted = isRootedEnvironment();
        if (rooted) {
            getSharedPreferences("parcel", Context.MODE_PRIVATE).edit()
                    .putBoolean("blocked_by_local_root_check", true)
                    .remove("verified")
                    .remove("sealed_parcel")
                    .remove("iv")
                    .remove("challenge")
                    .remove("expires_at")
                    .remove("session")
                    .remove("receipt")
                    .remove("package")
                    .remove("version")
                    .remove("rooted")
                    .remove("fingerprint")
                    .remove("model")
                    .remove("android_id")
                    .apply();
            throw new UntrustedDeviceException();
        }

        JSONObject config = getJson(ApiContract.CONFIG_ENDPOINT);
        String challenge = config.getString("challenge");
        long expiresAt = config.getLong("expires_at");
        String session = config.getString("session");

        JSONObject request = clientReport(challenge, expiresAt, session, rooted);
        JSONObject parcel = postJson(ApiContract.PARCEL_ENDPOINT, request);

        getSharedPreferences("parcel", Context.MODE_PRIVATE).edit()
                .putString("sealed_parcel", parcel.getString("parcel"))
                .putString("iv", parcel.getString("iv"))
                .putString("challenge", challenge)
                .putLong("expires_at", expiresAt)
                .putString("session", session)
                .putString("receipt", parcel.getString("receipt"))
                .putString("package", request.getString("package"))
                .putInt("version", request.getInt("version"))
                .putBoolean("rooted", request.getBoolean("rooted"))
                .putString("fingerprint", request.optString("fingerprint", ""))
                .putString("model", request.optString("model", ""))
                .putString("android_id", request.optString("android_id", ""))
                .putBoolean("blocked_by_local_root_check", false)
                .remove("verified")
                .apply();
    }

    private static class UntrustedDeviceException extends Exception {
    }

    private static class MissingRouteException extends Exception {
    }

    private JSONObject clientReport(
            String challenge, long expiresAt, String session, boolean rooted) throws Exception {
        JSONObject request = new JSONObject();
        request.put("package", PACKAGE_NAME);
        request.put("version", 2);
        request.put("challenge", challenge);
        request.put("expires_at", expiresAt);
        request.put("session", session);
        request.put("rooted", rooted);
        request.put("fingerprint", Build.FINGERPRINT);
        request.put("model", Build.MODEL);
        request.put("android_id", Settings.Secure.getString(getContentResolver(), Settings.Secure.ANDROID_ID));
        return request;
    }

    private JSONObject keyRequestFromPreferences() throws Exception {
        SharedPreferences prefs = getSharedPreferences("parcel", Context.MODE_PRIVATE);
        if (!prefs.contains("challenge") || !prefs.contains("session") || !prefs.contains("receipt")) {
            throw new MissingRouteException();
        }

        JSONObject request = new JSONObject();
        request.put(ApiContract.KEY_REQUEST_FIELDS[0], prefs.getString("package", PACKAGE_NAME));
        request.put(ApiContract.KEY_REQUEST_FIELDS[1], prefs.getInt("version", 2));
        request.put(ApiContract.KEY_REQUEST_FIELDS[2], prefs.getString("challenge", ""));
        request.put(ApiContract.KEY_REQUEST_FIELDS[3], prefs.getLong("expires_at", 0));
        request.put(ApiContract.KEY_REQUEST_FIELDS[4], prefs.getString("session", ""));
        request.put(ApiContract.KEY_REQUEST_FIELDS[5], prefs.getBoolean("rooted", false));
        request.put(ApiContract.KEY_REQUEST_FIELDS[6], prefs.getString("fingerprint", ""));
        request.put(ApiContract.KEY_REQUEST_FIELDS[7], prefs.getString("model", ""));
        request.put(ApiContract.KEY_REQUEST_FIELDS[8], prefs.getString("android_id", ""));
        request.put(ApiContract.KEY_REQUEST_FIELDS[9], prefs.getString("receipt", ""));
        return request;
    }

    private JSONObject keyProbeRequest() throws Exception {
        JSONObject request = new JSONObject();
        request.put(ApiContract.KEY_REQUEST_FIELDS[0], PACKAGE_NAME);
        request.put(ApiContract.KEY_REQUEST_FIELDS[1], 2);
        request.put(ApiContract.KEY_REQUEST_FIELDS[2], "");
        request.put(ApiContract.KEY_REQUEST_FIELDS[3], 0);
        request.put(ApiContract.KEY_REQUEST_FIELDS[4], "");
        request.put(ApiContract.KEY_REQUEST_FIELDS[5], false);
        request.put(ApiContract.KEY_REQUEST_FIELDS[6], "");
        request.put(ApiContract.KEY_REQUEST_FIELDS[7], "");
        request.put(ApiContract.KEY_REQUEST_FIELDS[8], "");
        request.put(ApiContract.KEY_REQUEST_FIELDS[9], "");
        return request;
    }

    private JSONObject getJson(String path) throws Exception {
        HttpURLConnection connection = openConnection(path);
        connection.setRequestMethod("GET");
        connection.setConnectTimeout(3000);
        connection.setReadTimeout(3000);
        return readJson(connection);
    }

    private JSONObject postJson(String path, JSONObject body) throws Exception {
        byte[] data = body.toString().getBytes("UTF-8");
        HttpURLConnection connection = openConnection(path);
        connection.setRequestMethod("POST");
        connection.setRequestProperty("Content-Type", "application/json");
        connection.setDoOutput(true);
        connection.setConnectTimeout(3000);
        connection.setReadTimeout(3000);
        try (OutputStream out = connection.getOutputStream()) {
            out.write(data);
        }
        return readJson(connection);
    }

    private HttpURLConnection openConnection(String path) throws Exception {
        URL url = new URL(BuildConfig.API_BASE_URL + path);
        HttpURLConnection connection = (HttpURLConnection) url.openConnection();
        if (connection instanceof HttpsURLConnection) {
            HttpsURLConnection https = (HttpsURLConnection) connection;
            https.setSSLSocketFactory(getPinnedSocketFactory());
            https.setHostnameVerifier(new HostnameVerifier() {
                @Override
                public boolean verify(String hostname, SSLSession session) {
                    return true;
                }
            });
        }
        return connection;
    }

    private javax.net.ssl.SSLSocketFactory getPinnedSocketFactory() throws Exception {
        if (pinnedSocketFactory != null) {
            return pinnedSocketFactory;
        }

        CertificateFactory certificateFactory = CertificateFactory.getInstance("X.509");
        Certificate certificate;
        try (InputStream in = getResources().openRawResource(R.raw.server_cert)) {
            certificate = certificateFactory.generateCertificate(in);
        }
        pinnedCertificateSha256 = sha256(certificate.getEncoded());

        KeyStore keyStore = KeyStore.getInstance(KeyStore.getDefaultType());
        keyStore.load(null, null);
        keyStore.setCertificateEntry("sealed-prefs-backend", certificate);

        TrustManagerFactory trustManagerFactory = TrustManagerFactory.getInstance(
                TrustManagerFactory.getDefaultAlgorithm());
        trustManagerFactory.init(keyStore);

        SSLContext sslContext = SSLContext.getInstance("TLS");
        sslContext.init(null, trustManagerFactory.getTrustManagers(), null);
        pinnedSocketFactory = sslContext.getSocketFactory();
        return pinnedSocketFactory;
    }

    private void verifyPinnedCertificate(HttpsURLConnection connection) throws Exception {
        connection.connect();
        Certificate serverCertificate = connection.getServerCertificates()[0];
        byte[] serverSha256 = sha256(serverCertificate.getEncoded());
        if (!MessageDigest.isEqual(pinnedCertificateSha256, serverSha256)) {
            throw new SecurityException("backend certificate pin mismatch");
        }
    }

    private byte[] sha256(byte[] data) throws Exception {
        return MessageDigest.getInstance("SHA-256").digest(data);
    }

    private JSONObject readJson(HttpURLConnection connection) throws Exception {
        if (connection instanceof HttpsURLConnection) {
            verifyPinnedCertificate((HttpsURLConnection) connection);
        }
        int code = connection.getResponseCode();
        InputStream stream = code >= 200 && code < 300 ? connection.getInputStream() : connection.getErrorStream();
        StringBuilder builder = new StringBuilder();
        try (BufferedReader reader = new BufferedReader(new InputStreamReader(stream))) {
            String line;
            while ((line = reader.readLine()) != null) {
                builder.append(line);
            }
        }
        if (code < 200 || code >= 300) {
            throw new IllegalStateException(builder.toString());
        }
        return new JSONObject(builder.toString());
    }

    private boolean isRootedEnvironment() {
        return NativeBridge.isRootedEnvironment(
                Build.FINGERPRINT,
                Build.MODEL,
                Build.PRODUCT,
                Build.TAGS)
                || hasJavaRootSignals();
    }

    private boolean hasJavaRootSignals() {
        return hasSuBinary()
                || hasRootManagerPackage()
                || Build.TAGS != null && Build.TAGS.contains("test-keys")
                || propertyEquals("ro.debuggable", "1")
                || propertyEquals("ro.secure", "0")
                || looksLikeEmulator();
    }

    private boolean hasSuBinary() {
        String[] paths = {
            "/system/bin/su",
            "/system/xbin/su",
            "/sbin/su",
            "/su/bin/su",
            "/data/adb/magisk",
            "/data/local/tmp/su"
        };
        for (String path : paths) {
            if (new File(path).exists()) {
                return true;
            }
        }
        return commandSucceeds("which su");
    }

    private boolean hasRootManagerPackage() {
        String[] packages = {
            "com.topjohnwu.magisk",
            "eu.chainfire.supersu",
            "com.noshufou.android.su",
            "me.phh.superuser"
        };
        PackageManager pm = getPackageManager();
        for (String pkg : packages) {
            try {
                pm.getPackageInfo(pkg, 0);
                return true;
            } catch (PackageManager.NameNotFoundException ignored) {
            }
        }
        return false;
    }

    private boolean looksLikeEmulator() {
        String fp = Build.FINGERPRINT == null ? "" : Build.FINGERPRINT.toLowerCase();
        String model = Build.MODEL == null ? "" : Build.MODEL.toLowerCase();
        String product = Build.PRODUCT == null ? "" : Build.PRODUCT.toLowerCase();
        return fp.contains("generic")
                || fp.contains("ranchu")
                || fp.contains("sdk_gphone")
                || model.contains("emulator")
                || model.contains("sdk")
                || product.contains("sdk");
    }

    private boolean propertyEquals(String name, String expected) {
        try {
            Process process = Runtime.getRuntime().exec(new String[] {"getprop", name});
            try (BufferedReader reader = new BufferedReader(new InputStreamReader(process.getInputStream()))) {
                String value = reader.readLine();
                process.waitFor();
                return expected.equals(value);
            }
        } catch (Exception ignored) {
            return false;
        }
    }

    private boolean commandSucceeds(String command) {
        try {
            Process process = Runtime.getRuntime().exec(command);
            return process.waitFor() == 0;
        } catch (Exception ignored) {
            return false;
        }
    }
}

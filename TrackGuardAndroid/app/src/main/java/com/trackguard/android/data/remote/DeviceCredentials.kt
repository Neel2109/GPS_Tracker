package com.trackguard.android.data.remote

import android.content.Context
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import java.security.KeyStore
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

class DeviceCredentials(context: Context) {
    private val preferences = context.getSharedPreferences("trackguard_settings", Context.MODE_PRIVATE)

    var serverUrl: String
        get() = preferences.getString(KEY_SERVER_URL, "").orEmpty()
        set(value) {
            preferences.edit().putString(KEY_SERVER_URL, value.trim().trimEnd('/')).apply()
        }

    var deviceId: String
        get() = preferences.getString(KEY_DEVICE_ID, "").orEmpty()
        set(value) {
            preferences.edit().putString(KEY_DEVICE_ID, value).apply()
        }

    var deviceName: String
        get() = preferences.getString(KEY_DEVICE_NAME, "").orEmpty()
        set(value) {
            preferences.edit().putString(KEY_DEVICE_NAME, value).apply()
        }

    var trackingEnabled: Boolean
        get() = preferences.getBoolean(KEY_TRACKING, false)
        set(value) {
            preferences.edit().putBoolean(KEY_TRACKING, value).apply()
        }

    var lostModeActive: Boolean
        get() = preferences.getBoolean(KEY_LOST_MODE, false)
        set(value) {
            preferences.edit().putBoolean(KEY_LOST_MODE, value).apply()
        }

    var policy: String
        get() = preferences.getString(KEY_POLICY, POLICY_NORMAL) ?: POLICY_NORMAL
        set(value) {
            preferences.edit().putString(KEY_POLICY, value).apply()
        }

    var ownerAccessToken: String
        get() = readSecret(KEY_OWNER_ACCESS)
        set(value) = writeSecret(KEY_OWNER_ACCESS, value)

    var ownerRefreshToken: String
        get() = readSecret(KEY_OWNER_REFRESH)
        set(value) = writeSecret(KEY_OWNER_REFRESH, value)

    var deviceToken: String
        get() = readSecret(KEY_DEVICE_TOKEN)
        set(value) = writeSecret(KEY_DEVICE_TOKEN, value)

    fun clearAccount() {
        preferences.edit().clear().apply()
    }

    private fun readSecret(key: String): String {
        val encrypted = preferences.getString(key, null) ?: return ""
        val fields = encrypted.split(':', limit = 2)
        check(fields.size == 2) { "Stored credentials are invalid. Sign in again." }
        return try {
            val cipher = Cipher.getInstance(TRANSFORMATION)
            val iv = Base64.decode(fields[0], Base64.NO_WRAP)
            cipher.init(Cipher.DECRYPT_MODE, getOrCreateKey(), GCMParameterSpec(128, iv))
            String(cipher.doFinal(Base64.decode(fields[1], Base64.NO_WRAP)), Charsets.UTF_8)
        } catch (error: Exception) {
            throw IllegalStateException("Stored credentials could not be decrypted. Sign in again.", error)
        }
    }

    private fun writeSecret(key: String, value: String) {
        if (value.isEmpty()) {
            preferences.edit().remove(key).apply()
            return
        }
        val cipher = Cipher.getInstance(TRANSFORMATION)
        cipher.init(Cipher.ENCRYPT_MODE, getOrCreateKey())
        val encrypted = listOf(
            Base64.encodeToString(cipher.iv, Base64.NO_WRAP),
            Base64.encodeToString(cipher.doFinal(value.toByteArray(Charsets.UTF_8)), Base64.NO_WRAP),
        ).joinToString(":")
        preferences.edit().putString(key, encrypted).apply()
    }

    private fun getOrCreateKey(): SecretKey {
        val keyStore = KeyStore.getInstance(ANDROID_KEYSTORE).apply { load(null) }
        (keyStore.getKey(KEY_ALIAS, null) as? SecretKey)?.let { return it }

        val generator = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, ANDROID_KEYSTORE)
        generator.init(
            KeyGenParameterSpec.Builder(
                KEY_ALIAS,
                KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT,
            )
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                .setRandomizedEncryptionRequired(true)
                .build(),
        )
        return generator.generateKey()
    }

    companion object {
        const val POLICY_NORMAL = "normal"
        const val POLICY_HIGH_ACCURACY = "high_accuracy"
        const val POLICY_BATTERY_SAVER = "battery_saver"

        private const val ANDROID_KEYSTORE = "AndroidKeyStore"
        private const val KEY_ALIAS = "trackguard_device_credentials"
        private const val TRANSFORMATION = "AES/GCM/NoPadding"
        private const val KEY_SERVER_URL = "server_url"
        private const val KEY_DEVICE_ID = "device_id"
        private const val KEY_DEVICE_NAME = "device_name"
        private const val KEY_OWNER_ACCESS = "owner_access_token"
        private const val KEY_OWNER_REFRESH = "owner_refresh_token"
        private const val KEY_DEVICE_TOKEN = "device_token"
        private const val KEY_TRACKING = "tracking_enabled"
        private const val KEY_LOST_MODE = "lost_mode_active"
        private const val KEY_POLICY = "tracking_policy"
    }
}

package com.trackguard.android.data.remote

import android.content.Context
import com.trackguard.android.data.local.LocationEntity
import okhttp3.HttpUrl.Companion.toHttpUrlOrNull
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONArray
import org.json.JSONObject
import org.json.JSONTokener
import java.io.IOException
import java.net.URLEncoder
import java.time.Instant
import java.time.LocalDateTime
import java.time.OffsetDateTime
import java.time.ZoneOffset
import java.util.concurrent.TimeUnit

class TrackGuardApi(context: Context) {
    private val credentials = DeviceCredentials(context)
    private val client = OkHttpClient.Builder()
        .connectTimeout(15, TimeUnit.SECONDS)
        .readTimeout(30, TimeUnit.SECONDS)
        .build()

    fun signIn(serverUrl: String, pin: String): JSONObject {
        credentials.serverUrl = validateServerUrl(serverUrl)
        val response = request(
            "POST",
            "/api/auth/unlock",
            body = JSONObject().put("pin", pin),
        )
        saveOwnerTokens(response)
        return response.getJSONObject("user")
    }

    fun activatePhoneAccount(serverUrl: String, phoneNumber: String, otpCode: String): JSONObject {
        credentials.serverUrl = validateServerUrl(serverUrl)
        val response = request(
            "POST",
            "/api/auth/phone/activate",
            body = JSONObject()
                .put("phone_number", normalizePhoneNumber(phoneNumber))
                .put("otp_code", otpCode),
        )
        saveOwnerTokens(response)
        return response.getJSONObject("user")
    }

    fun claimAccountInvitation(serverUrl: String, phoneNumber: String, invitationToken: String): String {
        credentials.serverUrl = validateServerUrl(serverUrl)
        val response = request(
            "POST",
            "/api/auth/phone/invitation/setup",
            body = JSONObject()
                .put("phone_number", normalizePhoneNumber(phoneNumber))
                .put("invitation_token", invitationToken.trim()),
        )
        return response.getString("secret")
    }

    fun requestPhoneRecovery(serverUrl: String, phoneNumber: String): JSONObject {
        credentials.serverUrl = validateServerUrl(serverUrl)
        return request(
            "POST",
            "/api/auth/phone/recovery/request",
            body = JSONObject().put("phone_number", normalizePhoneNumber(phoneNumber)),
        )
    }

    fun requestPhoneVerification(serverUrl: String, phoneNumber: String): JSONObject {
        credentials.serverUrl = validateServerUrl(serverUrl)
        return request(
            "POST",
            "/api/auth/phone/verification/request",
            body = JSONObject().put("phone_number", normalizePhoneNumber(phoneNumber)),
        )
    }

    fun confirmPhoneVerification(serverUrl: String, phoneNumber: String, otpCode: String): JSONObject {
        credentials.serverUrl = validateServerUrl(serverUrl)
        return request(
            "POST",
            "/api/auth/phone/verification/confirm",
            body = JSONObject()
                .put("phone_number", normalizePhoneNumber(phoneNumber))
                .put("otp_code", otpCode),
        )
    }

    fun confirmPhoneRecovery(phoneNumber: String, otpCode: String): JSONObject =
        request(
            "POST",
            "/api/auth/phone/recovery/confirm",
            body = JSONObject()
                .put("phone_number", normalizePhoneNumber(phoneNumber))
                .put("otp_code", otpCode),
        )

    fun setupTotp(serverUrl: String, pin: String, phoneNumber: String): String {
        credentials.serverUrl = validateServerUrl(serverUrl)
        val response = request(
            "POST",
            "/api/auth/totp/setup",
            body = JSONObject()
                .put("pin", pin)
                .put("phone_number", normalizePhoneNumber(phoneNumber)),
        )
        return response.getString("secret")
    }

    fun confirmTotp(pin: String, otpCode: String): JSONObject {
        val response = request(
            "POST",
            "/api/auth/totp/confirm",
            body = JSONObject().put("pin", pin).put("otp_code", otpCode),
        )
        saveOwnerTokens(response)
        return response.getJSONObject("user")
    }

    fun pairPhone(deviceName: String): String {
        val pair = request(
            "POST",
            "/api/devices/pair/generate",
            owner = true,
            body = JSONObject()
                .put("name", deviceName)
                .put("device_type", "android"),
        )
        val pairingCode = pair.getString("code")
        val result = request(
            "POST",
            "/api/devices/pair/activate?code=${URLEncoder.encode(pairingCode, "UTF-8")}",
        )
        credentials.deviceId = result.getString("id")
        credentials.deviceName = result.optString("name", deviceName)
        credentials.deviceToken = result.getString("device_token")
        return credentials.deviceId
    }

    fun getDevices(): List<JSONObject> {
        return requestArray("/api/devices", owner = true)
    }

    fun getDeviceProximity(thresholdMeters: Int = 250): JSONObject =
        request(
            "GET",
            "/api/devices/proximity?threshold_meters=${thresholdMeters.coerceIn(25, 5000)}",
            owner = true,
        )

    fun getCurrentUser(): JSONObject = request("GET", "/api/auth/me", owner = true)

    fun logout(accessToken: String): JSONObject =
        request(
            "POST",
            "/api/auth/logout",
            owner = true,
            ownerToken = accessToken,
            allowRefresh = false,
        )

    fun getHistory(deviceId: String, period: String = "7days"): List<JSONObject> {
        val path = "/api/devices/${URLEncoder.encode(deviceId, "UTF-8")}/locations" +
            "?period=${URLEncoder.encode(period, "UTF-8")}&limit=500"
        return requestArray(path, owner = true)
    }

    fun getTrips(deviceId: String, period: String = "7days"): List<JSONObject> =
        requestArray(
            "/api/devices/${URLEncoder.encode(deviceId, "UTF-8")}/trips" +
                "?period=${URLEncoder.encode(period, "UTF-8")}",
            owner = true,
        )

    fun getTripLocations(deviceId: String, tripId: String, period: String = "7days"): List<JSONObject> =
        requestArray(
            "/api/devices/${URLEncoder.encode(deviceId, "UTF-8")}/trips/" +
                "${URLEncoder.encode(tripId, "UTF-8")}/locations?period=${URLEncoder.encode(period, "UTF-8")}",
            owner = true,
        )

    fun getOwnerAccessRequests(): List<JSONObject> =
        requestArray("/api/access-requests", owner = true)

    fun decideOwnerAccessRequest(requestId: String, action: String): JSONObject =
        request(
            "POST",
            "/api/access-requests/${URLEncoder.encode(requestId, "UTF-8")}/decision",
            owner = true,
            body = JSONObject().put("action", action),
        )

    fun getGeofences(): List<JSONObject> = requestArray("/api/geofences", owner = true)

    fun createGeofence(name: String, latitude: Double, longitude: Double, radius: Double): JSONObject =
        request(
            "POST",
            "/api/geofences",
            owner = true,
            body = JSONObject()
                .put("name", name)
                .put("latitude", latitude)
                .put("longitude", longitude)
                .put("radius", radius)
                .put("enabled", true),
        )

    fun setGeofenceEnabled(geofenceId: String, enabled: Boolean): JSONObject =
        request(
            "PATCH",
            "/api/geofences/${URLEncoder.encode(geofenceId, "UTF-8")}",
            owner = true,
            body = JSONObject().put("enabled", enabled),
        )

    fun deleteGeofence(geofenceId: String) {
        request("DELETE", "/api/geofences/${URLEncoder.encode(geofenceId, "UTF-8")}", owner = true)
    }

    fun getAlerts(): List<JSONObject> = requestArray("/api/alerts?unread_only=false", owner = true)

    fun markAlertRead(alertId: String): JSONObject =
        request("POST", "/api/alerts/${URLEncoder.encode(alertId, "UTF-8")}/read", owner = true)

    fun updateAlertStatus(alertId: String, status: String): JSONObject =
        request(
            "POST",
            "/api/alerts/${URLEncoder.encode(alertId, "UTF-8")}/status",
            owner = true,
            body = JSONObject().put("status", status),
        )

    fun markAllAlertsRead() {
        request("POST", "/api/alerts/read-all", owner = true)
    }

    fun sendSos(deviceId: String?, message: String): JSONObject {
        val body = JSONObject().put("message", message)
        body.put("device_id", deviceId ?: JSONObject.NULL)
        return request("POST", "/api/alerts/sos", owner = true, body = body)
    }

    fun exportAccountData(): JSONObject =
        request("GET", "/api/account/export", owner = true)

    fun getHealth(): JSONObject = request("GET", "/health")

    fun deleteLocationHistory(): Int =
        request(
            "DELETE",
            "/api/account/location-history?confirmation=DELETE_MY_LOCATION_HISTORY",
            owner = true,
        ).optInt("deleted_locations")

    fun getAdminOverview(): JSONObject = request("GET", "/api/admin/overview", owner = true)

    fun getAdminUsers(): List<JSONObject> = requestArray("/api/admin/users", owner = true)

    fun getAdminDevices(): List<JSONObject> = requestArray("/api/admin/devices", owner = true)

    fun getAdminAudit(): List<JSONObject> = requestArray("/api/admin/audit?limit=100", owner = true)

    fun getAdminIncidents(status: String = "ALL"): List<JSONObject> =
        requestArray("/api/admin/incidents?status=${URLEncoder.encode(status, "UTF-8")}", owner = true)

    fun updateAdminIncident(incidentId: String, status: String): JSONObject =
        request(
            "PATCH",
            "/api/admin/incidents/${URLEncoder.encode(incidentId, "UTF-8")}",
            owner = true,
            body = JSONObject().put("status", status),
        )

    fun getAdminAccessRequests(): List<JSONObject> =
        requestArray("/api/admin/access-requests", owner = true)

    fun createAdminUser(name: String, phoneNumber: String, role: String): JSONObject =
        request(
            "POST",
            "/api/admin/users",
            owner = true,
            body = JSONObject()
                .put("name", name)
                .put("phone_number", phoneNumber)
                .put("role", role),
        )

    fun createAdminInvitation(userId: String): JSONObject =
        request(
            "POST",
            "/api/admin/users/${URLEncoder.encode(userId, "UTF-8")}/invitation",
            owner = true,
        )

    fun updateAdminUser(userId: String, role: String?, accountStatus: String?): JSONObject {
        val body = JSONObject()
        if (role != null) body.put("role", role)
        if (accountStatus != null) body.put("account_status", accountStatus)
        return request(
            "PATCH",
            "/api/admin/users/${URLEncoder.encode(userId, "UTF-8")}",
            owner = true,
            body = body,
        )
    }

    fun resetAdminAuthenticator(userId: String): JSONObject =
        request(
            "POST",
            "/api/admin/users/${URLEncoder.encode(userId, "UTF-8")}/reset-authenticator",
            owner = true,
        )

    fun requestAdminAccess(
        targetUserId: String,
        scope: String,
        targetDeviceId: String?,
        reason: String,
        durationMinutes: Int,
    ): JSONObject {
        val body = JSONObject()
            .put("target_user_id", targetUserId)
            .put("scope", scope)
            .put("reason", reason)
            .put("duration_minutes", durationMinutes)
        if (targetDeviceId != null) body.put("target_device_id", targetDeviceId)
        return request("POST", "/api/admin/access-requests", owner = true, body = body)
    }

    fun revokeAdminAccess(requestId: String): JSONObject =
        request(
            "POST",
            "/api/admin/access-requests/${URLEncoder.encode(requestId, "UTF-8")}/revoke",
            owner = true,
        )

    fun getGrantedLocations(requestId: String): List<JSONObject> =
        requestArray(
            "/api/admin/access-requests/${URLEncoder.encode(requestId, "UTF-8")}/devices",
            owner = true,
        )

    fun getGrantedHistory(requestId: String, deviceId: String): List<JSONObject> =
        requestArray(
            "/api/admin/access-requests/${URLEncoder.encode(requestId, "UTF-8")}/devices/" +
                "${URLEncoder.encode(deviceId, "UTF-8")}/locations?period=7days&limit=500",
            owner = true,
        )

    fun controlGrantedDevice(
        requestId: String,
        deviceId: String,
        command: String,
        confirmation: String,
    ): JSONObject =
        request(
            "POST",
            "/api/admin/access-requests/${URLEncoder.encode(requestId, "UTF-8")}/devices/" +
                "${URLEncoder.encode(deviceId, "UTF-8")}/commands",
            owner = true,
            body = JSONObject().put("command", command).put("confirmation", confirmation),
        )

    fun sendDeviceCommand(deviceId: String, command: String): JSONObject {
        val endpoint = when (command) {
            "LOCK" -> "lock"
            "SLEEP" -> "sleep"
            "RESTART" -> "restart"
            "SHUTDOWN" -> "shutdown"
            "GET_STATUS" -> "status"
            "GET_LOCATION" -> "location"
            else -> throw IllegalArgumentException("Unsupported device command.")
        }
        return request(
            "POST",
            "/api/devices/${URLEncoder.encode(deviceId, "UTF-8")}/commands/$endpoint",
            owner = true,
        )
    }

    fun setLostMode(deviceId: String, enabled: Boolean): JSONObject {
        val action = if (enabled) "enable" else "disable"
        return request(
            "POST",
            "/api/devices/${URLEncoder.encode(deviceId, "UTF-8")}/lost-mode/$action",
            owner = true,
        )
    }

    fun uploadLocations(points: List<LocationEntity>) {
        if (points.isEmpty()) return
        val locations = JSONArray()
        points.forEach { point ->
            locations.put(
                JSONObject()
                    .put("latitude", point.latitude)
                    .put("longitude", point.longitude)
                    .putNullable("accuracy", point.accuracy)
                    .putNullable("altitude", point.altitude)
                    .putNullable("speed", point.speed)
                    .putNullable("heading", point.heading)
                    .put("source", point.source)
                    .put("movement_state", point.movementState)
                    .put("timestamp", Instant.ofEpochMilli(point.timestamp).toString()),
            )
        }
        val path = "/api/devices/${URLEncoder.encode(credentials.deviceId, "UTF-8")}/locations/batch"
        request(
            "POST",
            path,
            device = true,
            body = JSONObject().put("locations", locations),
        )
    }

    fun getOwnerAccessToken(): String = credentials.ownerAccessToken

    fun getDeviceId(): String = credentials.deviceId

    fun getDeviceToken(): String = credentials.deviceToken

    fun websocketUrl(): String {
        val base = validateServerUrl(credentials.serverUrl)
        val scheme = if (base.startsWith("https://")) "wss://" else "ws://"
        val host = base.removePrefix("https://").removePrefix("http://")
        return "$scheme$host/ws/device/${URLEncoder.encode(credentials.deviceId, "UTF-8")}?token=${
            URLEncoder.encode(credentials.deviceToken, "UTF-8")
        }"
    }

    private fun request(
        method: String,
        path: String,
        owner: Boolean = false,
        device: Boolean = false,
        body: JSONObject? = null,
        allowRefresh: Boolean = true,
        ownerToken: String? = null,
    ): JSONObject {
        val base = credentials.serverUrl
        require(base.isNotBlank()) { "Enter the FastAPI server address in Settings." }
        val builder = Request.Builder().url("$base$path")
        if (owner) builder.header("Authorization", "Bearer ${ownerToken ?: credentials.ownerAccessToken}")
        if (device) builder.header("Authorization", "Bearer ${credentials.deviceToken}")
        val requestBody = body?.toString()?.toRequestBody(JSON_MEDIA_TYPE)
            ?: if (method in setOf("POST", "PUT", "PATCH")) ByteArray(0).toRequestBody(JSON_MEDIA_TYPE) else null
        builder.method(method, requestBody)

        client.newCall(builder.build()).execute().use { response ->
            val responseText = response.body?.string().orEmpty()
            if (response.code == 401 && owner && ownerToken == null && allowRefresh) {
                refreshOwnerToken()
                return request(method, path, owner = true, body = body, allowRefresh = false)
            }
            if (!response.isSuccessful) {
                val detail = runCatching { JSONObject(responseText).optString("detail") }.getOrNull()
                throw ApiException(response.code, detail?.takeIf(String::isNotBlank) ?: "Server returned HTTP ${response.code}.")
            }
            if (responseText.isBlank()) return JSONObject()
            return JSONTokener(responseText).nextValue() as? JSONObject
                ?: throw IOException("The server returned an invalid response.")
        }
    }

    private fun requestArray(path: String, owner: Boolean, allowRefresh: Boolean = true): List<JSONObject> {
        val base = credentials.serverUrl
        require(base.isNotBlank()) { "Enter the FastAPI server address in Settings." }
        val builder = Request.Builder().url("$base$path")
        if (owner) builder.header("Authorization", "Bearer ${credentials.ownerAccessToken}")
        builder.get()
        client.newCall(builder.build()).execute().use { response ->
            val responseText = response.body?.string().orEmpty()
            if (response.code == 401 && owner && allowRefresh) {
                refreshOwnerToken()
                return requestArray(path, owner = true, allowRefresh = false)
            }
            if (!response.isSuccessful) {
                val detail = runCatching { JSONObject(responseText).optString("detail") }.getOrNull()
                throw ApiException(response.code, detail?.takeIf(String::isNotBlank) ?: "Server returned HTTP ${response.code}.")
            }
            val array = JSONTokener(responseText).nextValue() as? JSONArray
                ?: throw IOException("The server returned an invalid list.")
            return List(array.length()) { index -> array.getJSONObject(index) }
        }
    }

    private fun refreshOwnerToken() {
        val refresh = credentials.ownerRefreshToken
        if (refresh.isBlank()) throw ApiException(401, "Your session expired. Enter your PIN again.")
        val result = request(
            "POST",
            "/api/auth/refresh",
            body = JSONObject().put("refresh_token", refresh),
            allowRefresh = false,
        )
        credentials.ownerAccessToken = result.getString("access_token")
        credentials.ownerRefreshToken = result.getString("refresh_token")
    }

    private fun saveOwnerTokens(response: JSONObject) {
        credentials.ownerAccessToken = response.getString("access_token")
        credentials.ownerRefreshToken = response.getString("refresh_token")
    }

    private fun validateServerUrl(value: String): String {
        val normalized = value.trim().trimEnd('/')
        val url = normalized.toHttpUrlOrNull()
            ?: throw IllegalArgumentException("Enter a valid server URL, for example http://192.168.1.20:8000.")
        require(url.encodedPath == "/" && url.query == null && url.fragment == null) {
            "Enter the server origin only, without a path."
        }
        require(url.scheme == "https" || url.scheme == "http") {
            "The server URL must start with http:// or https://."
        }
        return normalized
    }

    private fun normalizePhoneNumber(value: String): String {
        val normalized = value.filterNot { it.isWhitespace() || it in "().-" }
        require(Regex("^\\+[1-9][0-9]{7,14}$").matches(normalized)) {
            "Enter a phone number with country code in E.164 format, for example +14155550123."
        }
        return normalized
    }

    private fun JSONObject.putNullable(key: String, value: Number?): JSONObject =
        put(key, value ?: JSONObject.NULL)

    companion object {
        private val JSON_MEDIA_TYPE = "application/json; charset=utf-8".toMediaType()
    }
}

class ApiException(val statusCode: Int, message: String) : IOException(message)

fun parseServerTimestamp(value: String?): Long? {
    if (value.isNullOrBlank()) return null
    return runCatching { Instant.parse(value).toEpochMilli() }
        .recoverCatching { OffsetDateTime.parse(value).toInstant().toEpochMilli() }
        .recoverCatching { LocalDateTime.parse(value).toInstant(ZoneOffset.UTC).toEpochMilli() }
        .getOrNull()
}

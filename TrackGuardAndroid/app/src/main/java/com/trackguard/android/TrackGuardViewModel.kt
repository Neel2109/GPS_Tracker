package com.trackguard.android

import android.app.Application
import android.util.Log
import android.content.Intent
import android.os.Build
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.core.content.ContextCompat
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.trackguard.android.data.local.LocationEntity
import com.trackguard.android.data.local.TrackGuardDatabase
import com.trackguard.android.data.remote.DeviceCredentials
import com.trackguard.android.data.remote.ApiException
import com.trackguard.android.data.remote.TrackGuardApi
import com.trackguard.android.data.remote.parseServerTimestamp
import com.trackguard.android.location.LocationService
import com.trackguard.android.model.Device
import com.trackguard.android.model.DeviceStatus
import com.trackguard.android.model.DeviceType
import com.trackguard.android.model.LocationPoint
import com.trackguard.android.model.MovementState
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.json.JSONObject

data class TrackGuardUiState(
    val serverUrl: String = "",
    val deviceName: String = "",
    val signedIn: Boolean = false,
    val userId: String = "",
    val userName: String = "",
    val email: String = "",
    val phoneNumber: String = "",
    val phoneVerificationCodeSent: Boolean = false,
    val phoneVerified: Boolean = false,
    val phoneRecoveryCodeSent: Boolean = false,
    val phoneRecoverySecret: String = "",
    val role: String = "USER",
    val accountStatus: String = "ACTIVE",
    val isLoading: Boolean = false,
    val isPageLoading: Boolean = false,
    val isTracking: Boolean = false,
    val apiHealthStatus: String = "checking",
    val apiHealthMessage: String = "",
    val policy: String = DeviceCredentials.POLICY_NORMAL,
    val currentDeviceId: String = "",
    val historyDeviceId: String = "",
    val historyPeriod: String = "7days",
    val selectedTripId: String = "",
    val proximityThresholdMeters: Int = 250,
    val proximitySnapshot: JSONObject? = null,
    val totpSetupSecret: String = "",
    val invitationSetupSecret: String = "",
    val commandInProgress: String? = null,
    val devices: List<Device> = emptyList(),
    val history: List<LocationPoint> = emptyList(),
    val trips: List<JSONObject> = emptyList(),
    val geofences: List<JSONObject> = emptyList(),
    val alerts: List<JSONObject> = emptyList(),
    val ownerAccessRequests: List<JSONObject> = emptyList(),
    val adminOverview: JSONObject? = null,
    val adminUsers: List<JSONObject> = emptyList(),
    val adminDevices: List<JSONObject> = emptyList(),
    val adminAudit: List<JSONObject> = emptyList(),
    val adminIncidents: List<JSONObject> = emptyList(),
    val adminAccessRequests: List<JSONObject> = emptyList(),
    val grantedLocations: List<JSONObject> = emptyList(),
    val grantedLocationsRequestId: String? = null,
    val grantedHistory: List<JSONObject> = emptyList(),
    val grantedHistoryDeviceName: String = "",
    val accountExportJson: String = "",
    val oneTimeSetupSecret: String? = null,
    val oneTimeSetupLabel: String = "Authenticator setup key",
    val pendingUploads: Int = 0,
    val error: String? = null,
    val info: String? = null,
)

class TrackGuardViewModel(application: Application) : AndroidViewModel(application) {
    private val credentials = DeviceCredentials(application)
    private val api = TrackGuardApi(application)
    private val database = TrackGuardDatabase.getInstance(application)

    var state by mutableStateOf(TrackGuardUiState())
        private set

    init {
        try {
            val signedIn = credentials.ownerAccessToken.isNotBlank()
            state = state.copy(
                serverUrl = credentials.serverUrl,
                deviceName = credentials.deviceName.ifBlank(::defaultDeviceName),
                signedIn = signedIn,
                isTracking = credentials.trackingEnabled,
                policy = credentials.policy,
                currentDeviceId = credentials.deviceId,
                historyDeviceId = credentials.deviceId,
            )
            if (signedIn) refresh()
        } catch (error: IllegalStateException) {
            state = state.copy(error = error.message)
        }
    }

    fun updateServerUrl(value: String) {
        state = state.copy(serverUrl = value, error = null)
    }

    fun updateDeviceName(value: String) {
        state = state.copy(deviceName = value, error = null)
    }

    fun dismissMessage() {
        state = state.copy(error = null, info = null)
    }

    fun resetPhoneRecovery() {
        state = state.copy(phoneRecoveryCodeSent = false, phoneRecoverySecret = "", error = null, info = null)
    }

    fun requestPhoneRecovery(serverUrl: String, phoneNumber: String) {
        if (state.isLoading) return
        state = state.copy(isLoading = true, error = null, info = null)
        viewModelScope.launch {
            try {
                val response = withContext(Dispatchers.IO) {
                    api.requestPhoneRecovery(serverUrl, phoneNumber)
                }
                state = state.copy(
                    phoneRecoveryCodeSent = true,
                    info = response.optString("message", "If the phone number is eligible, a recovery code was sent."),
                )
            } catch (error: Exception) {
                state = state.copy(error = error.message ?: "Could not request account recovery.")
            } finally {
                state = state.copy(isLoading = false)
            }
        }
    }

    fun confirmPhoneRecovery(phoneNumber: String, otpCode: String) {
        if (state.isLoading) return
        state = state.copy(isLoading = true, error = null, info = null)
        viewModelScope.launch {
            try {
                val setup = withContext(Dispatchers.IO) {
                    api.confirmPhoneRecovery(phoneNumber, otpCode)
                }
                state = state.copy(
                    phoneRecoverySecret = setup.optString("secret"),
                    info = "Recovery verified. Add the replacement authenticator key, then activate your account.",
                )
            } catch (error: Exception) {
                state = state.copy(error = error.message ?: "Could not verify the recovery code.")
            } finally {
                state = state.copy(isLoading = false)
            }
        }
    }

    fun showError(message: String) {
        state = state.copy(error = message)
    }

    fun resetPhoneVerification() {
        state = state.copy(
            phoneVerificationCodeSent = false,
            phoneVerified = false,
            error = null,
            info = null,
        )
    }

    fun requestPhoneVerification(serverUrl: String, phoneNumber: String) {
        if (state.isLoading) return
        state = state.copy(isLoading = true, error = null, info = null)
        viewModelScope.launch {
            try {
                val response = withContext(Dispatchers.IO) {
                    api.requestPhoneVerification(serverUrl, phoneNumber)
                }
                state = state.copy(
                    phoneVerificationCodeSent = true,
                    info = response.optString("message"),
                )
            } catch (error: Exception) {
                state = state.copy(error = error.message ?: "Could not request phone verification.")
            } finally {
                state = state.copy(isLoading = false)
            }
        }
    }

    fun confirmPhoneVerification(serverUrl: String, phoneNumber: String, otpCode: String) {
        if (state.isLoading) return
        state = state.copy(isLoading = true, error = null, info = null)
        viewModelScope.launch {
            try {
                val response = withContext(Dispatchers.IO) {
                    api.confirmPhoneVerification(serverUrl, phoneNumber, otpCode)
                }
                state = state.copy(
                    phoneVerificationCodeSent = false,
                    phoneVerified = true,
                    info = response.optString("message"),
                )
            } catch (error: Exception) {
                state = state.copy(error = error.message ?: "Could not verify phone ownership.")
            } finally {
                state = state.copy(isLoading = false)
            }
        }
    }

    fun connectAndPair(pin: String) {
        val serverUrl = state.serverUrl.trim()
        val deviceName = state.deviceName.trim()
        if (
            serverUrl.isBlank() ||
            deviceName.isBlank() ||
            pin.length !in 6..12
        ) {
            state = state.copy(error = "Enter the server address, 6–12 digit PIN, and phone name.")
            return
        }
        if (deviceName.length > 100) {
            state = state.copy(error = "Phone name must be 100 characters or fewer.")
            return
        }
        state = state.copy(isLoading = true, error = null, info = null)
        viewModelScope.launch {
            try {
                val message = withContext(Dispatchers.IO) {
                    api.signIn(serverUrl, pin)
                    if (credentials.deviceId.isBlank() || credentials.deviceToken.isBlank()) {
                        api.pairPhone(deviceName)
                    }
                    credentials.deviceName = deviceName
                    val account = api.getCurrentUser()
                    account to loadAccountData()
                }
                state = state.copy(
                    serverUrl = credentials.serverUrl,
                    deviceName = credentials.deviceName,
                    signedIn = true,
                    userId = message.first.optString("id"),
                    userName = message.first.optString("name"),
                    email = message.first.optString("email"),
                    phoneNumber = message.first.optString("phone_number"),
                    phoneRecoveryCodeSent = false,
                    phoneRecoverySecret = "",
                    role = message.first.optString("role", "USER"),
                    accountStatus = message.first.optString("account_status", "ACTIVE"),
                    totpSetupSecret = "",
                    invitationSetupSecret = "",
                    currentDeviceId = credentials.deviceId,
                    historyDeviceId = credentials.deviceId,
                    devices = message.second.devices,
                    history = message.second.history,
                    trips = message.second.trips,
                    isLoading = false,
                    info = "Phone paired. Grant location permission and start tracking.",
                )
                refreshPageData()
            } catch (error: Exception) {
                state = state.copy(isLoading = false, error = error.message ?: "Could not connect to TrackGuard.")
            }
        }
    }

    fun refresh() {
        if (state.isLoading) return
        state = state.copy(isLoading = true, error = null)
        viewModelScope.launch {
            try {
                val (account, accountData, pending) = withContext(Dispatchers.IO) {
                    Triple(
                        api.getCurrentUser(),
                        loadAccountData(),
                        database.locationDao().getUnsyncedCount(),
                    )
                }
                val apiHealth = try {
                    val health = withContext(Dispatchers.IO) { api.getHealth() }
                    health.optString("status", "unknown") to ""
                } catch (healthError: Exception) {
                    "unavailable" to (healthError.message ?: "Health check failed.")
                }
                state = state.copy(
                    userId = account.optString("id"),
                    userName = account.optString("name"),
                    email = account.optString("email"),
                    phoneNumber = account.optString("phone_number"),
                    role = account.optString("role", "USER"),
                    accountStatus = account.optString("account_status", "ACTIVE"),
                    devices = accountData.devices,
                    history = accountData.history,
                    trips = accountData.trips,
                    apiHealthStatus = apiHealth.first,
                    apiHealthMessage = apiHealth.second,
                    pendingUploads = pending,
                    isLoading = false,
                    signedIn = true,
                )
            } catch (error: Exception) {
                if (error is ApiException && error.statusCode == 401) {
                    credentials.ownerAccessToken = ""
                    credentials.ownerRefreshToken = ""
                    state = state.copy(
                        isLoading = false,
                        signedIn = false,
                        error = "Your session expired. Sign in again with your PIN.",
                    )
                } else {
                    state = state.copy(
                        isLoading = false,
                        error = error.message ?: "Could not refresh device information.",
                    )
                }
            }
        }
    }

    fun setTracking(enabled: Boolean) {
        val app = getApplication<Application>()
        if (enabled && credentials.deviceId.isBlank()) {
            state = state.copy(error = "Connect and pair this phone before enabling tracking.")
            return
        }
        credentials.trackingEnabled = enabled
        state = state.copy(isTracking = enabled, error = null)
        val intent = Intent(app, LocationService::class.java).setAction(
            if (enabled) LocationService.ACTION_START else LocationService.ACTION_STOP,
        )
        if (enabled && Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            ContextCompat.startForegroundService(app, intent)
        } else {
            app.startService(intent)
        }
        if (!enabled) {
            state = state.copy(info = "Location tracking stopped. Unsent points remain saved on this phone.")
        }
    }

    fun setPolicy(policy: String) {
        if (policy !in setOf(
                DeviceCredentials.POLICY_NORMAL,
                DeviceCredentials.POLICY_HIGH_ACCURACY,
                DeviceCredentials.POLICY_BATTERY_SAVER,
            )
        ) return
        credentials.policy = policy
        state = state.copy(policy = policy)
        if (credentials.trackingEnabled) {
            val intent = Intent(getApplication<Application>(), LocationService::class.java)
                .setAction(LocationService.ACTION_RECONFIGURE)
            getApplication<Application>().startService(intent)
        }
    }

    fun signOut() {
        if (credentials.trackingEnabled) setTracking(false)
        val serverUrl = state.serverUrl
        val accessToken = credentials.ownerAccessToken
        credentials.ownerAccessToken = ""
        credentials.ownerRefreshToken = ""
        credentials.deviceId = ""
        credentials.deviceToken = ""
        credentials.deviceName = ""
        credentials.lostModeActive = false
        state = TrackGuardUiState(serverUrl = serverUrl, deviceName = defaultDeviceName())
        if (accessToken.isNotBlank()) {
            viewModelScope.launch {
                try {
                    withContext(Dispatchers.IO) { api.logout(accessToken) }
                } catch (error: Exception) {
                    Log.w("TrackGuard", "Server sign-out failed; local credentials were cleared.", error)
                }
            }
        }
    }

    fun dismissSetupSecret() {
        state = state.copy(oneTimeSetupSecret = null, oneTimeSetupLabel = "Authenticator setup key")
    }

    fun refreshPageData() {
        if (state.isPageLoading || !state.signedIn) return
        state = state.copy(isPageLoading = true)
        viewModelScope.launch {
            try {
                val pageData = withContext(Dispatchers.IO) {
                    val geofences = api.getGeofences()
                    val alerts = api.getAlerts()
                    val ownerRequests = api.getOwnerAccessRequests()
                    val proximitySnapshot = api.getDeviceProximity(state.proximityThresholdMeters)
                    val isAdmin = state.role == "ADMIN" || state.role == "SUPER_ADMIN"
                    if (!isAdmin) {
                        PageData(
                            geofences = geofences,
                            alerts = alerts,
                            ownerAccessRequests = ownerRequests,
                            proximitySnapshot = proximitySnapshot,
                        )
                    } else {
                        PageData(
                            geofences = geofences,
                            alerts = alerts,
                            ownerAccessRequests = ownerRequests,
                            proximitySnapshot = proximitySnapshot,
                            adminOverview = api.getAdminOverview(),
                            adminUsers = api.getAdminUsers(),
                            adminDevices = api.getAdminDevices(),
                            adminAudit = api.getAdminAudit(),
                            adminIncidents = api.getAdminIncidents(),
                            adminAccessRequests = api.getAdminAccessRequests(),
                        )
                    }
                }
                applyPageData(pageData)
            } catch (error: Exception) {
                state = state.copy(
                    error = error.message ?: "Could not load account and administrator pages.",
                )
            } finally {
                state = state.copy(isPageLoading = false)
            }
        }
    }

    fun selectProximityThreshold(thresholdMeters: Int) {
        if (thresholdMeters == state.proximityThresholdMeters || state.isPageLoading) return
        if (thresholdMeters !in listOf(100, 250, 500, 1000)) return
        state = state.copy(
            proximityThresholdMeters = thresholdMeters,
            isPageLoading = true,
            error = null,
        )
        viewModelScope.launch {
            try {
                val snapshot = withContext(Dispatchers.IO) {
                    api.getDeviceProximity(thresholdMeters)
                }
                state = state.copy(proximitySnapshot = snapshot)
            } catch (error: Exception) {
                state = state.copy(error = error.message ?: "Could not calculate device proximity.")
            } finally {
                state = state.copy(isPageLoading = false)
            }
        }
    }

    fun createGeofence(name: String, latitude: Double, longitude: Double, radius: Double) =
        runPageAction("Geofence saved.") { api.createGeofence(name, latitude, longitude, radius) }

    fun setGeofenceEnabled(geofenceId: String, enabled: Boolean) =
        runPageAction("Geofence updated.") { api.setGeofenceEnabled(geofenceId, enabled) }

    fun deleteGeofence(geofenceId: String) =
        runPageAction("Geofence deleted.") {
            api.deleteGeofence(geofenceId)
            null
        }

    fun sendSos(deviceId: String?, message: String) =
        runPageAction("SOS alert created in TrackGuard.") { api.sendSos(deviceId, message) }

    fun exportAccountData() {
        if (state.isPageLoading) return
        state = state.copy(isPageLoading = true, error = null, info = null)
        viewModelScope.launch {
            try {
                val export = withContext(Dispatchers.IO) { api.exportAccountData() }
                state = state.copy(
                    accountExportJson = export.toString(2),
                    info = "Account data export is ready to share.",
                )
            } catch (error: Exception) {
                state = state.copy(error = error.message ?: "Could not export account data.")
            } finally {
                state = state.copy(isPageLoading = false)
            }
        }
    }

    fun deleteLocationHistory() {
        if (state.isPageLoading) return
        state = state.copy(isPageLoading = true, error = null, info = null)
        viewModelScope.launch {
            try {
                val deleted = withContext(Dispatchers.IO) { api.deleteLocationHistory() }
                state = state.copy(
                    history = emptyList(),
                    info = "$deleted location records permanently deleted.",
                )
                refresh()
            } catch (error: Exception) {
                state = state.copy(error = error.message ?: "Could not delete location history.")
            } finally {
                state = state.copy(isPageLoading = false)
            }
        }
    }

    fun markAlertRead(alertId: String) =
        runPageAction("Alert marked as read.") { api.markAlertRead(alertId) }

    fun updateAlertStatus(alertId: String, status: String) =
        runPageAction("Incident ${status.lowercase()}.") {
            api.updateAlertStatus(alertId, status)
        }

    fun markAllAlertsRead() =
        runPageAction("All alerts marked as read.") {
            api.markAllAlertsRead()
            null
        }

    fun decideOwnerAccessRequest(requestId: String, action: String) =
        runPageAction("Access request ${action.lowercase()}.") {
            api.decideOwnerAccessRequest(requestId, action)
        }

    fun createAdminUser(name: String, phoneNumber: String, role: String) =
        runPageAction("Account created. Share the single-use invitation code privately.") {
            api.createAdminUser(name, phoneNumber, role)
        }

    fun createAdminInvitation(userId: String) =
        runPageAction("A new 48-hour invitation was created. Share its code privately.") {
            api.createAdminInvitation(userId)
        }

    fun updateAdminIncident(incidentId: String, status: String) =
        runPageAction("Incident ${status.lowercase()}.") {
            api.updateAdminIncident(incidentId, status)
        }

    fun updateAdminUser(userId: String, role: String?, accountStatus: String?) =
        runPageAction("Account updated.") { api.updateAdminUser(userId, role, accountStatus) }

    fun resetAdminAuthenticator(userId: String) =
        runPageAction("Authenticator reset. Share the new setup key privately.") {
            api.resetAdminAuthenticator(userId)
        }

    fun requestAdminAccess(
        targetUserId: String,
        scope: String,
        targetDeviceId: String?,
        reason: String,
        durationMinutes: Int,
    ) = runPageAction("Owner approval request sent.") {
        api.requestAdminAccess(targetUserId, scope, targetDeviceId, reason, durationMinutes)
    }

    fun revokeAdminAccess(requestId: String) =
        runPageAction("Access request revoked.") { api.revokeAdminAccess(requestId) }

    fun showGrantedLocations(requestId: String) {
        state = state.copy(
            isPageLoading = true,
            error = null,
            grantedLocations = emptyList(),
            grantedLocationsRequestId = null,
            grantedHistory = emptyList(),
            grantedHistoryDeviceName = "",
        )
        viewModelScope.launch {
            try {
                val locations = withContext(Dispatchers.IO) { api.getGrantedLocations(requestId) }
                state = state.copy(
                    grantedLocations = locations,
                    grantedLocationsRequestId = requestId,
                )
            } catch (error: Exception) {
                state = state.copy(error = error.message ?: "Could not load approved device locations.")
            } finally {
                state = state.copy(isPageLoading = false)
            }
        }
    }

    fun showGrantedHistory(requestId: String, deviceId: String, deviceName: String) {
        state = state.copy(
            isPageLoading = true,
            error = null,
            grantedHistory = emptyList(),
            grantedHistoryDeviceName = deviceName,
        )
        viewModelScope.launch {
            try {
                val history = withContext(Dispatchers.IO) {
                    api.getGrantedHistory(requestId, deviceId)
                }
                state = state.copy(
                    grantedHistory = history,
                    grantedHistoryDeviceName = deviceName,
                )
            } catch (error: Exception) {
                state = state.copy(error = error.message ?: "Could not load approved location history.")
            } finally {
                state = state.copy(isPageLoading = false)
            }
        }
    }

    fun sendGrantedDeviceCommand(
        requestId: String,
        deviceId: String,
        command: String,
        confirmation: String,
    ) = runPageAction("Command sent to the approved device.") {
        api.controlGrantedDevice(requestId, deviceId, command, confirmation)
    }

    private fun runPageAction(
        successMessage: String,
        action: (TrackGuardApi) -> JSONObject?,
    ) {
        if (state.isPageLoading) return
        state = state.copy(isPageLoading = true, error = null, info = null)
        viewModelScope.launch {
            try {
                val result = withContext(Dispatchers.IO) { action(api) }
                val pageData = withContext(Dispatchers.IO) {
                    val geofences = api.getGeofences()
                    val alerts = api.getAlerts()
                    val ownerRequests = api.getOwnerAccessRequests()
                    val proximitySnapshot = api.getDeviceProximity(state.proximityThresholdMeters)
                    val isAdmin = state.role == "ADMIN" || state.role == "SUPER_ADMIN"
                    if (!isAdmin) {
                        PageData(
                            geofences = geofences,
                            alerts = alerts,
                            ownerAccessRequests = ownerRequests,
                            proximitySnapshot = proximitySnapshot,
                        )
                    } else {
                        PageData(
                            geofences = geofences,
                            alerts = alerts,
                            ownerAccessRequests = ownerRequests,
                            proximitySnapshot = proximitySnapshot,
                            adminOverview = api.getAdminOverview(),
                            adminUsers = api.getAdminUsers(),
                            adminDevices = api.getAdminDevices(),
                            adminAudit = api.getAdminAudit(),
                            adminIncidents = api.getAdminIncidents(),
                            adminAccessRequests = api.getAdminAccessRequests(),
                        )
                    }
                }
                applyPageData(pageData)
                val secret = result?.optString("invitation_token")?.takeIf(String::isNotBlank)
                    ?: result?.optString("totp_secret")?.takeIf(String::isNotBlank)
                    ?: result?.optString("secret")?.takeIf(String::isNotBlank)
                val setupLabel = if (result?.has("invitation_token") == true) {
                    "Single-use account invitation code"
                } else {
                    "Authenticator setup key"
                }
                state = state.copy(
                    info = successMessage,
                    oneTimeSetupSecret = secret,
                    oneTimeSetupLabel = setupLabel,
                    isPageLoading = false,
                )
            } catch (error: Exception) {
                state = state.copy(
                    error = error.message ?: "The requested account action could not be completed.",
                    isPageLoading = false,
                )
            }
        }
    }

    private fun applyPageData(data: PageData) {
        state = state.copy(
            geofences = data.geofences,
            alerts = data.alerts,
            ownerAccessRequests = data.ownerAccessRequests,
            proximitySnapshot = data.proximitySnapshot,
            adminOverview = data.adminOverview,
            adminUsers = data.adminUsers,
            adminDevices = data.adminDevices,
            adminAudit = data.adminAudit,
            adminIncidents = data.adminIncidents,
            adminAccessRequests = data.adminAccessRequests,
        )
    }

    private data class PageData(
        val geofences: List<JSONObject>,
        val alerts: List<JSONObject>,
        val ownerAccessRequests: List<JSONObject>,
        val proximitySnapshot: JSONObject? = null,
        val adminOverview: JSONObject? = null,
        val adminUsers: List<JSONObject> = emptyList(),
        val adminDevices: List<JSONObject> = emptyList(),
        val adminAudit: List<JSONObject> = emptyList(),
        val adminIncidents: List<JSONObject> = emptyList(),
        val adminAccessRequests: List<JSONObject> = emptyList(),
    )

    fun selectHistoryDevice(deviceId: String) {
        if (deviceId == state.historyDeviceId || deviceId.isBlank()) return
        state = state.copy(
            historyDeviceId = deviceId,
            history = emptyList(),
            trips = emptyList(),
            selectedTripId = "",
            isLoading = true,
            error = null,
        )
        loadHistoryData(deviceId)
    }

    fun selectHistoryPeriod(period: String) {
        if (period !in setOf("today", "7days", "30days", "all") || period == state.historyPeriod) return
        state = state.copy(
            historyPeriod = period,
            selectedTripId = "",
            history = emptyList(),
            trips = emptyList(),
        )
        if (state.historyDeviceId.isNotBlank()) loadHistoryData(state.historyDeviceId)
    }

    private fun loadHistoryData(deviceId: String) {
        state = state.copy(isLoading = true, error = null)
        viewModelScope.launch {
            try {
                val result = withContext(Dispatchers.IO) {
                    HistoryData(
                        history = api.getHistory(deviceId, state.historyPeriod).map(::locationFromJson),
                        trips = api.getTrips(deviceId, state.historyPeriod),
                    )
                }
                state = state.copy(history = result.history, trips = result.trips, isLoading = false)
            } catch (error: Exception) {
                state = state.copy(isLoading = false, error = error.message ?: "Could not load this device's history.")
            }
        }
    }

    fun selectHistoryTrip(tripId: String?) {
        val deviceId = state.historyDeviceId
        if (deviceId.isBlank()) return
        if (tripId == null) {
            state = state.copy(selectedTripId = "", history = emptyList(), isLoading = true, error = null)
            viewModelScope.launch {
                try {
                    val locations = withContext(Dispatchers.IO) {
                        api.getHistory(deviceId, state.historyPeriod).map(::locationFromJson)
                    }
                    state = state.copy(history = locations, isLoading = false)
                } catch (error: Exception) {
                    state = state.copy(isLoading = false, error = error.message ?: "Could not load route history.")
                }
            }
            return
        }
        state = state.copy(selectedTripId = tripId, history = emptyList(), isLoading = true, error = null)
        viewModelScope.launch {
            try {
                val locations = withContext(Dispatchers.IO) {
                    api.getTripLocations(deviceId, tripId, state.historyPeriod).map(::locationFromJson)
                }
                state = state.copy(history = locations, isLoading = false)
            } catch (error: Exception) {
                state = state.copy(isLoading = false, error = error.message ?: "Could not load this trip.")
            }
        }
    }

    fun sendDeviceCommand(device: Device, command: String) {
        val supportedCommands = when (device.type) {
            DeviceType.LAPTOP, DeviceType.DESKTOP ->
                setOf("LOCK", "SLEEP", "RESTART", "SHUTDOWN", "GET_STATUS", "GET_LOCATION")
            DeviceType.ANDROID -> setOf("GET_STATUS", "GET_LOCATION")
            else -> emptySet()
        }
        if (command !in supportedCommands) {
            state = state.copy(error = "This command is not supported for ${device.name}.")
            return
        }
        if (state.commandInProgress != null) return
        state = state.copy(commandInProgress = device.id, error = null, info = null)

        viewModelScope.launch {
            try {
                val result = withContext(Dispatchers.IO) {
                    api.sendDeviceCommand(device.id, command)
                }
                state = state.copy(
                    info = "$command queued for ${device.name} (${result.optString("status", "pending")}).",
                    error = null,
                )
            } catch (error: Exception) {
                state = state.copy(error = error.message ?: "Could not send the command.")
            } finally {
                state = state.copy(commandInProgress = null)
            }
            refresh()
        }
    }

    fun setLostMode(device: Device, enabled: Boolean) {
        if (device.type != DeviceType.ANDROID) {
            state = state.copy(error = "Lost Mode is currently supported for tracked Android phones.")
            return
        }
        if (state.commandInProgress != null) return
        state = state.copy(commandInProgress = device.id, error = null, info = null)
        viewModelScope.launch {
            try {
                withContext(Dispatchers.IO) {
                    api.setLostMode(device.id, enabled)
                }
                state = state.copy(
                    info = if (enabled) "Lost Mode enabled for ${device.name}."
                    else "Lost Mode disabled for ${device.name}.",
                    error = null,
                )
                refresh()
            } catch (error: Exception) {
                state = state.copy(error = error.message ?: "Could not update Lost Mode.")
            } finally {
                state = state.copy(commandInProgress = null)
            }
            refresh()
        }
    }

    private suspend fun loadAccountData(): AccountData {
        val remoteDevices = api.getDevices()
        val selectedId = state.historyDeviceId.ifBlank { credentials.deviceId }
        val devices = remoteDevices.map(::deviceFromJson)
        val historyData = if (selectedId.isNotBlank()) {
            HistoryData(
                history = api.getHistory(selectedId, state.historyPeriod).map(::locationFromJson),
                trips = api.getTrips(selectedId, state.historyPeriod),
            )
        } else {
            HistoryData(emptyList(), emptyList())
        }
        return AccountData(devices, historyData.history, historyData.trips)
    }

    private data class AccountData(
        val devices: List<Device>,
        val history: List<LocationPoint>,
        val trips: List<JSONObject>,
    )

    private data class HistoryData(
        val history: List<LocationPoint>,
        val trips: List<JSONObject>,
    )

    private fun deviceFromJson(json: JSONObject): Device {
        val type = runCatching {
            DeviceType.valueOf(json.optString("device_type", "OTHER").uppercase())
        }.getOrDefault(DeviceType.OTHER)
        val status = runCatching {
            DeviceStatus.valueOf(json.optString("connection_state", json.optString("status", "unknown")).uppercase())
        }.getOrDefault(DeviceStatus.UNKNOWN)
        return Device(
            id = json.getString("id"),
            name = json.optString("name", "Device"),
            type = type,
            platform = json.optString("platform", json.optString("device_type", "Device")),
            model = json.optString("model").takeUnless { it == "null" || it.isBlank() },
            osVersion = json.optString("os_version").takeUnless { it == "null" || it.isBlank() },
            status = status,
            battery = json.nullableInt("last_battery") ?: json.nullableInt("battery_level"),
            isCharging = json.nullableBoolean("is_charging"),
            networkType = json.optString("network_type").takeUnless { it == "null" || it.isBlank() }
                ?: json.optString("last_network").takeUnless { it == "null" || it.isBlank() },
            wifiConnected = json.nullableBoolean("wifi_connected"),
            localIp = json.optString("local_ip").takeUnless { it == "null" || it.isBlank() },
            publicIp = json.optString("public_ip").takeUnless { it == "null" || it.isBlank() },
            cpuInfo = json.optString("cpu_info").takeUnless { it == "null" || it.isBlank() },
            ramTotal = json.optString("ram_total").takeUnless { it == "null" || it.isBlank() },
            storageTotal = json.optString("storage_total").takeUnless { it == "null" || it.isBlank() },
            isLostMode = json.optBoolean("is_lost_mode"),
            latitude = json.nullableDouble("last_latitude"),
            longitude = json.nullableDouble("last_longitude"),
            accuracy = json.nullableDouble("last_accuracy")?.toFloat(),
            speed = json.nullableDouble("last_speed")?.toFloat(),
            heading = json.nullableDouble("last_heading")?.toFloat(),
            lastSeen = parseServerTimestamp(json.optString("last_seen").takeUnless { it == "null" }),
            lastLocationTime = parseServerTimestamp(json.optString("last_location_time").takeUnless { it == "null" }),
            locationSource = json.optString("last_location_source").takeUnless { it == "null" },
            movementState = json.optString("last_movement_state").takeUnless { it == "null" || it.isBlank() },
        )
    }

    private fun locationFromJson(json: JSONObject): LocationPoint {
        val movement = runCatching {
            MovementState.valueOf(json.optString("movement_state", "UNKNOWN").uppercase())
        }.getOrDefault(MovementState.UNKNOWN)
        return LocationPoint(
            deviceId = json.optString("device_id", credentials.deviceId),
            latitude = json.getDouble("latitude"),
            longitude = json.getDouble("longitude"),
            accuracy = json.nullableDouble("accuracy")?.toFloat(),
            altitude = json.nullableDouble("altitude"),
            speed = json.nullableDouble("speed")?.toFloat(),
            heading = json.nullableDouble("heading")?.toFloat(),
            source = json.optString("source", "unknown"),
            movementState = movement,
            timestamp = parseServerTimestamp(json.optString("timestamp").takeUnless { it == "null" })
                ?: System.currentTimeMillis(),
        )
    }

    private fun JSONObject.nullableDouble(name: String): Double? =
        if (isNull(name) || !has(name)) null else optDouble(name).takeUnless { it.isNaN() }

    private fun JSONObject.nullableInt(name: String): Int? =
        if (isNull(name) || !has(name)) null else optInt(name)

    private fun JSONObject.nullableBoolean(name: String): Boolean? =
        if (isNull(name) || !has(name)) null else optBoolean(name)

    private fun defaultDeviceName(): String =
        "${Build.MANUFACTURER} ${Build.MODEL}".trim().ifBlank { "Android phone" }
}

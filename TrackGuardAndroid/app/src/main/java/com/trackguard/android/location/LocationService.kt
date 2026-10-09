package com.trackguard.android.location

import android.Manifest
import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.content.pm.PackageManager
import android.location.Location
import android.net.ConnectivityManager
import android.net.NetworkCapabilities
import android.os.BatteryManager
import android.os.Build
import android.os.Handler
import android.os.IBinder
import android.os.Looper
import android.os.SystemClock
import androidx.core.app.NotificationCompat
import androidx.core.content.ContextCompat
import com.google.android.gms.location.LocationCallback
import com.google.android.gms.location.LocationRequest
import com.google.android.gms.location.LocationResult
import com.google.android.gms.location.LocationServices
import com.google.android.gms.location.Priority
import com.trackguard.android.MainActivity
import com.trackguard.android.R
import com.trackguard.android.data.local.LocationEntity
import com.trackguard.android.data.local.TrackGuardDatabase
import com.trackguard.android.data.remote.DeviceCredentials
import com.trackguard.android.data.remote.LocationSyncWorker
import com.trackguard.android.data.remote.TrackGuardApi
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.launch
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import org.json.JSONObject
import java.io.IOException
import java.util.concurrent.TimeUnit

class LocationService : Service() {
    private val serviceScope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private val handler = Handler(Looper.getMainLooper())
    private lateinit var credentials: DeviceCredentials
    private lateinit var locationCallback: LocationCallback
    private val locationClient by lazy { LocationServices.getFusedLocationProviderClient(this) }
    private val socketClient by lazy {
        OkHttpClient.Builder()
            .pingInterval(25, TimeUnit.SECONDS)
            .connectTimeout(15, TimeUnit.SECONDS)
            .build()
    }
    private var socket: WebSocket? = null
    private var reconnectDelayMillis = 2_000L
    private var reconnectScheduled = false
    private var lastReportedLocation: Location? = null
    private var lastReportedElapsedMillis = 0L
    private var stopped = false

    private val heartbeat = object : Runnable {
        override fun run() {
            if (stopped) return
            sendHeartbeatAndStatus()
            handler.postDelayed(this, HEARTBEAT_INTERVAL_MILLIS)
        }
    }

    override fun onCreate() {
        super.onCreate()
        credentials = DeviceCredentials(this)
        createNotificationChannel()
        locationCallback = object : LocationCallback() {
            override fun onLocationResult(result: LocationResult) {
                result.locations.forEach(::handleLocation)
            }
        }
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        when (intent?.action) {
            ACTION_STOP -> {
                stopTracking()
                return START_NOT_STICKY
            }
            ACTION_RECONFIGURE -> {
                stopLocationUpdates()
                startLocationUpdates()
                return START_STICKY
            }
        }

        if (credentials.deviceId.isBlank() || credentials.deviceToken.isBlank()) {
            stopSelf()
            return START_NOT_STICKY
        }

        stopped = false
        credentials.trackingEnabled = true
        startForeground(NOTIFICATION_ID, buildNotification())
        connectSocket()
        startLocationUpdates()
        handler.removeCallbacks(heartbeat)
        handler.post(heartbeat)
        LocationSyncWorker.enqueue(this)
        return START_STICKY
    }

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onDestroy() {
        stopTracking()
        serviceScope.cancel()
        super.onDestroy()
    }

    private fun startLocationUpdates() {
        if (!hasLocationPermission()) {
            credentials.trackingEnabled = false
            stopSelf()
            return
        }

        val activePolicy = if (credentials.lostModeActive) {
            DeviceCredentials.POLICY_HIGH_ACCURACY
        } else {
            credentials.policy
        }
        val (interval, distance, priority) = when (activePolicy) {
            DeviceCredentials.POLICY_HIGH_ACCURACY -> Triple(7_500L, 7f, Priority.PRIORITY_HIGH_ACCURACY)
            DeviceCredentials.POLICY_BATTERY_SAVER -> Triple(60_000L, 50f, Priority.PRIORITY_BALANCED_POWER_ACCURACY)
            else -> Triple(15_000L, 15f, Priority.PRIORITY_BALANCED_POWER_ACCURACY)
        }
        val request = LocationRequest.Builder(priority, interval)
            .setMinUpdateIntervalMillis(interval / 2)
            .setMinUpdateDistanceMeters(distance)
            .build()
        try {
            locationClient.requestLocationUpdates(request, locationCallback, Looper.getMainLooper())
        } catch (_: SecurityException) {
            credentials.trackingEnabled = false
            stopSelf()
        }
    }

    private fun stopLocationUpdates() {
        if (::locationCallback.isInitialized) {
            locationClient.removeLocationUpdates(locationCallback)
        }
    }

    private fun handleLocation(location: Location) {
        val elapsed = SystemClock.elapsedRealtime()
        val previous = lastReportedLocation
        val movedEnough = previous == null || location.distanceTo(previous) >= minimumDistanceMeters()
        val waitedLongEnough = elapsed - lastReportedElapsedMillis >= MAX_SILENCE_MILLIS
        if (!movedEnough && !waitedLongEnough) return

        lastReportedLocation = Location(location)
        lastReportedElapsedMillis = elapsed
        val point = LocationEntity(
            deviceId = credentials.deviceId,
            latitude = location.latitude,
            longitude = location.longitude,
            accuracy = if (location.hasAccuracy()) location.accuracy else null,
            altitude = if (location.hasAltitude()) location.altitude else null,
            speed = if (location.hasSpeed()) location.speed else null,
            heading = if (location.hasBearing()) location.bearing else null,
            source = if (location.provider == "gps") "gps" else "fused",
            movementState = movementState(location),
            timestamp = location.time,
        )
        serviceScope.launch {
            TrackGuardDatabase.getInstance(applicationContext)
                .locationDao()
                .insertLocation(point)
            LocationSyncWorker.enqueue(applicationContext)
            sendLocation(point)
        }
    }

    private fun minimumDistanceMeters(): Float = when (
        if (credentials.lostModeActive) DeviceCredentials.POLICY_HIGH_ACCURACY else credentials.policy
    ) {
        DeviceCredentials.POLICY_HIGH_ACCURACY -> 7f
        DeviceCredentials.POLICY_BATTERY_SAVER -> 50f
        else -> 15f
    }

    private fun movementState(location: Location): String {
        if (!location.hasSpeed() || location.speed < 0.5f) return "STATIONARY"
        return when {
            location.speed >= 8.3f -> "DRIVING"
            location.speed >= 2.2f -> "CYCLING"
            else -> "WALKING"
        }
    }

    private fun connectSocket() {
        if (stopped || credentials.deviceId.isBlank() || credentials.deviceToken.isBlank()) return
        val request = try {
            Request.Builder().url(TrackGuardApi(this).websocketUrl()).build()
        } catch (_: IllegalArgumentException) {
            scheduleReconnect()
            return
        }
        socket?.cancel()
        socket = socketClient.newWebSocket(request, object : WebSocketListener() {
            override fun onOpen(webSocket: WebSocket, response: okhttp3.Response) {
                socket = webSocket
                reconnectDelayMillis = 2_000L
                sendStatus()
                sendHeartbeatAndStatus()
                serviceScope.launch {
                    TrackGuardDatabase.getInstance(applicationContext)
                        .locationDao()
                        .getRecentLocations(credentials.deviceId)
                        .firstOrNull()
                        ?.let(::sendLocation)
                }
            }

            override fun onMessage(webSocket: WebSocket, text: String) {
                handleServerMessage(text)
            }

            override fun onClosed(webSocket: WebSocket, code: Int, reason: String) {
                if (socket === webSocket) socket = null
                scheduleReconnect()
            }

            override fun onFailure(webSocket: WebSocket, t: Throwable, response: okhttp3.Response?) {
                if (socket === webSocket) socket = null
                scheduleReconnect()
            }
        })
    }

    private fun scheduleReconnect() {
        if (stopped || reconnectScheduled) return
        reconnectScheduled = true
        handler.postDelayed({
            reconnectScheduled = false
            connectSocket()
        }, reconnectDelayMillis)
        reconnectDelayMillis = (reconnectDelayMillis * 2).coerceAtMost(MAX_RECONNECT_DELAY_MILLIS)
    }

    private fun sendLocation(point: LocationEntity) {
        socket?.send(
            JSONObject()
                .put("type", "LOCATION_UPDATE")
                .put(
                    "data",
                    JSONObject()
                        .put("latitude", point.latitude)
                        .put("longitude", point.longitude)
                        .putNullable("accuracy", point.accuracy)
                        .putNullable("altitude", point.altitude)
                        .putNullable("speed", point.speed)
                        .putNullable("heading", point.heading)
                        .put("source", point.source)
                        .put("movement_state", point.movementState)
                        .put("timestamp", java.time.Instant.ofEpochMilli(point.timestamp).toString()),
                )
                .toString(),
        )
    }

    private fun sendHeartbeatAndStatus() {
        socket?.send(JSONObject().put("type", "HEARTBEAT").toString())
        socket?.send(JSONObject().put("type", "BATTERY_UPDATE").put("data", batteryInfo()).toString())
    }

    private fun sendStatus() {
        socket?.send(
            JSONObject()
                .put("type", "STATUS_UPDATE")
                .put(
                    "data",
                    JSONObject()
                        .put("platform", "Android")
                        .put("model", "${Build.MANUFACTURER} ${Build.MODEL}".trim())
                        .put("os_version", "Android ${Build.VERSION.RELEASE}")
                        .put("network_type", networkType())
                        .put("wifi_connected", isWifiConnected()),
                )
                .toString(),
        )
    }

    private fun batteryInfo(): JSONObject {
        val battery = registerReceiver(null, IntentFilter(Intent.ACTION_BATTERY_CHANGED))
        val level = battery?.getIntExtra(BatteryManager.EXTRA_LEVEL, -1) ?: -1
        val scale = battery?.getIntExtra(BatteryManager.EXTRA_SCALE, -1) ?: -1
        val percent = if (level >= 0 && scale > 0) level * 100 / scale else JSONObject.NULL
        val plugged = battery?.getIntExtra(BatteryManager.EXTRA_PLUGGED, 0) ?: 0
        return JSONObject()
            .put("battery_level", percent)
            .put("is_charging", plugged != 0)
            .put("network_type", networkType())
            .put("wifi_connected", isWifiConnected())
    }

    private fun networkType(): String {
        val manager = getSystemService(Context.CONNECTIVITY_SERVICE) as ConnectivityManager
        val capabilities = manager.getNetworkCapabilities(manager.activeNetwork) ?: return "offline"
        return when {
            capabilities.hasTransport(NetworkCapabilities.TRANSPORT_WIFI) -> "wifi"
            capabilities.hasTransport(NetworkCapabilities.TRANSPORT_CELLULAR) -> "cellular"
            capabilities.hasTransport(NetworkCapabilities.TRANSPORT_ETHERNET) -> "ethernet"
            else -> "online"
        }
    }

    private fun isWifiConnected(): Boolean = networkType() == "wifi"

    private fun handleServerMessage(text: String) {
        val message = try {
            JSONObject(text)
        } catch (_: Exception) {
            return
        }
        when (message.optString("type")) {
            "COMMAND" -> {
                val command = message.optString("command")
                val commandId = message.optString("command_id")
                when (command) {
                    "GET_STATUS" -> {
                        sendStatus()
                        sendCommandResult(commandId, command, "success", "Status reported")
                    }
                    "GET_LOCATION" -> serviceScope.launch {
                        val point = TrackGuardDatabase.getInstance(applicationContext)
                            .locationDao()
                            .getRecentLocations(credentials.deviceId)
                            .firstOrNull()
                        if (point != null) {
                            sendLocation(point)
                            sendCommandResult(commandId, command, "success", "Location reported")
                        } else {
                            sendCommandResult(commandId, command, "failed", "No location has been recorded yet")
                        }
                    }
                    "ENABLE_LOST_MODE" -> {
                        credentials.lostModeActive = true
                        stopLocationUpdates()
                        startLocationUpdates()
                        sendCommandResult(commandId, command, "success", "Lost Mode enabled")
                    }
                    "DISABLE_LOST_MODE" -> {
                        credentials.lostModeActive = false
                        stopLocationUpdates()
                        startLocationUpdates()
                        sendCommandResult(commandId, command, "success", "Lost Mode disabled")
                    }
                    else -> {
                        sendCommandResult(commandId, command, "failed", "Unsupported command")
                    }
                }
            }
            "ENABLE_LOST_MODE" -> {
                credentials.lostModeActive = true
                stopLocationUpdates()
                startLocationUpdates()
            }
            "DISABLE_LOST_MODE" -> {
                credentials.lostModeActive = false
                stopLocationUpdates()
                startLocationUpdates()
            }
        }
    }

    private fun sendCommandResult(commandId: String, command: String, status: String, result: String) {
        if (commandId.isBlank()) return
        socket?.send(
            JSONObject()
                .put("type", "COMMAND_RESULT")
                .put(
                    "data",
                    JSONObject()
                        .put("command_id", commandId)
                        .put("command", command)
                        .put("status", status)
                        .put("result", result),
                )
                .toString(),
        )
    }

    private fun stopTracking() {
        if (stopped) return
        stopped = true
        credentials.trackingEnabled = false
        handler.removeCallbacks(heartbeat)
        stopLocationUpdates()
        socket?.close(1000, "tracking stopped")
        socket = null
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.N) {
            stopForeground(STOP_FOREGROUND_REMOVE)
        } else {
            @Suppress("DEPRECATION")
            stopForeground(true)
        }
        stopSelf()
    }

    private fun hasLocationPermission(): Boolean =
        ContextCompat.checkSelfPermission(this, Manifest.permission.ACCESS_FINE_LOCATION) == PackageManager.PERMISSION_GRANTED ||
            ContextCompat.checkSelfPermission(this, Manifest.permission.ACCESS_COARSE_LOCATION) == PackageManager.PERMISSION_GRANTED

    private fun createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(
                CHANNEL_ID,
                "TrackGuard location tracking",
                NotificationManager.IMPORTANCE_LOW,
            )
            getSystemService(NotificationManager::class.java).createNotificationChannel(channel)
        }
    }

    private fun buildNotification(): Notification {
        val openApp = PendingIntent.getActivity(
            this,
            0,
            Intent(this, MainActivity::class.java),
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
        )
        val stopService = PendingIntent.getService(
            this,
            1,
            Intent(this, LocationService::class.java).setAction(ACTION_STOP),
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
        )
        return NotificationCompat.Builder(this, CHANNEL_ID)
            .setContentTitle("TrackGuard tracking is on")
            .setContentText("Collecting location and syncing when a network is available")
            .setSmallIcon(android.R.drawable.ic_menu_mylocation)
            .setContentIntent(openApp)
            .setOngoing(true)
            .addAction(0, "Stop", stopService)
            .setPriority(NotificationCompat.PRIORITY_LOW)
            .build()
    }

    private fun JSONObject.putNullable(key: String, value: Number?): JSONObject =
        put(key, value ?: JSONObject.NULL)

    companion object {
        const val ACTION_START = "com.trackguard.android.location.START"
        const val ACTION_STOP = "com.trackguard.android.location.STOP"
        const val ACTION_RECONFIGURE = "com.trackguard.android.location.RECONFIGURE"

        private const val CHANNEL_ID = "trackguard_locations"
        private const val NOTIFICATION_ID = 1001
        private const val HEARTBEAT_INTERVAL_MILLIS = 30_000L
        private const val MAX_SILENCE_MILLIS = 300_000L
        private const val MAX_RECONNECT_DELAY_MILLIS = 60_000L
    }
}

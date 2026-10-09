package com.trackguard.android.model

enum class DeviceType {
    LAPTOP,
    DESKTOP,
    ANDROID,
    IPHONE,
    TABLET,
    SMARTWATCH,
    CAR,
    GPS_TRACKER,
    OTHER
}

enum class DeviceStatus {
    ONLINE,
    RECENTLY_OFFLINE,
    OFFLINE,
    SLEEPING,
    POWERED_OFF,
    LOCATION_UNAVAILABLE,
    UNKNOWN
}

data class Device(
    val id: String,
    val name: String,
    val type: DeviceType = DeviceType.LAPTOP,
    val platform: String = "Android",
    val model: String? = null,
    val osVersion: String? = null,
    val status: DeviceStatus = DeviceStatus.ONLINE,
    val battery: Int? = null,
    val isCharging: Boolean? = null,
    val networkType: String? = null,
    val wifiConnected: Boolean? = null,
    val localIp: String? = null,
    val publicIp: String? = null,
    val cpuInfo: String? = null,
    val ramTotal: String? = null,
    val storageTotal: String? = null,
    val isLostMode: Boolean = false,
    val latitude: Double? = null,
    val longitude: Double? = null,
    val accuracy: Float? = null,
    val speed: Float? = null,
    val heading: Float? = null,
    val lastSeen: Long? = null,
    val lastLocationTime: Long? = null,
    val locationSource: String? = null,
    val movementState: String? = null,
)

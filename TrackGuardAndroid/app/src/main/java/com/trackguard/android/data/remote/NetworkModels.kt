package com.trackguard.android.data.remote

import kotlinx.serialization.Serializable

@Serializable
data class DeviceApiResponse(
    val id: String,
    val name: String,
    val device_type: String,
    val status: String,
    val battery_level: Int? = null,
    val latitude: Double? = null,
    val longitude: Double? = null,
    val accuracy: Float? = null,
    val last_seen: String? = null,
    val last_location_source: String? = null,
)

@Serializable
data class SocketMessage(
    val type: String,
    val device_id: String? = null,
    val data: Map<String, String>? = null,
)

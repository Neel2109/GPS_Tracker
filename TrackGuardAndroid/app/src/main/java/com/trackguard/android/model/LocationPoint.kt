package com.trackguard.android.model

enum class MovementState {
    STATIONARY,
    WALKING,
    CYCLING,
    DRIVING,
    UNKNOWN
}

data class LocationPoint(
    val deviceId: String,
    val latitude: Double,
    val longitude: Double,
    val accuracy: Float? = null,
    val altitude: Double? = null,
    val speed: Float? = null,
    val heading: Float? = null,
    val source: String = "gps",
    val movementState: MovementState = MovementState.STATIONARY,
    val timestamp: Long = System.currentTimeMillis()
)

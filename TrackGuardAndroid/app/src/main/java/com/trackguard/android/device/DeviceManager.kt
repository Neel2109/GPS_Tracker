package com.trackguard.android.device

import com.trackguard.android.model.Device
import com.trackguard.android.model.DeviceStatus
import com.trackguard.android.model.DeviceType

class DeviceManager {
    fun getDemoDevices(): List<Device> = listOf(
        Device(
            id = "laptop-1",
            name = "Neel Laptop",
            type = DeviceType.LAPTOP,
            platform = "Windows",
            status = DeviceStatus.ONLINE,
            battery = 76,
            latitude = 23.0225,
            longitude = 72.5714,
            accuracy = 8f,
            speed = 12f,
            heading = 90f,
            lastSeen = System.currentTimeMillis() - 120_000,
            locationSource = "gps"
        ),
        Device(
            id = "phone-1",
            name = "Neel Phone",
            type = DeviceType.ANDROID,
            platform = "Android",
            status = DeviceStatus.ONLINE,
            battery = 82,
            latitude = 23.0215,
            longitude = 72.5702,
            accuracy = 10f,
            speed = 7f,
            heading = 120f,
            lastSeen = System.currentTimeMillis() - 30_000,
            locationSource = "gps"
        )
    )
}

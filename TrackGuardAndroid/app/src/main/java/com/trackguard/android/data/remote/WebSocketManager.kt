package com.trackguard.android.data.remote

import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.SharedFlow
import kotlinx.coroutines.flow.asSharedFlow
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import java.util.concurrent.TimeUnit

class WebSocketManager {
    private val client = OkHttpClient.Builder()
        .readTimeout(30, TimeUnit.SECONDS)
        .connectTimeout(15, TimeUnit.SECONDS)
        .build()

    private val _events = MutableSharedFlow<SocketMessage>(extraBufferCapacity = 64)
    val events: SharedFlow<SocketMessage> = _events.asSharedFlow()

    private var socket: WebSocket? = null

    fun connect(serverUrl: String) {
        val request = Request.Builder().url(serverUrl).build()
        socket = client.newWebSocket(request, object : WebSocketListener() {
            override fun onMessage(webSocket: WebSocket, text: String) {
                val payload = SocketMessage(type = "DATA", device_id = null, data = mapOf("raw" to text))
                _events.tryEmit(payload)
            }
        })
    }

    fun sendHeartbeat(deviceId: String) {
        val message = """{"type":"HEARTBEAT","device_id":"$deviceId"}"""
        socket?.send(message)
    }

    fun close() {
        socket?.close(1000, "closed")
        socket = null
    }
}

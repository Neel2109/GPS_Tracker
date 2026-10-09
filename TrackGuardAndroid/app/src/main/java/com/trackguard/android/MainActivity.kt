package com.trackguard.android

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Build
import android.os.Bundle
import androidx.compose.foundation.background
import androidx.activity.ComponentActivity
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.activity.viewModels
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.text.selection.SelectionContainer
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.AccessTime
import androidx.compose.material.icons.filled.Devices
import androidx.compose.material.icons.filled.Home
import androidx.compose.material.icons.filled.Map
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material.icons.filled.MyLocation
import androidx.compose.material3.Button
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.FilterChip
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Slider
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.ui.graphics.Color
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import androidx.core.content.ContextCompat
import com.google.android.gms.maps.CameraUpdateFactory
import com.google.android.gms.maps.model.BitmapDescriptorFactory
import com.google.android.gms.maps.model.CameraPosition
import com.google.android.gms.maps.model.LatLng
import com.trackguard.android.model.Device
import com.trackguard.android.model.DeviceStatus
import com.trackguard.android.model.DeviceType
import com.trackguard.android.model.LocationPoint
import com.trackguard.android.ui.theme.TrackGuardTheme
import com.google.maps.android.compose.GoogleMap
import com.google.maps.android.compose.MapProperties
import com.google.maps.android.compose.MapType
import com.google.maps.android.compose.MapUiSettings
import com.google.maps.android.compose.Marker
import com.google.maps.android.compose.MarkerState
import com.google.maps.android.compose.Polyline
import com.google.maps.android.compose.rememberCameraPositionState
import kotlinx.coroutines.delay
import java.text.DateFormat
import org.json.JSONObject
import java.util.Date
import java.util.Locale

class MainActivity : ComponentActivity() {
    private val viewModel: TrackGuardViewModel by viewModels()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            TrackGuardTheme {
                TrackGuardApp(viewModel)
            }
        }
    }
}

private sealed class AppTab(val title: String, val icon: androidx.compose.ui.graphics.vector.ImageVector) {
    data object Home : AppTab("Home", Icons.Default.Home)
    data object Map : AppTab("Map", Icons.Default.Map)
    data object Devices : AppTab("Devices", Icons.Default.Devices)
    data object History : AppTab("History", Icons.Default.AccessTime)
    data object More : AppTab("More", Icons.Default.Settings)
}

@Composable
private fun TrackGuardApp(viewModel: TrackGuardViewModel) {
    val state = viewModel.state
    var selectedTab by rememberSaveable { mutableStateOf("Map") }
    var moreSection by rememberSaveable { mutableStateOf("Account") }
    var pin by rememberSaveable { mutableStateOf("") }
    val context = LocalContext.current
    val locationPermissionLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestMultiplePermissions(),
    ) { results ->
        val locationGranted =
            results[Manifest.permission.ACCESS_FINE_LOCATION] == true ||
                results[Manifest.permission.ACCESS_COARSE_LOCATION] == true
        if (locationGranted) {
            viewModel.setTracking(true)
        } else {
            viewModel.showError("Location permission is needed to track this phone.")
        }
    }

    LaunchedEffect(state.signedIn) {
        while (state.signedIn) {
            delay(5_000)
            viewModel.refresh()
        }
    }

    if (!state.signedIn) {
        PinConnectScreen(
            serverUrl = state.serverUrl,
            deviceName = state.deviceName,
            pin = pin,
            isLoading = state.isLoading,
            error = state.error,
            onServerUrlChanged = viewModel::updateServerUrl,
            onDeviceNameChanged = viewModel::updateDeviceName,
            onPinChanged = { pin = it.filter(Char::isDigit).take(12) },
            onConnect = { viewModel.connectAndPair(pin) },
        )
        return
    }

    Scaffold(
        bottomBar = {
            NavigationBar {
                listOf(AppTab.Home, AppTab.Map, AppTab.Devices, AppTab.History, AppTab.More).forEach { tab ->
                    NavigationBarItem(
                        selected = selectedTab == tab.title,
                        onClick = {
                            selectedTab = tab.title
                            if (tab == AppTab.More) {
                                moreSection = if (state.role == "ADMIN" || state.role == "SUPER_ADMIN") "Admin" else "Account"
                                viewModel.refreshPageData()
                            }
                        },
                        icon = { Icon(tab.icon, contentDescription = tab.title) },
                        label = { Text(tab.title) },
                    )
                }
            }
        },
    ) { padding ->
        Column(Modifier.fillMaxSize().padding(padding)) {
            state.error?.let { MessageCard(it, onDismiss = viewModel::dismissMessage, isError = true) }
            state.info?.let { MessageCard(it, onDismiss = viewModel::dismissMessage, isError = false) }
            when (selectedTab) {
                AppTab.Home.title -> HomeScreen(
                    devices = state.devices,
                    currentDeviceId = state.currentDeviceId,
                    apiHealthStatus = state.apiHealthStatus,
                    apiHealthMessage = state.apiHealthMessage,
                    isTracking = state.isTracking,
                    isLoading = state.isLoading,
                    pendingUploads = state.pendingUploads,
                    onToggleTracking = {
                        if (state.isTracking) {
                            viewModel.setTracking(false)
                        } else {
                            val fineGranted = ContextCompat.checkSelfPermission(
                                context,
                                Manifest.permission.ACCESS_FINE_LOCATION,
                            ) == PackageManager.PERMISSION_GRANTED
                            val coarseGranted = ContextCompat.checkSelfPermission(
                                context,
                                Manifest.permission.ACCESS_COARSE_LOCATION,
                            ) == PackageManager.PERMISSION_GRANTED
                            if (fineGranted || coarseGranted) {
                                viewModel.setTracking(true)
                            } else {
                                val permissions = buildList {
                                    add(Manifest.permission.ACCESS_FINE_LOCATION)
                                    add(Manifest.permission.ACCESS_COARSE_LOCATION)
                                    if (Build.VERSION.SDK_INT >= 33) add(Manifest.permission.POST_NOTIFICATIONS)
                                }
                                locationPermissionLauncher.launch(permissions.toTypedArray())
                            }
                        }
                    },
                    onRefresh = viewModel::refresh,
                )
                AppTab.Map.title -> MapScreen(
                    devices = state.devices,
                    selectedDeviceId = state.currentDeviceId,
                    isLoading = state.isLoading,
                    onRefresh = viewModel::refresh,
                    onViewHistory = { deviceId ->
                        viewModel.selectHistoryDevice(deviceId)
                        selectedTab = AppTab.History.title
                    },
                    onViewDevices = { selectedTab = AppTab.Devices.title },
                )
                AppTab.Devices.title -> DevicesScreen(
                    devices = state.devices,
                    commandInProgress = state.commandInProgress,
                    onCommand = viewModel::sendDeviceCommand,
                    onLostMode = viewModel::setLostMode,
                )
                AppTab.History.title -> HistoryScreen(
                    history = state.history,
                    devices = state.devices,
                    trips = state.trips,
                    selectedDeviceId = state.historyDeviceId,
                    selectedPeriod = state.historyPeriod,
                    selectedTripId = state.selectedTripId,
                    isLoading = state.isLoading,
                    onSelectDevice = viewModel::selectHistoryDevice,
                    onSelectPeriod = viewModel::selectHistoryPeriod,
                    onSelectTrip = viewModel::selectHistoryTrip,
                )
                else -> AccountToolsScreen(
                    state = state,
                    section = moreSection,
                    onSectionChanged = { moreSection = it },
                    onRefresh = viewModel::refreshPageData,
                    onSignOut = viewModel::signOut,
                    onPolicyChanged = viewModel::setPolicy,
                    onCreateGeofence = viewModel::createGeofence,
                    onSetGeofenceEnabled = viewModel::setGeofenceEnabled,
                    onDeleteGeofence = viewModel::deleteGeofence,
                    onSendSos = viewModel::sendSos,
                    onExportAccountData = viewModel::exportAccountData,
                    onShareAccountExport = { json ->
                        val shareIntent = Intent(Intent.ACTION_SEND).apply {
                            type = "application/json"
                            putExtra(Intent.EXTRA_TEXT, json)
                        }
                        context.startActivity(Intent.createChooser(shareIntent, "Share TrackGuard data export"))
                    },
                    onDeleteLocationHistory = viewModel::deleteLocationHistory,
                    onMarkAlertRead = viewModel::markAlertRead,
                    onUpdateAlertStatus = viewModel::updateAlertStatus,
                    onMarkAllAlertsRead = viewModel::markAllAlertsRead,
                    onDecideAccessRequest = viewModel::decideOwnerAccessRequest,
                    onCreateAdminUser = viewModel::createAdminUser,
                    onCreateAdminInvitation = viewModel::createAdminInvitation,
                    onUpdateAdminUser = viewModel::updateAdminUser,
                    onUpdateAdminIncident = viewModel::updateAdminIncident,
                    onResetAuthenticator = viewModel::resetAdminAuthenticator,
                    onRequestAdminAccess = viewModel::requestAdminAccess,
                    onRevokeAdminAccess = viewModel::revokeAdminAccess,
                    onShowGrantedLocations = viewModel::showGrantedLocations,
                    onShowGrantedHistory = viewModel::showGrantedHistory,
                    onExportAdminCsv = { fileName, csv ->
                        val shareIntent = Intent(Intent.ACTION_SEND).apply {
                            type = "text/csv"
                            putExtra(Intent.EXTRA_SUBJECT, fileName)
                            putExtra(Intent.EXTRA_TEXT, csv)
                        }
                        context.startActivity(Intent.createChooser(shareIntent, "Share filtered administrator report"))
                    },
                    onSendGrantedDeviceCommand = viewModel::sendGrantedDeviceCommand,
                    onDismissSetupSecret = viewModel::dismissSetupSecret,
                    onProximityThresholdChanged = viewModel::selectProximityThreshold,
                )
            }
        }
    }
}

@Composable
private fun PinConnectScreen(
    serverUrl: String,
    deviceName: String,
    pin: String,
    isLoading: Boolean,
    error: String?,
    onServerUrlChanged: (String) -> Unit,
    onDeviceNameChanged: (String) -> Unit,
    onPinChanged: (String) -> Unit,
    onConnect: () -> Unit,
) {
    Column(
        modifier = Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(24.dp),
        verticalArrangement = Arrangement.Center,
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Text("TrackGuard", style = MaterialTheme.typography.headlineLarge)
        Spacer(Modifier.height(24.dp))
        OutlinedTextField(
            value = serverUrl,
            onValueChange = onServerUrlChanged,
            label = { Text("Backend server URL") },
            placeholder = { Text("http://192.168.1.20:8000") },
            singleLine = true,
            modifier = Modifier.fillMaxWidth(),
        )
        OutlinedTextField(
            value = deviceName,
            onValueChange = onDeviceNameChanged,
            label = { Text("Phone name") },
            singleLine = true,
            modifier = Modifier.fillMaxWidth(),
        )
        OutlinedTextField(
            value = pin,
            onValueChange = onPinChanged,
            label = { Text("PIN") },
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.NumberPassword),
            visualTransformation = PasswordVisualTransformation(),
            singleLine = true,
            modifier = Modifier.fillMaxWidth(),
        )
        error?.let {
            Spacer(Modifier.height(8.dp))
            Text(it, color = MaterialTheme.colorScheme.error)
        }
        Spacer(Modifier.height(16.dp))
        Button(
            onClick = onConnect,
            enabled = !isLoading && pin.length in 6..12 && serverUrl.isNotBlank() && deviceName.isNotBlank(),
            modifier = Modifier.fillMaxWidth(),
        ) {
            if (isLoading) CircularProgressIndicator() else Text("Sign in and pair phone")
        }
    }
}

@Composable
private fun HomeScreen(
    devices: List<Device>,
    currentDeviceId: String,
    apiHealthStatus: String,
    apiHealthMessage: String,
    isTracking: Boolean,
    isLoading: Boolean,
    pendingUploads: Int,
    onToggleTracking: () -> Unit,
    onRefresh: () -> Unit,
) {
    val ownDevice = devices.firstOrNull { it.id == currentDeviceId }
    LazyColumn(
        modifier = Modifier.fillMaxSize().padding(horizontal = 16.dp, vertical = 12.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        item {
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
                Column {
                    Text("TrackGuard", style = MaterialTheme.typography.headlineSmall)
                    Text("${devices.count { it.status == DeviceStatus.ONLINE }} devices online")
                }
                TextButton(onClick = onRefresh, enabled = !isLoading) {
                    Icon(Icons.Default.Refresh, contentDescription = "Refresh")
                }
            }
        }
        item {
            Card(Modifier.fillMaxWidth()) {
                Column(Modifier.fillMaxWidth().padding(14.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                    Text("Service & device health", style = MaterialTheme.typography.titleMedium)
                    Text("TrackGuard API: $apiHealthStatus")
                    if (apiHealthMessage.isNotBlank()) Text(apiHealthMessage, style = MaterialTheme.typography.bodySmall)
                    devices.forEach { device ->
                        val lastReport = device.lastSeen?.let(::formatTime) ?: "No report received"
                        val health = when {
                            device.status != DeviceStatus.ONLINE -> device.status.name.lowercase().replace('_', ' ')
                            device.battery != null && device.battery <= 20 -> "low battery"
                            else -> "healthy"
                        }
                        Text("${device.name}: $health · last seen $lastReport", style = MaterialTheme.typography.bodySmall)
                    }
                }
            }
        }
        item {
            Card(Modifier.fillMaxWidth(), shape = RoundedCornerShape(20.dp)) {
                Column(Modifier.fillMaxWidth().padding(18.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                    Text(ownDevice?.name ?: "This phone", style = MaterialTheme.typography.titleLarge)
                    Text(if (isTracking) "Tracking is active" else "Tracking is paused")
                    ownDevice?.let { LocationSummary(it) }
                    Button(onClick = onToggleTracking, modifier = Modifier.fillMaxWidth()) {
                        Text(if (isTracking) "Stop tracking" else "Start tracking")
                    }
                    Text(
                        when {
                            pendingUploads > 0 -> "$pendingUploads location points waiting to sync"
                            isTracking -> "Locations sync when a network is available."
                            else -> "Start tracking to record this phone's route."
                        },
                        style = MaterialTheme.typography.bodySmall,
                    )
                }
            }
        }
        item { Text("YOUR DEVICES", style = MaterialTheme.typography.labelLarge) }
        items(devices, key = { it.id }) { DeviceCard(it) }
        if (devices.isEmpty() && !isLoading) {
            item { Text("No paired devices yet. Refresh to check your account.") }
        }
    }
}

@Composable
private fun DevicesScreen(
    devices: List<Device>,
    commandInProgress: String?,
    onCommand: (Device, String) -> Unit,
    onLostMode: (Device, Boolean) -> Unit,
) {
    if (devices.isEmpty()) {
        Column(Modifier.fillMaxSize().padding(24.dp), verticalArrangement = Arrangement.Center) {
            Text("No devices found for this account.", style = MaterialTheme.typography.titleMedium)
        }
        return
    }
    LazyColumn(
        Modifier.fillMaxSize().padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        items(devices, key = { it.id }) { device ->
            DeviceCard(
                device = device,
                showControls = true,
                isBusy = commandInProgress != null,
                onCommand = { command -> onCommand(device, command) },
                onLostMode = { enabled -> onLostMode(device, enabled) },
            )
        }
    }
}

@Composable
private fun DeviceCard(
    device: Device,
    showControls: Boolean = false,
    isBusy: Boolean = false,
    onCommand: (String) -> Unit = {},
    onLostMode: (Boolean) -> Unit = {},
) {
    var commandToConfirm by remember(device.id) { mutableStateOf<String?>(null) }
    val supportedCommands = when (device.type) {
        com.trackguard.android.model.DeviceType.LAPTOP,
        com.trackguard.android.model.DeviceType.DESKTOP -> listOf(
            "GET_STATUS" to "Request status",
            "GET_LOCATION" to "Request location",
            "LOCK" to "Lock",
            "SLEEP" to "Sleep",
            "RESTART" to "Restart",
            "SHUTDOWN" to "Shut down",
        )
        com.trackguard.android.model.DeviceType.ANDROID -> listOf(
            "GET_STATUS" to "Request status",
            "GET_LOCATION" to "Request location",
        )
        else -> emptyList()
    }
    Card(Modifier.fillMaxWidth()) {
        Column(Modifier.fillMaxWidth().padding(16.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                Text(device.name, style = MaterialTheme.typography.titleMedium)
                Text(statusLabel(device.status), color = statusColor(device.status))
            }
            Text("${device.platform} · ${device.type.name.lowercase().replace('_', ' ')}")
            device.battery?.let { Text("Battery: $it%${if (device.isCharging == true) " · charging" else ""}") }
            device.networkType?.let { Text("Network: $it") }
            device.localIp?.let { Text("Local IP: $it") }
            device.publicIp?.let { Text("Public IP: $it") }
            device.osVersion?.let { Text("OS: $it") }
            device.model?.let { Text("Model: $it") }
            device.cpuInfo?.let { Text("CPU: $it") }
            device.ramTotal?.let { Text("Memory: $it") }
            device.storageTotal?.let { Text("Storage: $it") }
            if (device.latitude != null && device.longitude != null) LocationSummary(device)
            else Text("No location reported yet.")
            device.lastLocationTime?.let { Text("Location fix: ${formatTime(it)}", style = MaterialTheme.typography.bodySmall) }
            device.lastSeen?.let { Text("Last update: ${formatTime(it)}", style = MaterialTheme.typography.bodySmall) }
            if (device.isLostMode) {
                Text("LOST MODE ACTIVE", color = MaterialTheme.colorScheme.error)
            }
            if (showControls && supportedCommands.isNotEmpty()) {
                Spacer(Modifier.height(4.dp))
                Text("DEVICE CONTROL", style = MaterialTheme.typography.labelLarge)
                val deviceOnline = device.status == DeviceStatus.ONLINE
                supportedCommands.forEach { (command, label) ->
                    val requiresConfirmation = command in setOf("LOCK", "SLEEP", "RESTART", "SHUTDOWN")
                    OutlinedButton(
                        onClick = {
                            if (requiresConfirmation) commandToConfirm = command
                            else onCommand(command)
                        },
                        enabled = !isBusy && deviceOnline,
                        modifier = Modifier.fillMaxWidth(),
                    ) {
                        Text(if (isBusy) "Sending…" else label)
                    }
                }
                if (device.type == com.trackguard.android.model.DeviceType.ANDROID) {
                    OutlinedButton(
                        onClick = { onLostMode(!device.isLostMode) },
                        enabled = !isBusy,
                        modifier = Modifier.fillMaxWidth(),
                    ) {
                        Text(if (device.isLostMode) "Disable Lost Mode" else "Enable Lost Mode")
                    }
                }
                Text(
                    if (!deviceOnline) {
                        "Device is offline. Commands are unavailable; Lost Mode changes will apply when it reconnects."
                    } else {
                        "Power controls are available only for supported, paired devices."
                    },
                    style = MaterialTheme.typography.bodySmall,
                )
            }
        }
    }
    commandToConfirm?.let { command ->
        val label = supportedCommands.firstOrNull { it.first == command }?.second ?: command
        AlertDialog(
            onDismissRequest = { commandToConfirm = null },
            title = { Text("Confirm $label?") },
            text = {
                Text(
                    when (command) {
                        "LOCK" -> "Lock ${device.name}'s Windows session."
                        "SLEEP" -> "Put ${device.name} to sleep."
                        "RESTART" -> "Restart ${device.name}. Unsaved work may be lost."
                        "SHUTDOWN" -> "Shut down ${device.name}. It will go offline."
                        else -> "Send this command to ${device.name}?"
                    },
                )
            },
            confirmButton = {
                TextButton(
                    onClick = {
                        commandToConfirm = null
                        onCommand(command)
                    },
                ) { Text(label) }
            },
            dismissButton = {
                TextButton(onClick = { commandToConfirm = null }) { Text("Cancel") }
            },
        )
    }
}

@Composable
private fun LocationSummary(device: Device) {
    val latitude = device.latitude ?: return
    val longitude = device.longitude ?: return
    Text("Latitude  ${"%.6f".format(Locale.US, latitude)}")
    Text("Longitude  ${"%.6f".format(Locale.US, longitude)}")
    device.accuracy?.let { Text("Reported accuracy  ±${it.toInt()} m") }
    device.speed?.let { Text("Speed  ${"%.1f".format(Locale.US, it)} m/s") }
    device.heading?.let { Text("Heading  ${it.toInt()}°") }
    device.locationSource?.let { Text("Source  $it") }
    device.movementState?.let { Text("Movement  ${it.lowercase().replace('_', ' ')}") }
}

@Composable
private fun MapScreen(
    devices: List<Device>,
    selectedDeviceId: String,
    isLoading: Boolean,
    onRefresh: () -> Unit,
    onViewHistory: (String) -> Unit,
    onViewDevices: () -> Unit,
) {
    val context = LocalContext.current
    val locatedDevices = devices.filter { it.latitude != null && it.longitude != null }
    var selectedId by rememberSaveable { mutableStateOf(selectedDeviceId) }
    var followSelected by rememberSaveable { mutableStateOf(true) }
    val selectedDevice = locatedDevices.firstOrNull { it.id == selectedId }
        ?: locatedDevices.firstOrNull()
    val initialPosition = selectedDevice?.let {
        LatLng(it.latitude!!, it.longitude!!)
    } ?: LatLng(20.0, 0.0)
    val cameraPositionState = rememberCameraPositionState {
        position = CameraPosition.fromLatLngZoom(initialPosition, if (selectedDevice == null) 2f else 14f)
    }

    LaunchedEffect(selectedDevice?.id, selectedDevice?.latitude, selectedDevice?.longitude, followSelected) {
        val latitude = selectedDevice?.latitude
        val longitude = selectedDevice?.longitude
        if (followSelected && latitude != null && longitude != null) {
            cameraPositionState.animate(
                CameraUpdateFactory.newLatLngZoom(LatLng(latitude, longitude), 14f),
            )
        }
    }

    Box(Modifier.fillMaxSize().background(MaterialTheme.colorScheme.background)) {
        if (BuildConfig.HAS_MAPS_API_KEY) {
            GoogleMap(
                modifier = Modifier.fillMaxSize(),
                cameraPositionState = cameraPositionState,
                properties = MapProperties(mapType = MapType.SATELLITE),
                uiSettings = MapUiSettings(zoomControlsEnabled = false),
                onMapClick = { followSelected = false },
            ) {
                locatedDevices.forEach { device ->
                    val latitude = device.latitude ?: return@forEach
                    val longitude = device.longitude ?: return@forEach
                    Marker(
                        state = remember(device.id, latitude, longitude) {
                            MarkerState(position = LatLng(latitude, longitude))
                        },
                        title = device.name,
                        snippet = markerSummary(device),
                        icon = BitmapDescriptorFactory.defaultMarker(markerHue(device.type)),
                        alpha = if (device.status == DeviceStatus.ONLINE) 1f else 0.62f,
                        rotation = if (device.type == DeviceType.CAR) device.heading ?: 0f else 0f,
                        flat = device.type == DeviceType.CAR,
                        onClick = {
                            selectedId = device.id
                            followSelected = true
                            true
                        },
                    )
                }
            }
        } else {
            Column(
                Modifier.fillMaxSize().padding(28.dp),
                verticalArrangement = Arrangement.Center,
                horizontalAlignment = Alignment.CenterHorizontally,
            ) {
                Text("Map setup needed", style = MaterialTheme.typography.titleLarge)
                Spacer(Modifier.height(8.dp))
                Text(
                    "Add a restricted Google Maps Android API key as MAPS_API_KEY in " +
                        "TrackGuardAndroid/local.properties, then rebuild. Device locations remain available below.",
                    style = MaterialTheme.typography.bodyMedium,
                )
            }
        }

        Row(
            Modifier.align(Alignment.TopEnd).padding(12.dp),
            horizontalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            TextButton(onClick = onRefresh, enabled = !isLoading) {
                if (isLoading) CircularProgressIndicator() else Icon(Icons.Default.Refresh, contentDescription = "Refresh")
            }
            if (BuildConfig.HAS_MAPS_API_KEY) {
                TextButton(
                    onClick = {
                        followSelected = true
                        val latitude = selectedDevice?.latitude
                        val longitude = selectedDevice?.longitude
                        if (latitude != null && longitude != null) {
                            cameraPositionState.move(
                                CameraUpdateFactory.newLatLngZoom(LatLng(latitude, longitude), 15f),
                            )
                        }
                    },
                ) {
                    Icon(Icons.Default.MyLocation, contentDescription = "Follow selected device")
                }
            }
        }

        if (selectedDevice != null) {
            Card(
                Modifier.align(Alignment.BottomCenter).fillMaxWidth().padding(12.dp),
                shape = RoundedCornerShape(20.dp),
                colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface.copy(alpha = 0.96f)),
            ) {
                Column(
                    Modifier.fillMaxWidth().padding(horizontal = 18.dp, vertical = 14.dp),
                    verticalArrangement = Arrangement.spacedBy(6.dp),
                ) {
                    Row(
                        Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceBetween,
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        Column(Modifier.weight(1f)) {
                            Text(selectedDevice.name, style = MaterialTheme.typography.titleLarge)
                            Text(
                                "${statusLabel(selectedDevice.status)} · ${selectedDevice.type.name.replace('_', ' ')}",
                                color = statusColor(selectedDevice.status),
                                style = MaterialTheme.typography.labelLarge,
                            )
                        }
                        selectedDevice.battery?.let { Text("🔋 $it%") }
                    }
                    if (selectedDevice.latitude != null && selectedDevice.longitude != null) {
                        Text(
                            "Reported accuracy ±${selectedDevice.accuracy?.let { "${it.toInt()} m" } ?: "unavailable"}" +
                                selectedDevice.speed?.let { " · ${"%.1f".format(Locale.US, it)} m/s" }.orEmpty(),
                            style = MaterialTheme.typography.bodyMedium,
                        )
                        selectedDevice.lastLocationTime?.let {
                            Text("Location updated ${formatTime(it)}", style = MaterialTheme.typography.bodySmall)
                        }
                    } else {
                        Text("No location has been reported for this device.", style = MaterialTheme.typography.bodyMedium)
                    }

                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        TextButton(
                            onClick = {
                                followSelected = true
                                selectedDevice.latitude?.let { latitude ->
                                    selectedDevice.longitude?.let { longitude ->
                                        cameraPositionState.move(
                                            CameraUpdateFactory.newLatLngZoom(LatLng(latitude, longitude), 15f),
                                        )
                                    }
                                }
                            },
                            enabled = selectedDevice.latitude != null && BuildConfig.HAS_MAPS_API_KEY,
                        ) { Text("Follow") }
                        TextButton(onClick = { onViewHistory(selectedDevice.id) }) { Text("History") }
                        TextButton(onClick = onViewDevices) { Text("Devices") }
                        TextButton(
                            onClick = {
                                val latitude = selectedDevice.latitude ?: return@TextButton
                                val longitude = selectedDevice.longitude ?: return@TextButton
                                val label = Uri.encode(selectedDevice.name)
                                val mapIntent = Intent(
                                    Intent.ACTION_VIEW,
                                    Uri.parse("geo:$latitude,$longitude?q=$latitude,$longitude($label)"),
                                )
                                if (mapIntent.resolveActivity(context.packageManager) != null) {
                                    context.startActivity(mapIntent)
                                }
                            },
                            enabled = selectedDevice.latitude != null,
                        ) { Text("Open map app") }
                    }
                }
            }
        } else if (locatedDevices.isEmpty()) {
            Card(
                Modifier.align(Alignment.BottomCenter).fillMaxWidth().padding(12.dp),
                shape = RoundedCornerShape(20.dp),
            ) {
                Column(Modifier.fillMaxWidth().padding(18.dp)) {
                    Text(
                        if (devices.isEmpty()) "No devices paired yet" else "Waiting for location reports",
                        style = MaterialTheme.typography.titleMedium,
                    )
                    Text("Pair a device and allow it to report location to see it on this map.")
                    TextButton(onClick = onViewDevices) { Text("View devices") }
                }
            }
        }

        if (locatedDevices.size > 1) {
            Row(
                Modifier.align(Alignment.TopStart)
                    .fillMaxWidth(0.72f)
                    .horizontalScroll(rememberScrollState())
                    .padding(horizontal = 8.dp, vertical = 10.dp),
                horizontalArrangement = Arrangement.spacedBy(6.dp),
            ) {
                locatedDevices.forEach { device ->
                    FilterChip(
                        selected = selectedDevice?.id == device.id,
                        onClick = {
                            selectedId = device.id
                            followSelected = true
                        },
                        label = { Text(device.name) },
                    )
                }
            }
        }
    }
}

private fun markerSummary(device: Device): String = buildList {
    add(statusLabel(device.status))
    device.battery?.let { add("Battery $it%") }
    device.accuracy?.let { add("Accuracy ±${it.toInt()} m") }
}.joinToString(" · ")

private fun markerHue(type: DeviceType): Float = when (type) {
    DeviceType.CAR -> BitmapDescriptorFactory.HUE_ORANGE
    DeviceType.ANDROID, DeviceType.IPHONE, DeviceType.TABLET -> BitmapDescriptorFactory.HUE_AZURE
    DeviceType.LAPTOP, DeviceType.DESKTOP -> BitmapDescriptorFactory.HUE_BLUE
    DeviceType.SMARTWATCH -> BitmapDescriptorFactory.HUE_VIOLET
    DeviceType.GPS_TRACKER -> BitmapDescriptorFactory.HUE_CYAN
    DeviceType.OTHER -> BitmapDescriptorFactory.HUE_GREEN
}

@Composable
private fun HistoryScreen(
    history: List<LocationPoint>,
    devices: List<Device>,
    trips: List<JSONObject>,
    selectedDeviceId: String,
    selectedPeriod: String,
    selectedTripId: String,
    isLoading: Boolean,
    onSelectDevice: (String) -> Unit,
    onSelectPeriod: (String) -> Unit,
    onSelectTrip: (String?) -> Unit,
) {
    var isPlaying by rememberSaveable(selectedTripId) { mutableStateOf(false) }
    var replayIndex by rememberSaveable(selectedTripId) { mutableStateOf(0f) }
    LaunchedEffect(isPlaying, history.size, selectedTripId) {
        while (isPlaying && selectedTripId.isNotBlank() && history.size > 1) {
            delay(700)
            val nextIndex = replayIndex.toInt() + 1
            if (nextIndex >= history.size) {
                isPlaying = false
            } else {
                replayIndex = nextIndex.toFloat()
            }
        }
    }
    if (devices.isNotEmpty()) {
        Row(
            Modifier.fillMaxWidth()
                .horizontalScroll(rememberScrollState())
                .padding(horizontal = 16.dp, vertical = 8.dp),
            horizontalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            devices.forEach { device ->
                FilterChip(
                    selected = selectedDeviceId == device.id,
                    onClick = { onSelectDevice(device.id) },
                    label = { Text(device.name) },
                )
            }
        }
    }
    Row(
        Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()).padding(horizontal = 16.dp),
        horizontalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        listOf("Today" to "today", "7 days" to "7days", "30 days" to "30days", "All" to "all").forEach { (label, value) ->
            FilterChip(selectedPeriod == value, { onSelectPeriod(value) }, label = { Text(label) })
        }
    }
    if (trips.isNotEmpty()) {
        Column(
            Modifier.fillMaxWidth().heightIn(max = 220.dp).verticalScroll(rememberScrollState()).padding(horizontal = 16.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            Text("TRIP REPORTS · ${trips.size}", style = MaterialTheme.typography.labelLarge)
            Text(
                "Trips split at gaps over 30 minutes. Stops are estimated from reported stationary samples lasting at least 5 minutes.",
                style = MaterialTheme.typography.bodySmall,
            )
            trips.forEachIndexed { index, trip ->
                val tripId = trip.optString("id")
                val distanceKm = trip.optDouble("distance_meters") / 1000.0
                val durationMinutes = (trip.optDouble("duration_seconds") / 60.0).toInt()
                val activeSeconds = trip.optDouble("active_duration_seconds", trip.optDouble("duration_seconds"))
                Card(
                    onClick = {
                        isPlaying = false
                        replayIndex = 0f
                        onSelectTrip(if (selectedTripId == tripId) null else tripId)
                    },
                    modifier = Modifier.fillMaxWidth(),
                ) {
                    Column(Modifier.fillMaxWidth().padding(12.dp), verticalArrangement = Arrangement.spacedBy(3.dp)) {
                        Text("Trip ${trips.size - index} · ${"%.2f".format(Locale.US, distanceKm)} km", style = MaterialTheme.typography.titleSmall)
                        Text(
                            "${trip.optInt("point_count")} fixes · $durationMinutes min · " +
                                "${trip.optInt("stop_count")} stops · ${formatDuration(activeSeconds)} active",
                            style = MaterialTheme.typography.bodySmall,
                        )
                        Text(
                            "Avg ${trip.optDouble("average_speed", 0.0).times(3.6).toInt()} km/h · " +
                                "max ${trip.optDouble("maximum_speed", 0.0).times(3.6).toInt()} km/h",
                            style = MaterialTheme.typography.bodySmall,
                        )
                        Text("${trip.optString("start_time")} → ${trip.optString("end_time")}", style = MaterialTheme.typography.bodySmall)
                    }
                }
            }
            if (selectedTripId.isNotBlank() && history.size > 1) {
                Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                    TextButton(onClick = { isPlaying = !isPlaying }) {
                        Text(if (isPlaying) "Pause replay" else "Play replay")
                    }
                    Slider(
                        value = replayIndex.coerceIn(0f, (history.lastIndex).toFloat()),
                        onValueChange = {
                            isPlaying = false
                            replayIndex = it
                        },
                        valueRange = 0f..history.lastIndex.toFloat(),
                        modifier = Modifier.weight(1f),
                    )
                    Text("${replayIndex.toInt() + 1}/${history.size}", style = MaterialTheme.typography.labelSmall)
                }
                history.getOrNull(replayIndex.toInt())?.let { point ->
                    Text("${formatTime(point.timestamp)} · replay position", style = MaterialTheme.typography.bodySmall)
                }
            }
        }
    }
    if (history.isEmpty()) {
        Column(Modifier.fillMaxSize().padding(24.dp), verticalArrangement = Arrangement.Center) {
            Text(
                if (isLoading) "Loading route history…" else "No route history for this period.",
                style = MaterialTheme.typography.titleMedium,
            )
            Text("Select a device above. Recorded trips and location points appear here.")
        }
        return
    }
    val routePoints = history.map { LatLng(it.latitude, it.longitude) }
    val cameraState = rememberCameraPositionState {
        position = CameraPosition.fromLatLngZoom(routePoints.first(), 13f)
    }
    GoogleMap(
        modifier = Modifier.fillMaxWidth().height(300.dp).padding(horizontal = 16.dp),
        cameraPositionState = cameraState,
        uiSettings = MapUiSettings(zoomControlsEnabled = true),
    ) {
        if (routePoints.size > 1) {
            Polyline(points = routePoints, color = MaterialTheme.colorScheme.primary, width = 5f)
        }
        val replayPoint = if (selectedTripId.isNotBlank()) routePoints.getOrNull(replayIndex.toInt()) else null
        Marker(
            state = MarkerState(position = replayPoint ?: routePoints.last()),
            title = if (replayPoint != null) "Route replay" else "Latest recorded point",
        )
    }
    LazyColumn(
        Modifier.fillMaxSize().padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        item {
            Text("ROUTE HISTORY", style = MaterialTheme.typography.titleLarge)
            Text("${history.size} points · $selectedPeriod")
        }
        items(history.asReversed()) { point ->
            Card(Modifier.fillMaxWidth()) {
                Column(Modifier.fillMaxWidth().padding(14.dp)) {
                    Text("${"%.6f".format(Locale.US, point.latitude)}, ${"%.6f".format(Locale.US, point.longitude)}")
                    Text("${formatTime(point.timestamp)} · ${point.movementState.name.lowercase()}")
                    point.accuracy?.let { Text("Reported accuracy ±${it.toInt()} m") }
                }
            }
        }
    }
}

@Composable
private fun MessageCard(message: String, onDismiss: () -> Unit, isError: Boolean) {
    Card(
        Modifier.fillMaxWidth().padding(horizontal = 12.dp, vertical = 4.dp),
        colors = CardDefaults.cardColors(
            containerColor = if (isError) MaterialTheme.colorScheme.errorContainer else MaterialTheme.colorScheme.secondaryContainer,
        ),
    ) {
        Row(
            Modifier.fillMaxWidth().padding(start = 12.dp, end = 4.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.SpaceBetween,
        ) {
            Text(message, Modifier.weight(1f))
            TextButton(onClick = onDismiss) { Text("Dismiss") }
        }
    }
}

@Composable
private fun statusColor(status: DeviceStatus) =
    if (status == DeviceStatus.ONLINE) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.onSurfaceVariant

private fun statusLabel(status: DeviceStatus): String = when (status) {
    DeviceStatus.ONLINE -> "ONLINE"
    DeviceStatus.RECENTLY_OFFLINE -> "RECENTLY OFFLINE"
    DeviceStatus.OFFLINE -> "OFFLINE"
    DeviceStatus.SLEEPING -> "SLEEPING"
    DeviceStatus.POWERED_OFF -> "POWERED OFF"
    DeviceStatus.LOCATION_UNAVAILABLE -> "NO LOCATION"
    DeviceStatus.UNKNOWN -> "UNKNOWN"
}

private fun formatTime(timestamp: Long): String =
    DateFormat.getDateTimeInstance(DateFormat.SHORT, DateFormat.SHORT).format(Date(timestamp))

private fun formatDuration(seconds: Double): String {
    val minutes = seconds.coerceAtLeast(0.0).toLong() / 60
    return if (minutes < 60) "$minutes min" else "${minutes / 60} h ${minutes % 60} min"
}

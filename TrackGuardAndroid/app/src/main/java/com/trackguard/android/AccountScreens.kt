package com.trackguard.android

import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.text.selection.SelectionContainer
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.FilterChip
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import org.json.JSONObject

@Composable
internal fun AccountToolsScreen(
    state: TrackGuardUiState,
    section: String,
    onSectionChanged: (String) -> Unit,
    onRefresh: () -> Unit,
    onSignOut: () -> Unit,
    onPolicyChanged: (String) -> Unit,
    onCreateGeofence: (String, Double, Double, Double) -> Unit,
    onSetGeofenceEnabled: (String, Boolean) -> Unit,
    onDeleteGeofence: (String) -> Unit,
    onSendSos: (String?, String) -> Unit,
    onExportAccountData: () -> Unit,
    onShareAccountExport: (String) -> Unit,
    onDeleteLocationHistory: () -> Unit,
    onMarkAlertRead: (String) -> Unit,
    onUpdateAlertStatus: (String, String) -> Unit,
    onMarkAllAlertsRead: () -> Unit,
    onDecideAccessRequest: (String, String) -> Unit,
    onCreateAdminUser: (String, String, String) -> Unit,
    onCreateAdminInvitation: (String) -> Unit,
    onUpdateAdminUser: (String, String?, String?) -> Unit,
    onUpdateAdminIncident: (String, String) -> Unit,
    onResetAuthenticator: (String) -> Unit,
    onRequestAdminAccess: (String, String, String?, String, Int) -> Unit,
    onRevokeAdminAccess: (String) -> Unit,
    onShowGrantedLocations: (String) -> Unit,
    onShowGrantedHistory: (String, String, String) -> Unit,
    onExportAdminCsv: (String, String) -> Unit,
    onSendGrantedDeviceCommand: (String, String, String, String) -> Unit,
    onDismissSetupSecret: () -> Unit,
    onProximityThresholdChanged: (Int) -> Unit,
) {
    val sections = buildList {
        add("Account")
        add("Proximity")
        add("Places")
        add("Alerts")
        add("Approvals")
        add("Privacy")
        if (state.role == "ADMIN" || state.role == "SUPER_ADMIN") add("Admin")
    }
    Column(Modifier.fillMaxSize()) {
        Row(
            Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()).padding(horizontal = 12.dp),
            horizontalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            sections.forEach { item ->
                FilterChip(
                    selected = section == item,
                    onClick = { onSectionChanged(item) },
                    label = { Text(item) },
                )
            }
            TextButton(onClick = onRefresh, enabled = !state.isPageLoading) {
                Text(if (state.isPageLoading) "Loading…" else "Refresh")
            }
        }

        state.oneTimeSetupSecret?.let { secret ->
            Card(
                Modifier.fillMaxWidth().padding(horizontal = 12.dp, vertical = 4.dp),
                colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.tertiaryContainer),
            ) {
                Column(Modifier.fillMaxWidth().padding(14.dp)) {
                    Text("${state.oneTimeSetupLabel} — show once", style = MaterialTheme.typography.titleMedium)
                    Text(
                        "Share privately. Invitation codes expire in 48 hours; authenticator reset keys must be enrolled immediately.",
                        style = MaterialTheme.typography.bodySmall,
                    )
                    Spacer(Modifier.height(8.dp))
                    SelectionContainer { Text(secret, style = MaterialTheme.typography.titleLarge) }
                    TextButton(onClick = onDismissSetupSecret) { Text("Dismiss") }
                }
            }
        }

        when (section) {
            "Proximity" -> DeviceProximityScreen(
                state = state,
                onThresholdChanged = onProximityThresholdChanged,
            )
            "Places" -> PlacesScreen(state, onCreateGeofence, onSetGeofenceEnabled, onDeleteGeofence)
            "Alerts" -> AlertsScreen(
                state,
                onSendSos,
                onMarkAlertRead,
                onUpdateAlertStatus,
                onMarkAllAlertsRead,
            )
            "Approvals" -> OwnerApprovalsScreen(state, onDecideAccessRequest)
            "Privacy" -> PrivacyScreen(
                state,
                onExportAccountData,
                onShareAccountExport,
                onDeleteLocationHistory,
            )
            "Admin" -> if (state.role == "ADMIN" || state.role == "SUPER_ADMIN") {
                AdminPanelScreen(
                    state = state,
                    onCreateUser = onCreateAdminUser,
                    onCreateInvitation = onCreateAdminInvitation,
                    onUpdateUser = onUpdateAdminUser,
                    onUpdateIncident = onUpdateAdminIncident,
                    onResetAuthenticator = onResetAuthenticator,
                    onRequestAccess = onRequestAdminAccess,
                    onRevokeAccess = onRevokeAdminAccess,
                    onShowLocations = onShowGrantedLocations,
                    onShowHistory = onShowGrantedHistory,
                    onExportCsv = onExportAdminCsv,
                    onSendCommand = onSendGrantedDeviceCommand,
                )
            } else {
                AccountScreen(state, onSignOut, onPolicyChanged)
            }
            else -> AccountScreen(state, onSignOut, onPolicyChanged)
        }
    }
}

@Composable
private fun DeviceProximityScreen(
    state: TrackGuardUiState,
    onThresholdChanged: (Int) -> Unit,
) {
    val snapshot = state.proximitySnapshot
    val pairs = snapshot?.optJSONArray("pairs")
    Column(
        Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        PageTitle(
            "Device proximity",
            "Compare the latest reported positions of your own devices.",
        )
        Text(
            "Only your account's paired devices are compared. A fix older than " +
                "${snapshot?.optInt("freshness_limit_minutes", 10) ?: 10} minutes or a pair of fixes more than " +
                "${snapshot?.optInt("max_fix_skew_minutes", 5) ?: 5} minutes apart is marked unknown. " +
                "Reported accuracy is included; this is an estimate, not a live Bluetooth connection.",
            style = MaterialTheme.typography.bodySmall,
        )
        Row(
            Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()),
            horizontalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            listOf(100, 250, 500, 1000).forEach { threshold ->
                FilterChip(
                    selected = state.proximityThresholdMeters == threshold,
                    onClick = { onThresholdChanged(threshold) },
                    enabled = !state.isPageLoading,
                    label = { Text("$threshold m") },
                )
            }
        }
        if (state.isPageLoading && pairs == null) {
            Text("Calculating device proximity…", style = MaterialTheme.typography.bodyMedium)
        } else if (pairs == null || pairs.length() == 0) {
            Card(Modifier.fillMaxWidth()) {
                Column(Modifier.fillMaxWidth().padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text("No device pairs to compare", style = MaterialTheme.typography.titleMedium)
                    Text(
                        "Pair at least two devices with this account and enable location reporting to see their estimated separation.",
                        style = MaterialTheme.typography.bodySmall,
                    )
                }
            }
        } else {
            Text(
                "${pairs.length()} pairs · ${snapshot.optInt("threshold_meters", state.proximityThresholdMeters)} m threshold",
                style = MaterialTheme.typography.labelLarge,
            )
            for (index in 0 until pairs.length()) {
                val pair = pairs.optJSONObject(index) ?: continue
                val distance = if (pair.isNull("last_known_distance_meters")) {
                    null
                } else {
                    pair.optDouble("last_known_distance_meters").takeUnless(Double::isNaN)
                }
                val distanceLabel = when {
                    distance == null -> "No distance available"
                    distance >= 1000 -> String.format(java.util.Locale.US, "%.2f km", distance / 1000)
                    else -> "${distance.toInt()} m"
                }
                val firstName = pair.optString("first_device_name", "Device")
                val secondName = pair.optString("second_device_name", "Device")
                val proximityStatus = pair.optString("status", "UNKNOWN")
                val firstAccuracy = proximityAccuracy(pair, "first_accuracy_meters")
                val secondAccuracy = proximityAccuracy(pair, "second_accuracy_meters")
                val firstFix = proximityTimestamp(pair, "first_location_time")
                val secondFix = proximityTimestamp(pair, "second_location_time")
                Card(Modifier.fillMaxWidth()) {
                    Column(
                        Modifier.fillMaxWidth().padding(14.dp),
                        verticalArrangement = Arrangement.spacedBy(6.dp),
                    ) {
                        Text("$firstName ↔ $secondName", style = MaterialTheme.typography.titleMedium)
                        Text(
                            "${proximityStatus.lowercase().replace('_', ' ')} · last known separation $distanceLabel",
                            style = MaterialTheme.typography.bodyMedium,
                        )
                        Text(
                            "$firstName fix: $firstFix · accuracy $firstAccuracy",
                            style = MaterialTheme.typography.bodySmall,
                        )
                        Text(
                            "$secondName fix: $secondFix · accuracy $secondAccuracy",
                            style = MaterialTheme.typography.bodySmall,
                        )
                        val leftBehindName = pair.optString("possible_left_behind_device_name")
                            .takeUnless { it.isBlank() || it == "null" }
                        if (leftBehindName != null) {
                            Text(
                                "Possible separation: $leftBehindName last reported stationary while the other device was moving. Verify directly; this does not prove it was left behind.",
                                color = MaterialTheme.colorScheme.error,
                                style = MaterialTheme.typography.bodySmall,
                            )
                        }
                        if (proximityStatus == "UNKNOWN") {
                            Text(
                                "A location fix is missing or stale, the fixes are far apart in time, or a timestamp is too far in the future. Any distance shown is historical, not current.",
                                style = MaterialTheme.typography.bodySmall,
                            )
                        } else if (proximityStatus == "UNCERTAIN") {
                            Text(
                                "The reported accuracy overlaps the threshold or is unavailable, so TrackGuard cannot classify this pair as near or separated.",
                                style = MaterialTheme.typography.bodySmall,
                            )
                        }
                    }
                }
            }
        }
    }
}

private fun proximityAccuracy(pair: JSONObject, field: String): String {
    if (pair.isNull(field)) return "not reported"
    val accuracy = pair.optDouble(field, Double.NaN)
    return if (accuracy.isFinite() && accuracy >= 0) "±${accuracy.toInt()} m" else "not reported"
}

private fun proximityTimestamp(pair: JSONObject, field: String): String =
    pair.optString(field).takeUnless { it.isBlank() || it == "null" } ?: "No fix"

@Composable
private fun PrivacyScreen(
    state: TrackGuardUiState,
    onExport: () -> Unit,
    onShareExport: (String) -> Unit,
    onDeleteHistory: () -> Unit,
) {
    var showDeleteConfirmation by rememberSaveable { mutableStateOf(false) }
    var confirmationText by rememberSaveable { mutableStateOf("") }
    Column(
        Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        PageTitle("Privacy & data", "Owner-controlled location access and account data")
        Card(Modifier.fillMaxWidth()) {
            Column(Modifier.fillMaxWidth().padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Text("Access and retention", style = MaterialTheme.typography.titleMedium)
                Text("Administrator location access requires owner approval and expires. Review or revoke it in Approvals. Device control is a separate, device-scoped grant.")
                Text("Location history is retained until you delete it.")
                Button(
                    onClick = onExport,
                    enabled = !state.isPageLoading,
                    modifier = Modifier.fillMaxWidth(),
                ) { Text(if (state.isPageLoading) "Preparing export…" else "Prepare account data export") }
                if (state.accountExportJson.isNotBlank()) {
                    OutlinedButton(
                        onClick = { onShareExport(state.accountExportJson) },
                        enabled = !state.isPageLoading,
                        modifier = Modifier.fillMaxWidth(),
                    ) { Text("Share JSON export") }
                }
            }
        }
        Card(
            Modifier.fillMaxWidth(),
            colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.errorContainer),
        ) {
            Column(Modifier.fillMaxWidth().padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Text("Delete location history", style = MaterialTheme.typography.titleMedium)
                Text("Permanently removes saved location points from all your devices, so trip reports and route playback based on them will no longer be available. Your account, devices, alerts, geofences, and access requests remain.")
                OutlinedButton(
                    onClick = { showDeleteConfirmation = true },
                    enabled = !state.isPageLoading,
                    modifier = Modifier.fillMaxWidth(),
                ) { Text("Permanently delete location history") }
            }
        }
    }
    if (showDeleteConfirmation) {
        AlertDialog(
            onDismissRequest = {
                showDeleteConfirmation = false
                confirmationText = ""
            },
            title = { Text("Delete all location history?") },
            text = {
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text("This action cannot be undone. Type DELETE MY LOCATION HISTORY to confirm.")
                    OutlinedTextField(
                        value = confirmationText,
                        onValueChange = { confirmationText = it },
                        label = { Text("Confirmation phrase") },
                        singleLine = true,
                    )
                }
            },
            confirmButton = {
                TextButton(
                    enabled = confirmationText == "DELETE MY LOCATION HISTORY" && !state.isPageLoading,
                    onClick = {
                        showDeleteConfirmation = false
                        confirmationText = ""
                        onDeleteHistory()
                    },
                ) { Text("Delete history") }
            },
            dismissButton = {
                TextButton(onClick = {
                    showDeleteConfirmation = false
                    confirmationText = ""
                }) { Text("Cancel") }
            },
        )
    }
}

@Composable
private fun AccountScreen(
    state: TrackGuardUiState,
    onSignOut: () -> Unit,
    onPolicyChanged: (String) -> Unit,
) {
    Column(
        Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        PageTitle("Your account", "Account and this phone's tracking settings")
        Card(Modifier.fillMaxWidth()) {
            Column(Modifier.fillMaxWidth().padding(16.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                Text(state.userName.ifBlank { "TrackGuard user" }, style = MaterialTheme.typography.titleLarge)
                Text(state.phoneNumber.ifBlank { "Phone number unavailable" })
                Text(state.email)
                Text("Role: ${state.role} · ${state.accountStatus}")
                Text("Signed in on ${state.deviceName}", style = MaterialTheme.typography.bodySmall)
            }
        }
        Card(Modifier.fillMaxWidth()) {
            Column(Modifier.fillMaxWidth().padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Text("Tracking policy", style = MaterialTheme.typography.titleMedium)
                Text("Choose how often this phone checks for location updates while tracking.")
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    listOf(
                        "Normal" to "normal",
                        "High accuracy" to "high_accuracy",
                        "Battery saver" to "battery_saver",
                    ).forEach { (label, value) ->
                        FilterChip(
                            selected = state.policy == value,
                            onClick = { onPolicyChanged(value) },
                            label = { Text(label) },
                        )
                    }
                }
                Text(
                    "Location tracking uses a visible foreground service. Stop tracking or sign out at any time.",
                    style = MaterialTheme.typography.bodySmall,
                )
            }
        }
        Card(Modifier.fillMaxWidth()) {
            Column(Modifier.fillMaxWidth().padding(16.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                Text("Privacy and security", style = MaterialTheme.typography.titleMedium)
                Text("Your phone number identifies your account; it is not verified by SMS.")
                Text("Authenticator codes and device locations are sent to your configured TrackGuard server.")
                Text("Location access requests from administrators are reviewed separately in Approvals.")
            }
        }
        OutlinedButton(onClick = onSignOut, modifier = Modifier.fillMaxWidth()) {
            Text("Sign out on this phone")
        }
    }
}

@Composable
private fun PlacesScreen(
    state: TrackGuardUiState,
    onCreate: (String, Double, Double, Double) -> Unit,
    onToggle: (String, Boolean) -> Unit,
    onDelete: (String) -> Unit,
) {
    var name by rememberSaveable { mutableStateOf("") }
    var latitude by rememberSaveable { mutableStateOf("") }
    var longitude by rememberSaveable { mutableStateOf("") }
    var radius by rememberSaveable { mutableStateOf("200") }
    var saveAttempted by rememberSaveable { mutableStateOf(false) }
    val parsedLatitude = latitude.toDoubleOrNull()
    val parsedLongitude = longitude.toDoubleOrNull()
    val parsedRadius = radius.toDoubleOrNull()
    val validLatitude = parsedLatitude != null && parsedLatitude.isFinite() && parsedLatitude in -90.0..90.0
    val validLongitude = parsedLongitude != null && parsedLongitude.isFinite() && parsedLongitude in -180.0..180.0
    val validRadius = parsedRadius != null && parsedRadius.isFinite() && parsedRadius > 0
    Column(
        Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        PageTitle("Geofences", "Create saved places and receive boundary alerts")
        OutlinedTextField(name, { name = it }, label = { Text("Place name") }, singleLine = true, modifier = Modifier.fillMaxWidth())
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            OutlinedTextField(
                latitude, { latitude = it }, label = { Text("Latitude") }, singleLine = true,
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal), modifier = Modifier.weight(1f),
            )
            OutlinedTextField(
                longitude, { longitude = it }, label = { Text("Longitude") }, singleLine = true,
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal), modifier = Modifier.weight(1f),
            )
        }
        OutlinedTextField(
            radius, { radius = it }, label = { Text("Radius (meters)") }, singleLine = true,
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal), modifier = Modifier.fillMaxWidth(),
        )
        Button(
            onClick = {
                saveAttempted = true
                if (name.isNotBlank() && validLatitude && validLongitude && validRadius) {
                    onCreate(
                        name.trim(),
                        requireNotNull(parsedLatitude),
                        requireNotNull(parsedLongitude),
                        requireNotNull(parsedRadius),
                    )
                    name = ""
                    latitude = ""
                    longitude = ""
                    radius = "200"
                    saveAttempted = false
                }
            },
            enabled = !state.isPageLoading && name.isNotBlank(),
            modifier = Modifier.fillMaxWidth(),
        ) { Text("Save geofence") }
        if (saveAttempted) {
            val validationMessage = when {
                name.isBlank() -> "Enter a place name."
                !validLatitude -> "Latitude must be a number between -90 and 90."
                !validLongitude -> "Longitude must be a number between -180 and 180."
                !validRadius -> "Radius must be a positive number of meters."
                else -> null
            }
            validationMessage?.let {
                Text(it, color = MaterialTheme.colorScheme.error)
            }
        }

        Text("Saved places", style = MaterialTheme.typography.titleLarge)
        if (state.geofences.isEmpty()) Text("No geofences yet.")
        state.geofences.forEach { fence ->
            val id = fence.optString("id")
            Card(Modifier.fillMaxWidth()) {
                Column(Modifier.fillMaxWidth().padding(14.dp)) {
                    Text(fence.optString("name"), style = MaterialTheme.typography.titleMedium)
                    Text(
                        "${fence.optDouble("latitude")}, ${fence.optDouble("longitude")} · " +
                            "${fence.optDouble("radius").toInt()} m",
                    )
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        TextButton(
                            enabled = !state.isPageLoading,
                            onClick = { onToggle(id, !fence.optBoolean("enabled")) },
                        ) { Text(if (fence.optBoolean("enabled")) "Disable" else "Enable") }
                        TextButton(enabled = !state.isPageLoading, onClick = { onDelete(id) }) { Text("Delete") }
                    }
                }
            }
        }
    }
}

@Composable
private fun AlertsScreen(
    state: TrackGuardUiState,
    onSendSos: (String?, String) -> Unit,
    onMarkRead: (String) -> Unit,
    onUpdateStatus: (String, String) -> Unit,
    onMarkAllRead: () -> Unit,
) {
    var message by rememberSaveable { mutableStateOf("Emergency assistance requested") }
    var selectedDeviceId by rememberSaveable { mutableStateOf("") }
    var alertFilter by rememberSaveable { mutableStateOf("ALL") }
    val filteredAlerts = state.alerts.filter { alert ->
        when (alertFilter) {
            "UNREAD" -> !alert.optBoolean("read")
            "SOS" -> alert.optString("type") == "SOS"
            "GEOFENCE" -> alert.optString("type").startsWith("GEOFENCE")
            else -> true
        }
    }
    val activeIncidentCount = state.alerts.count {
        it.optString("status", "OPEN") != "RESOLVED" &&
            it.optString("type") in setOf("DEVICE_OFFLINE", "LOW_BATTERY", "SOS")
    }
    var confirmSos by remember { mutableStateOf(false) }
    Column(
        Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        PageTitle("Incident center", "$activeIncidentCount active incidents · persistent account alerts")
        Card(
            Modifier.fillMaxWidth(),
            colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.errorContainer),
        ) {
            Column(Modifier.fillMaxWidth().padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Text("Send an SOS alert", style = MaterialTheme.typography.titleMedium)
                Text("This creates a TrackGuard alert only. It does not contact emergency services.")
                Text("Associated device (optional)", style = MaterialTheme.typography.labelMedium)
                Row(Modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    FilterChip(selectedDeviceId.isBlank(), { selectedDeviceId = "" }, label = { Text("Account") })
                    state.devices.forEach { device ->
                        FilterChip(
                            selected = selectedDeviceId == device.id,
                            onClick = { selectedDeviceId = device.id },
                            label = { Text(device.name) },
                        )
                    }
                }
                OutlinedTextField(
                    value = message,
                    onValueChange = { message = it.take(500) },
                    label = { Text("Message") },
                    modifier = Modifier.fillMaxWidth(),
                )
                Button(
                    onClick = { confirmSos = true },
                    enabled = !state.isPageLoading && message.isNotBlank(),
                    modifier = Modifier.fillMaxWidth(),
                ) { Text("Send SOS") }
            }
        }
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
            Text("Notifications", style = MaterialTheme.typography.titleLarge)
            TextButton(
                onClick = onMarkAllRead,
                enabled = !state.isPageLoading && state.alerts.any { !it.optBoolean("read") },
            ) { Text("Mark all read") }
        }
        Row(
            Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()),
            horizontalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            listOf("ALL" to "All", "UNREAD" to "Unread", "SOS" to "SOS", "GEOFENCE" to "Geofence").forEach { (filter, label) ->
                FilterChip(alertFilter == filter, { alertFilter = filter }, label = { Text(label) })
            }
        }
        filteredAlerts.forEach { alert ->
            Card(Modifier.fillMaxWidth()) {
                Column(Modifier.fillMaxWidth().padding(14.dp)) {
                    Text(alert.optString("title"), style = MaterialTheme.typography.titleMedium)
                    Text(alert.optString("message"))
                    Text(
                        "${alert.optString("type")} · ${alert.optString("status", "OPEN")} · ${alert.optString("created_at")}",
                        style = MaterialTheme.typography.bodySmall,
                    )
                    Row {
                        if (alert.optString("status", "OPEN") == "OPEN") {
                            TextButton(
                                enabled = !state.isPageLoading,
                                onClick = { onUpdateStatus(alert.optString("id"), "ACKNOWLEDGED") },
                            ) { Text("Acknowledge") }
                        }
                        if (alert.optString("status", "OPEN") != "RESOLVED") {
                            TextButton(
                                enabled = !state.isPageLoading,
                                onClick = { onUpdateStatus(alert.optString("id"), "RESOLVED") },
                            ) { Text("Resolve") }
                        }
                        if (!alert.optBoolean("read")) {
                            TextButton(
                                enabled = !state.isPageLoading,
                                onClick = { onMarkRead(alert.optString("id")) },
                            ) { Text("Mark read") }
                        }
                    }
                }
            }
        }
        if (filteredAlerts.isEmpty()) Text(if (state.alerts.isEmpty()) "No alerts yet." else "No alerts match this filter.")
    }
    if (confirmSos) {
        AlertDialog(
            onDismissRequest = { confirmSos = false },
            title = { Text("Confirm SOS") },
            text = { Text("Create an in-app SOS alert? It will not call emergency services.") },
            confirmButton = {
                TextButton(onClick = {
                    confirmSos = false
                    onSendSos(selectedDeviceId.takeIf(String::isNotBlank), message.trim())
                }) { Text("Send alert") }
            },
            dismissButton = { TextButton(onClick = { confirmSos = false }) { Text("Cancel") } },
        )
    }
}

@Composable
private fun OwnerApprovalsScreen(
    state: TrackGuardUiState,
    onDecide: (String, String) -> Unit,
) {
    Column(
        Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        PageTitle("Access approvals", "Review and revoke administrator access")
        Text("Location viewing and device control are separate permissions. Device control is restricted to the device shown.")
        if (state.ownerAccessRequests.isEmpty()) Text("No administrator access requests.")
        state.ownerAccessRequests.forEach { access ->
            val status = access.optString("status")
            val scope = access.optString("scope")
            Card(Modifier.fillMaxWidth()) {
                Column(Modifier.fillMaxWidth().padding(14.dp), verticalArrangement = Arrangement.spacedBy(5.dp)) {
                    Text(
                        "${access.optString("requester_name")} · " +
                            if (scope == "DEVICE_CONTROL") "Device control" else "Location access",
                        style = MaterialTheme.typography.titleMedium,
                    )
                    Text(access.optString("reason"))
                    if (scope == "DEVICE_CONTROL") {
                        Text("Device: ${access.optString("target_device_name", "Unavailable")}")
                    }
                    Text("$status · ${access.optInt("duration_minutes")} minutes")
                    if (access.optString("expires_at") != "null" && access.optString("expires_at").isNotBlank()) {
                        Text("Expires ${access.optString("expires_at")}", style = MaterialTheme.typography.bodySmall)
                    }
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        if (status == "PENDING") {
                            Button(
                                enabled = !state.isPageLoading,
                                onClick = { onDecide(access.optString("id"), "APPROVE") },
                            ) { Text("Approve") }
                            OutlinedButton(
                                enabled = !state.isPageLoading,
                                onClick = { onDecide(access.optString("id"), "DENY") },
                            ) { Text("Deny") }
                        } else if (status == "APPROVED") {
                            OutlinedButton(
                                enabled = !state.isPageLoading,
                                onClick = { onDecide(access.optString("id"), "REVOKE") },
                            ) { Text("Revoke access") }
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun AdminPanelScreen(
    state: TrackGuardUiState,
    onCreateUser: (String, String, String) -> Unit,
    onCreateInvitation: (String) -> Unit,
    onUpdateUser: (String, String?, String?) -> Unit,
    onUpdateIncident: (String, String) -> Unit,
    onResetAuthenticator: (String) -> Unit,
    onRequestAccess: (String, String, String?, String, Int) -> Unit,
    onRevokeAccess: (String) -> Unit,
    onShowLocations: (String) -> Unit,
    onShowHistory: (String, String, String) -> Unit,
    onExportCsv: (String, String) -> Unit,
    onSendCommand: (String, String, String, String) -> Unit,
) {
    var page by rememberSaveable { mutableStateOf("Overview") }
    var searchQuery by rememberSaveable { mutableStateOf("") }
    var statusFilter by rememberSaveable { mutableStateOf("ALL") }
    var name by rememberSaveable { mutableStateOf("") }
    var phone by rememberSaveable { mutableStateOf("") }
    var newRole by rememberSaveable { mutableStateOf("USER") }
    var selectedUserId by rememberSaveable { mutableStateOf("") }
    var selectedDeviceId by rememberSaveable { mutableStateOf("") }
    var scope by rememberSaveable { mutableStateOf("LOCATION_READ") }
    var reason by rememberSaveable { mutableStateOf("") }
    var duration by rememberSaveable { mutableStateOf(60) }
    var pendingCommand by remember { mutableStateOf<PendingAdminCommand?>(null) }
    var confirmation by rememberSaveable { mutableStateOf("") }
    val pages = listOf("Overview", "Accounts", "Devices", "Incidents", "Access", "Audit")
    val query = searchQuery.trim()
    val filteredUsers = state.adminUsers.filter { account ->
        val matchesQuery = query.isBlank() || account.toString().contains(query, ignoreCase = true)
        matchesQuery && (statusFilter == "ALL" || account.optString("account_status") == statusFilter)
    }
    val filteredDevices = state.adminDevices.filter { device ->
        val matchesQuery = query.isBlank() || device.toString().contains(query, ignoreCase = true)
        matchesQuery && (statusFilter == "ALL" || device.optString("status").equals(statusFilter, ignoreCase = true))
    }
    val filteredAccess = state.adminAccessRequests.filter { access ->
        val matchesQuery = query.isBlank() || access.toString().contains(query, ignoreCase = true)
        matchesQuery && (statusFilter == "ALL" || access.optString("status") == statusFilter)
    }
    val filteredAudit = state.adminAudit.filter { event ->
        val matchesQuery = query.isBlank() || event.toString().contains(query, ignoreCase = true)
        matchesQuery && (statusFilter == "ALL" || event.optString("action") == statusFilter)
    }
    val filteredIncidents = state.adminIncidents.filter { incident ->
        val matchesQuery = query.isBlank() || incident.toString().contains(query, ignoreCase = true)
        matchesQuery && (statusFilter == "ALL" || incident.optString("status") == statusFilter)
    }

    Column(Modifier.fillMaxSize()) {
        Row(
            Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()).padding(horizontal = 12.dp),
            horizontalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            pages.forEach { item ->
                FilterChip(
                    page == item,
                    {
                        page = item
                        statusFilter = "ALL"
                    },
                    label = { Text(item) },
                )
            }
        }
        Column(
            Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            PageTitle("Administrator console", "Signed in as ${state.userName} · ${state.role}")
            OutlinedTextField(
                value = searchQuery,
                onValueChange = { searchQuery = it },
                label = { Text("Search this administrator console") },
                modifier = Modifier.fillMaxWidth(),
                singleLine = true,
            )
            val filters = when (page) {
                "Accounts" -> listOf("ALL", "ACTIVE", "SUSPENDED")
                "Devices" -> listOf("ALL") + state.adminDevices.map { it.optString("status") }.filter(String::isNotBlank).distinct()
                "Incidents" -> listOf("ALL", "OPEN", "ACKNOWLEDGED", "RESOLVED")
                "Access" -> listOf("ALL", "PENDING", "APPROVED", "DENIED", "REVOKED", "EXPIRED")
                "Audit" -> listOf("ALL") + state.adminAudit.map { it.optString("action") }.filter(String::isNotBlank).distinct()
                else -> emptyList()
            }
            if (filters.isNotEmpty()) {
                Row(
                    Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()),
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                ) {
                    filters.forEach { filter ->
                        FilterChip(
                            selected = statusFilter.equals(filter, ignoreCase = true),
                            onClick = { statusFilter = filter },
                            label = { Text(filter) },
                        )
                    }
                }
            }
            val exportRows = when (page) {
                "Accounts" -> filteredUsers
                "Devices" -> filteredDevices
                "Incidents" -> filteredIncidents
                "Access" -> filteredAccess
                "Audit" -> filteredAudit
                else -> emptyList()
            }
            if (page != "Overview") {
                OutlinedButton(
                    onClick = { onExportCsv("trackguard-${page.lowercase()}.csv", exportRows.toCsv()) },
                    enabled = exportRows.isNotEmpty(),
                    modifier = Modifier.fillMaxWidth(),
                ) { Text("Share filtered ${page.lowercase()} CSV (${exportRows.size})") }
            }
            when (page) {
                "Accounts" -> {
                    Text("Provision an account", style = MaterialTheme.typography.titleLarge)
                    OutlinedTextField(name, { name = it }, label = { Text("Account holder name") }, singleLine = true, modifier = Modifier.fillMaxWidth())
                    OutlinedTextField(
                        phone, { phone = it }, label = { Text("Phone in E.164 format") },
                        placeholder = { Text("+14155550123") }, singleLine = true, modifier = Modifier.fillMaxWidth(),
                    )
                    if (state.role == "SUPER_ADMIN") {
                        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            listOf("USER", "ADMIN").forEach { role ->
                                FilterChip(newRole == role, { newRole = role }, label = { Text(role) })
                            }
                        }
                    }
                    Button(
                        onClick = {
                            onCreateUser(name.trim(), phone.trim(), newRole)
                            name = ""
                            phone = ""
                        },
                        enabled = !state.isPageLoading && name.isNotBlank() && phone.startsWith("+"),
                        modifier = Modifier.fillMaxWidth(),
                    ) { Text("Create account") }
                    Text("Share one-time invitation codes privately. The recipient verifies their phone and sets up their own authenticator.")
                    Text("Accounts", style = MaterialTheme.typography.titleLarge)
                    filteredUsers.forEach { account ->
                        AdminAccountCard(
                            account = account,
                            currentUserId = state.userId,
                            canManageSuperAdmin = state.role == "SUPER_ADMIN",
                            isBusy = state.isPageLoading,
                            onUpdate = onUpdateUser,
                            onCreateInvitation = onCreateInvitation,
                            onResetAuthenticator = onResetAuthenticator,
                        )
                    }
                }
                "Devices" -> {
                    Text("Platform inventory · coordinates are intentionally withheld", style = MaterialTheme.typography.titleMedium)
                    filteredDevices.forEach { device ->
                        Card(Modifier.fillMaxWidth()) {
                            Column(Modifier.fillMaxWidth().padding(14.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                                Text(device.optString("name"), style = MaterialTheme.typography.titleMedium)
                                Text("${device.optString("owner_name")} · ${device.optString("owner_phone_number")}")
                                Text("${device.optString("platform")} · ${device.optString("device_type")} · ${device.optString("status")}")
                                Text(
                                    "Battery ${device.opt("battery_level")?.toString()?.takeUnless { it == "null" } ?: "unavailable"}" +
                                        " · Lost Mode ${if (device.optBoolean("is_lost_mode")) "on" else "off"}",
                                )
                                Text("Last seen ${device.optString("last_seen")}", style = MaterialTheme.typography.bodySmall)
                            }
                        }
                    }
                }
                "Incidents" -> {
                    Text("Platform incident center · no precise coordinates", style = MaterialTheme.typography.titleLarge)
                    filteredIncidents.forEach { incident ->
                        Card(Modifier.fillMaxWidth()) {
                            Column(
                                Modifier.fillMaxWidth().padding(14.dp),
                                verticalArrangement = Arrangement.spacedBy(5.dp),
                            ) {
                                Text(incident.optString("title"), style = MaterialTheme.typography.titleMedium)
                                Text(incident.optString("message"))
                                Text(
                                    "${incident.optString("user_name")} · ${incident.optString("device_name")} · " +
                                        "${incident.optString("status")} · ${incident.optString("created_at")}",
                                    style = MaterialTheme.typography.bodySmall,
                                )
                                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                                    if (incident.optString("status") == "OPEN") {
                                        TextButton(
                                            enabled = !state.isPageLoading,
                                            onClick = { onUpdateIncident(incident.optString("id"), "ACKNOWLEDGED") },
                                        ) { Text("Acknowledge") }
                                    }
                                    if (incident.optString("status") != "RESOLVED") {
                                        TextButton(
                                            enabled = !state.isPageLoading,
                                            onClick = { onUpdateIncident(incident.optString("id"), "RESOLVED") },
                                        ) { Text("Resolve") }
                                    }
                                }
                            }
                        }
                    }
                    if (filteredIncidents.isEmpty()) Text("No incidents match this filter.")
                }
                "Access" -> {
                    Text("Request limited owner-approved access", style = MaterialTheme.typography.titleLarge)
                    Text("Location grants are read-only. Device-control grants cover exactly one device and expire after 15 minutes.")
                    Text("Target account", style = MaterialTheme.typography.labelLarge)
                    state.adminUsers.filter { it.optString("id") != state.userId && it.optString("account_status") == "ACTIVE" }
                        .forEach { account ->
                            FilterChip(
                                selected = selectedUserId == account.optString("id"),
                                onClick = {
                                    val targetId = account.optString("id")
                                    selectedUserId = targetId
                                    selectedDeviceId = state.adminDevices.firstOrNull {
                                        it.optString("owner_user_id") == targetId
                                    }?.optString("id").orEmpty()
                                },
                                label = { Text("${account.optString("name")} · ${account.optString("phone_number")}") },
                            )
                        }
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        FilterChip(scope == "LOCATION_READ", {
                            scope = "LOCATION_READ"
                            duration = 60
                            selectedDeviceId = ""
                        }, label = { Text("Location + history") })
                        FilterChip(scope == "DEVICE_CONTROL", {
                            scope = "DEVICE_CONTROL"
                            duration = 15
                        }, label = { Text("Control one device") })
                    }
                    if (scope == "DEVICE_CONTROL") {
                        Text("Select one device owned by the selected account", style = MaterialTheme.typography.labelLarge)
                        state.adminDevices.filter { it.optString("owner_user_id") == selectedUserId }.forEach { device ->
                            FilterChip(
                                selected = selectedDeviceId == device.optString("id"),
                                onClick = { selectedDeviceId = device.optString("id") },
                                label = { Text("${device.optString("name")} · ${device.optString("device_type")}") },
                            )
                        }
                    } else {
                        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            listOf(15, 60, 240).forEach { minutes ->
                                FilterChip(
                                    selected = duration == minutes,
                                    onClick = { duration = minutes },
                                    label = { Text(if (minutes < 60) "$minutes min" else "${minutes / 60} hr") },
                                )
                            }
                        }
                    }
                    OutlinedTextField(
                        value = reason,
                        onValueChange = { reason = it.take(500) },
                        label = { Text("Specific reason (at least 10 characters)") },
                        modifier = Modifier.fillMaxWidth(),
                    )
                    Button(
                        onClick = {
                            onRequestAccess(
                                selectedUserId,
                                scope,
                                selectedDeviceId.takeIf { scope == "DEVICE_CONTROL" },
                                reason.trim(),
                                duration,
                            )
                            reason = ""
                        },
                        enabled = !state.isPageLoading && selectedUserId.isNotBlank() &&
                            reason.trim().length >= 10 &&
                            (scope != "DEVICE_CONTROL" || selectedDeviceId.isNotBlank()),
                        modifier = Modifier.fillMaxWidth(),
                    ) { Text("Send owner approval request") }

                    Text("Your access requests", style = MaterialTheme.typography.titleLarge)
                    filteredAccess.forEach { access ->
                        val accessId = access.optString("id")
                        val active = access.optString("status") == "APPROVED" &&
                            !access.isExpired()
                        Card(Modifier.fillMaxWidth()) {
                            Column(Modifier.fillMaxWidth().padding(14.dp), verticalArrangement = Arrangement.spacedBy(5.dp)) {
                                Text("${access.optString("target_name")} · ${access.optString("status")}", style = MaterialTheme.typography.titleMedium)
                                Text("${access.optString("scope")} · ${access.optString("reason")}")
                                if (access.optString("scope") == "DEVICE_CONTROL") {
                                    Text("Approved device: ${access.optString("target_device_name", "Unavailable")}")
                                }
                                Text("${access.optInt("duration_minutes")} minutes")
                                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                                    if (active && access.optString("scope") == "LOCATION_READ") {
                                        TextButton(
                                            enabled = !state.isPageLoading,
                                            onClick = { onShowLocations(accessId) },
                                        ) { Text("View approved locations") }
                                    }
                                    if (access.optString("status") == "PENDING" || active) {
                                        TextButton(
                                            enabled = !state.isPageLoading,
                                            onClick = { onRevokeAccess(accessId) },
                                        ) { Text("Revoke") }
                                    }
                                }
                                if (active && access.optString("scope") == "DEVICE_CONTROL") {
                                    val device = state.adminDevices.firstOrNull {
                                        it.optString("id") == access.optString("target_device_id")
                                    }
                                    if (device == null) {
                                        Text("The approved device is no longer in inventory.")
                                    } else {
                                        AdminDeviceControl(
                                            accessRequestId = accessId,
                                            device = device,
                                            isBusy = state.isPageLoading,
                                            onCommand = { requestId, deviceId, command ->
                                                confirmation = ""
                                                pendingCommand = PendingAdminCommand(requestId, deviceId, device.optString("name"), command)
                                            },
                                        )
                                    }
                                }
                            }
                        }
                    }

                    if (state.grantedLocationsRequestId != null) {
                        Text("Approved device locations", style = MaterialTheme.typography.titleLarge)
                        if (state.grantedLocations.isEmpty()) Text("No devices are registered to this account.")
                        state.grantedLocations.forEach { device ->
                            Card(Modifier.fillMaxWidth()) {
                                Column(Modifier.fillMaxWidth().padding(14.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                                    Text("${device.optString("owner_name")} · ${device.optString("name")}", style = MaterialTheme.typography.titleMedium)
                                    val lat = device.optDouble("last_latitude", Double.NaN)
                                    val lon = device.optDouble("last_longitude", Double.NaN)
                                    Text(
                                        if (lat.isFinite() && lon.isFinite()) "$lat, $lon"
                                        else "No location reported yet.",
                                    )
                                    Text("Accuracy ${device.opt("last_accuracy") ?: "unavailable"} · ${device.optString("last_location_time")}")
                                    TextButton(
                                        enabled = !state.isPageLoading,
                                        onClick = {
                                            onShowHistory(
                                                state.grantedLocationsRequestId.orEmpty(),
                                                device.optString("id"),
                                                device.optString("name"),
                                            )
                                        },
                                    ) { Text("View 7-day history") }
                                }
                            }
                        }
                        if (state.grantedHistoryDeviceName.isNotBlank()) {
                            Text("${state.grantedHistoryDeviceName} · last 7 days", style = MaterialTheme.typography.titleMedium)
                            if (state.grantedHistory.isEmpty()) Text("No location history for this device.")
                            state.grantedHistory.forEach { point ->
                                Text(
                                    "${point.optString("timestamp")} · ${point.optDouble("latitude")}, " +
                                        point.optDouble("longitude"),
                                    style = MaterialTheme.typography.bodySmall,
                                )
                            }
                        }
                    }
                }
                "Audit" -> {
                    Text("Recent administrator audit events", style = MaterialTheme.typography.titleLarge)
                    filteredAudit.forEach { event ->
                        Card(Modifier.fillMaxWidth()) {
                            Column(Modifier.fillMaxWidth().padding(12.dp), verticalArrangement = Arrangement.spacedBy(3.dp)) {
                                Text(event.optString("action"), style = MaterialTheme.typography.titleSmall)
                                Text(event.optString("details"))
                                Text(event.optString("created_at"), style = MaterialTheme.typography.bodySmall)
                            }
                        }
                    }
                }
                else -> {
                    val overview = state.adminOverview
                    PageTitle("Administrator overview", "Manage accounts without exposing their coordinates")
                    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        OverviewCard("Users", overview?.optInt("total_users") ?: 0, Modifier.weight(1f))
                        OverviewCard("Active", overview?.optInt("active_users") ?: 0, Modifier.weight(1f))
                    }
                    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        OverviewCard("Admins", overview?.optInt("admins") ?: 0, Modifier.weight(1f))
                        OverviewCard("Devices online", overview?.optInt("online_devices") ?: 0, Modifier.weight(1f))
                    }
                    Text("Devices registered: ${overview?.optInt("total_devices") ?: 0}")
                    Text("Use Accounts to provision/manage users, Access for scoped owner-approved requests, and Audit to inspect administrator actions.")
                }
            }
        }
    }

    pendingCommand?.let { pending ->
        AlertDialog(
            onDismissRequest = {
                pendingCommand = null
                confirmation = ""
            },
            title = { Text("Confirm ${pending.command.replace('_', ' ').lowercase()}") },
            text = {
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text("Owner approval covers this device only. Type its name exactly: ${pending.deviceName}")
                    OutlinedTextField(
                        value = confirmation,
                        onValueChange = { confirmation = it },
                        label = { Text("Exact device name") },
                        singleLine = true,
                        modifier = Modifier.fillMaxWidth(),
                    )
                }
            },
            confirmButton = {
                TextButton(
                    enabled = confirmation == pending.deviceName && !state.isPageLoading,
                    onClick = {
                        onSendCommand(pending.requestId, pending.deviceId, pending.command, confirmation)
                        pendingCommand = null
                        confirmation = ""
                    },
                ) { Text("Send command") }
            },
            dismissButton = {
                TextButton(onClick = {
                    pendingCommand = null
                    confirmation = ""
                }) { Text("Cancel") }
            },
        )
    }
}

@Composable
private fun AdminAccountCard(
    account: JSONObject,
    currentUserId: String,
    canManageSuperAdmin: Boolean,
    isBusy: Boolean,
    onCreateInvitation: (String) -> Unit,
    onUpdate: (String, String?, String?) -> Unit,
    onResetAuthenticator: (String) -> Unit,
) {
    val id = account.optString("id")
    val role = account.optString("role")
    val status = account.optString("account_status")
    var roleMenu by remember(id) { mutableStateOf(false) }
    var confirmReset by remember(id) { mutableStateOf(false) }
    Card(Modifier.fillMaxWidth()) {
        Column(Modifier.fillMaxWidth().padding(14.dp), verticalArrangement = Arrangement.spacedBy(5.dp)) {
            Text(account.optString("name"), style = MaterialTheme.typography.titleMedium)
            Text("${account.optString("phone_number")} · $role · $status")
            Text("${account.optInt("device_count")} devices · ${account.optString("email")}", style = MaterialTheme.typography.bodySmall)
            if (id != currentUserId && (role != "SUPER_ADMIN" || canManageSuperAdmin)) {
                Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    androidx.compose.foundation.layout.Box {
                        TextButton(enabled = !isBusy, onClick = { roleMenu = true }) { Text("Change role") }
                        DropdownMenu(expanded = roleMenu, onDismissRequest = { roleMenu = false }) {
                            (if (canManageSuperAdmin) listOf("USER", "ADMIN", "SUPER_ADMIN") else listOf("USER", "ADMIN"))
                                .forEach { newRole ->
                                    DropdownMenuItem(
                                        text = { Text(newRole) },
                                        onClick = {
                                            roleMenu = false
                                            onUpdate(id, newRole, null)
                                        },
                                    )
                                }
                        }
                    }
                    TextButton(
                        enabled = !isBusy,
                        onClick = { onUpdate(id, null, if (status == "ACTIVE") "SUSPENDED" else "ACTIVE") },
                    ) { Text(if (status == "ACTIVE") "Suspend" else "Reactivate") }
                    if (id != currentUserId) {
                        TextButton(enabled = !isBusy, onClick = { onCreateInvitation(id) }) {
                            Text("Issue / reissue invite")
                        }
                    }
                    if (canManageSuperAdmin) {
                        TextButton(enabled = !isBusy, onClick = { confirmReset = true }) { Text("Reset authenticator") }
                    }
                }
            }
        }
    }
    if (confirmReset) {
        AlertDialog(
            onDismissRequest = { confirmReset = false },
            title = { Text("Reset authenticator?") },
            text = { Text("${account.optString("name")}'s current authenticator will stop working. Share the replacement key privately.") },
            confirmButton = {
                TextButton(onClick = {
                    confirmReset = false
                    onResetAuthenticator(id)
                }) { Text("Reset") }
            },
            dismissButton = { TextButton(onClick = { confirmReset = false }) { Text("Cancel") } },
        )
    }
}

@Composable
private fun AdminDeviceControl(
    accessRequestId: String,
    device: JSONObject,
    isBusy: Boolean,
    onCommand: (String, String, String) -> Unit,
) {
    val id = device.optString("id")
    val deviceType = device.optString("device_type").lowercase()
    val platform = device.optString("platform").lowercase()
    val isWindowsAgent = deviceType in setOf("laptop", "desktop") && platform.startsWith("windows")
    val supportsLostMode = deviceType == "android" || isWindowsAgent
    val online = device.optString("status") == "online"
    Text("Approved device controls · commands require exact-name confirmation")
    if (isWindowsAgent) {
        listOf("LOCK", "SLEEP", "RESTART", "SHUTDOWN").forEach { command ->
            OutlinedButton(
                enabled = online && !isBusy,
                onClick = { onCommand(accessRequestId, id, command) },
                modifier = Modifier.fillMaxWidth(),
            ) { Text(command.replace('_', ' ')) }
        }
    }
    if (supportsLostMode) {
        val command = if (device.optBoolean("is_lost_mode")) "DISABLE_LOST_MODE" else "ENABLE_LOST_MODE"
        OutlinedButton(
            enabled = online && !isBusy,
            onClick = { onCommand(accessRequestId, id, command) },
            modifier = Modifier.fillMaxWidth(),
        ) { Text(if (device.optBoolean("is_lost_mode")) "Disable Lost Mode" else "Enable Lost Mode") }
    }
    if (!online) Text("Device is offline. Commands are unavailable.")
    if (!supportsLostMode && !isWindowsAgent) Text("No supported remote commands for this device.")
}

@Composable
private fun OverviewCard(label: String, value: Int, modifier: Modifier = Modifier) {
    Card(modifier) {
        Column(Modifier.padding(14.dp)) {
            Text(value.toString(), style = MaterialTheme.typography.headlineSmall)
            Text(label, style = MaterialTheme.typography.bodySmall)
        }
    }
}

@Composable
private fun PageTitle(title: String, subtitle: String) {
    Column(verticalArrangement = Arrangement.spacedBy(3.dp)) {
        Text(title, style = MaterialTheme.typography.headlineSmall)
        Text(subtitle, style = MaterialTheme.typography.bodyMedium)
    }
}

private data class PendingAdminCommand(
    val requestId: String,
    val deviceId: String,
    val deviceName: String,
    val command: String,
)

private fun JSONObject.isExpired(): Boolean {
    val expiration = optString("expires_at")
    if (expiration.isBlank() || expiration == "null") return true
    val instant = runCatching { java.time.Instant.parse(expiration) }.getOrNull() ?: return true
    return instant <= java.time.Instant.now()
}

private fun List<JSONObject>.toCsv(): String {
    val columns = flatMap { row -> row.keys().asSequence().toList() }.distinct()
    fun escape(value: String): String {
        val safe = if (Regex("^[\\u0000-\\u0020\\uFEFF]*[=+\\-@]").containsMatchIn(value)) "'$value" else value
        return "\"${safe.replace("\"", "\"\"")}\""
    }
    return buildList {
        add(columns.joinToString(",") { escape(it) })
        this@toCsv.forEach { row ->
            add(columns.joinToString(",") { column ->
                escape(if (row.isNull(column)) "" else row.opt(column)?.toString().orEmpty())
            })
        }
    }.joinToString("\r\n")
}

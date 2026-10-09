# TrackGuard Android

Native Kotlin + Jetpack Compose Android project. Android Studio and an emulator
are not required; build with the Gradle Wrapper from VS Code or PowerShell and
install the debug APK on a physical Android device.

## Required tools

- JDK 17
- Android SDK command-line tools
- Android SDK Platform 35
- Android SDK Build-Tools 35.0.0 and Platform-Tools

Keep the SDK and Gradle cache on D: to reduce C: drive usage. For example, set
`ANDROID_HOME` and `ANDROID_SDK_ROOT` to `D:\AndroidSDK` and
`GRADLE_USER_HOME` to `D:\Gradle`. Install the SDK packages and accept licenses
with:

```powershell
sdkmanager "platform-tools" "platforms;android-35" "build-tools;35.0.0"
sdkmanager --licenses
```

If `sdkmanager` or `adb` is not on the current terminal's PATH, invoke
`D:\AndroidSDK\cmdline-tools\latest\bin\sdkmanager.bat` and
`D:\AndroidSDK\platform-tools\adb.exe` directly, or open a new terminal after
updating PATH.

## Google Maps key

The Android map uses the Google Maps SDK. Create a Google Maps Android API key,
enable Maps SDK for Android, and restrict the key to this app's package
(`com.trackguard.android`) and signing certificate. Store it in the ignored
`local.properties` file in this project:

```properties
MAPS_API_KEY=your-restricted-android-key
```

The APK still builds without a key and shows setup instructions instead of a
blank or misleading map. Do not commit `local.properties` or an unrestricted
maps key.

## Build and install

From this directory:

```powershell
$env:GRADLE_USER_HOME = "D:\Gradle"
.\gradlew.bat assembleDebug
```

The APK is written to
`app\build\outputs\apk\debug\app-debug.apk`. Connect a phone with USB debugging
enabled, authorize the computer on the phone, then run:

```powershell
adb devices
adb install -r app\build\outputs\apk\debug\app-debug.apk
```

## Android app features

- Sign in to the existing TrackGuard FastAPI server with the configured local
  owner PIN, then pair this phone.
- View registered devices, connection state, reported device/network details,
  and locations; open a reported position in the phone's map app.
- Start on a satellite live map with device-type markers, online/last-known
  styling, a selected-device summary, follow mode, and shortcuts to history and
  device controls. Configure the Android Maps key above to load map tiles.
- Review the last seven days of location history for any paired device.
- Track this phone in a visible foreground location service. The service uses
  configurable Normal, High Accuracy, and Battery Saver policies, deduplicates
  stationary points, stores points in Room, and retries batch uploads when the
  network returns.
- Enable Lost Mode for supported devices. A reconnecting Android tracker
  receives the current Lost Mode state and applies high-accuracy updates
  without replacing the user's saved tracking policy.
- Request status/location from online Android devices and use the Windows
  agent's Lock, Sleep, Restart, and Shut Down controls for online laptops and
  desktops. Destructive actions require confirmation.

The Android app cannot execute Windows power commands on an Android phone;
only status/location requests are offered for Android devices. Remote commands
are unavailable while a device is offline. A reachable backend is required for
sign-in, pairing, device data, Lost Mode, and uploads. For a phone and backend
on the same Wi-Fi network, use the computer's LAN IP rather than `localhost`.

Physical-device testing is still required to verify USB installation,
permission prompts, background-location behavior, OEM battery restrictions,
and end-to-end server connectivity on your phone.

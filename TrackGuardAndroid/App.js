import React, { useState, useEffect, useRef } from 'react';
import { StyleSheet, Text, View, TextInput, TouchableOpacity, Alert } from 'react-native';
import * as Location from 'expo-location';
import AsyncStorage from '@react-native-async-storage/async-storage';
import NetInfo from '@react-native-community/netinfo';

export default function App() {
  const [status, setStatus] = useState('Standby');
  const [isTracking, setIsTracking] = useState(false);
  const [deviceName, setDeviceName] = useState('My Android');
  const [serverUrl, setServerUrl] = useState('http://192.168.1.100:8000');
  
  // We'll just generate a random ID for the device if we don't have one
  const [deviceId] = useState(() => Math.random().toString(36).substring(7));
  const wsRef = useRef(null);
  const locationSubRef = useRef(null);

  const startTracking = async () => {
    let { status } = await Location.requestForegroundPermissionsAsync();
    if (status !== 'granted') {
      Alert.alert('Permission to access location was denied');
      return;
    }

    setStatus('Connecting to Server...');
    const wsUrl = serverUrl.replace('http://', 'ws://').replace('https://', 'wss://');
    const ws = new WebSocket(`${wsUrl}/ws/device/${deviceId}?token=dummy-android-token`);
    
    // Sync offline data
    const syncOfflineData = async () => {
      try {
        const stored = await AsyncStorage.getItem('@offline_locations');
        if (stored) {
          const locations = JSON.parse(stored);
          if (locations.length > 0 && ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({ type: 'BULK_LOCATION_UPDATE', data: locations }));
            await AsyncStorage.removeItem('@offline_locations');
            console.log(`Synced ${locations.length} offline locations`);
          }
        }
      } catch (e) {
        console.error('Failed to sync offline data', e);
      }
    };

    ws.onopen = async () => {
      setStatus('Connected & Tracking');
      setIsTracking(true);
      await syncOfflineData();
      
      locationSubRef.current = await Location.watchPositionAsync(
        {
          accuracy: Location.Accuracy.High,
          timeInterval: 5000,
          distanceInterval: 5,
        },
        async (location) => {
          const payload = {
            latitude: location.coords.latitude,
            longitude: location.coords.longitude,
            accuracy: location.coords.accuracy,
            altitude: location.coords.altitude,
            speed: location.coords.speed,
            heading: location.coords.heading,
            source: 'android_native',
            timestamp: new Date().toISOString(),
            movement_state: location.coords.speed > 8 ? 'DRIVING' : (location.coords.speed > 2 ? 'WALKING' : 'STATIONARY')
          };

          const netInfo = await NetInfo.fetch();
          
          if (netInfo.isConnected && ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({ type: 'LOCATION_UPDATE', data: payload }));
          } else {
            // Offline - Cache it
            try {
              setStatus('Offline - Caching Location');
              const stored = await AsyncStorage.getItem('@offline_locations');
              const locations = stored ? JSON.parse(stored) : [];
              locations.push(payload);
              await AsyncStorage.setItem('@offline_locations', JSON.stringify(locations));
            } catch (e) {
              console.error('Failed to cache location', e);
            }
          }
        }
      );
    };

    ws.onclose = () => {
      setStatus('Disconnected');
      setIsTracking(false);
      if (locationSubRef.current) {
        locationSubRef.current.remove();
        locationSubRef.current = null;
      }
    };

    ws.onerror = (e) => {
      console.log(e.message);
      setStatus('Connection Error');
    };

    wsRef.current = ws;
  };

  const stopTracking = () => {
    if (wsRef.current) {
      wsRef.current.close();
    }
    if (locationSubRef.current) {
      locationSubRef.current.remove();
      locationSubRef.current = null;
    }
    setIsTracking(false);
    setStatus('Standby');
  };

  return (
    <View style={styles.container}>
      <Text style={styles.title}>TrackGuard Android</Text>
      
      <View style={styles.statusBox}>
        <Text style={styles.statusLabel}>STATUS</Text>
        <Text style={[styles.statusText, isTracking && styles.trackingText]}>{status}</Text>
      </View>

      {!isTracking && (
        <>
          <View style={styles.inputContainer}>
            <Text style={styles.label}>Device Name</Text>
            <TextInput
              style={styles.input}
              value={deviceName}
              onChangeText={setDeviceName}
              placeholderTextColor="#666"
            />
          </View>
          
          <View style={styles.inputContainer}>
            <Text style={styles.label}>Server URL (with port)</Text>
            <TextInput
              style={styles.input}
              value={serverUrl}
              onChangeText={setServerUrl}
              autoCapitalize="none"
              placeholderTextColor="#666"
            />
          </View>
        </>
      )}

      <TouchableOpacity
        style={[styles.button, isTracking ? styles.buttonStop : styles.buttonStart]}
        onPress={isTracking ? stopTracking : startTracking}
      >
        <Text style={styles.buttonText}>{isTracking ? 'Stop Tracking' : 'Start Tracking'}</Text>
      </TouchableOpacity>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#0d0e15',
    alignItems: 'center',
    justifyContent: 'center',
    padding: 24,
  },
  title: {
    fontSize: 28,
    fontWeight: 'bold',
    color: '#fff',
    marginBottom: 40,
  },
  statusBox: {
    backgroundColor: 'rgba(0,0,0,0.4)',
    padding: 16,
    borderRadius: 12,
    width: '100%',
    marginBottom: 32,
    alignItems: 'center',
  },
  statusLabel: {
    color: '#666',
    fontSize: 12,
    fontWeight: 'bold',
    letterSpacing: 2,
    marginBottom: 8,
  },
  statusText: {
    color: '#ccc',
    fontSize: 18,
    fontWeight: '600',
  },
  trackingText: {
    color: '#4ade80',
  },
  inputContainer: {
    width: '100%',
    marginBottom: 20,
  },
  label: {
    color: '#888',
    fontSize: 12,
    marginBottom: 8,
    textTransform: 'uppercase',
  },
  input: {
    backgroundColor: 'rgba(0,0,0,0.3)',
    borderRadius: 8,
    padding: 16,
    color: '#fff',
    borderWidth: 1,
    borderColor: 'rgba(255,255,255,0.1)',
  },
  button: {
    width: '100%',
    padding: 18,
    borderRadius: 12,
    alignItems: 'center',
    marginTop: 20,
  },
  buttonStart: {
    backgroundColor: '#2563eb',
  },
  buttonStop: {
    backgroundColor: 'rgba(239, 68, 68, 0.2)',
    borderWidth: 1,
    borderColor: 'rgba(239, 68, 68, 0.5)',
  },
  buttonText: {
    color: '#fff',
    fontSize: 16,
    fontWeight: 'bold',
  }
});

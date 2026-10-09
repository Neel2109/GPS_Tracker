package com.trackguard.android.data.local

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query

@Dao
interface LocationDao {
    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun insertLocation(location: LocationEntity): Long

    @Query("SELECT * FROM locations WHERE deviceId = :deviceId ORDER BY timestamp DESC LIMIT 200")
    suspend fun getRecentLocations(deviceId: String): List<LocationEntity>

    @Query("SELECT * FROM locations WHERE synced = 0 ORDER BY timestamp ASC LIMIT :limit")
    suspend fun getUnsyncedLocations(limit: Int = 500): List<LocationEntity>

    @Query("UPDATE locations SET synced = 1 WHERE id IN (:ids)")
    suspend fun markSynced(ids: List<Long>)

    @Query("SELECT COUNT(*) FROM locations WHERE synced = 0")
    suspend fun getUnsyncedCount(): Int
}

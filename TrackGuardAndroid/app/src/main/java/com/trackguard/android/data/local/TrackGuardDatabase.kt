package com.trackguard.android.data.local

import androidx.room.Database
import androidx.room.Room
import androidx.room.RoomDatabase
import android.content.Context

@Database(entities = [LocationEntity::class], version = 1, exportSchema = false)
abstract class TrackGuardDatabase : RoomDatabase() {
    abstract fun locationDao(): LocationDao

    companion object {
        @Volatile
        private var INSTANCE: TrackGuardDatabase? = null

        fun getInstance(context: Context): TrackGuardDatabase {
            return INSTANCE ?: synchronized(this) {
                val instance = Room.databaseBuilder(
                    context.applicationContext,
                    TrackGuardDatabase::class.java,
                    "trackguard.db"
                ).build()
                INSTANCE = instance
                instance
            }
        }
    }
}

package com.trackguard.android.data.remote

import android.content.Context
import androidx.work.Constraints
import androidx.work.CoroutineWorker
import androidx.work.ExistingWorkPolicy
import androidx.work.NetworkType
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.WorkerParameters
import com.trackguard.android.data.local.TrackGuardDatabase
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

class LocationSyncWorker(
    appContext: Context,
    workerParams: WorkerParameters,
) : CoroutineWorker(appContext, workerParams) {
    override suspend fun doWork(): Result = withContext(Dispatchers.IO) {
        val credentials = DeviceCredentials(applicationContext)
        if (credentials.deviceId.isBlank() || credentials.deviceToken.isBlank()) {
            return@withContext Result.failure()
        }

        val dao = TrackGuardDatabase.getInstance(applicationContext).locationDao()
        val api = TrackGuardApi(applicationContext)
        try {
            while (true) {
                val pending = dao.getUnsyncedLocations()
                if (pending.isEmpty()) break
                api.uploadLocations(pending)
                dao.markSynced(pending.map { it.id })
            }
            Result.success()
        } catch (error: ApiException) {
            if (error.statusCode in 400..499 && error.statusCode != 408 && error.statusCode != 429) {
                Result.failure()
            } else {
                Result.retry()
            }
        } catch (_: Exception) {
            Result.retry()
        }
    }

    companion object {
        fun enqueue(context: Context) {
            val constraints = Constraints.Builder()
                .setRequiredNetworkType(NetworkType.CONNECTED)
                .build()
            val request = OneTimeWorkRequestBuilder<LocationSyncWorker>()
                .setConstraints(constraints)
                .build()
            WorkManager.getInstance(context).enqueueUniqueWork(
                "trackguard-location-sync",
                ExistingWorkPolicy.APPEND_OR_REPLACE,
                request,
            )
        }
    }
}

import java.util.Properties

plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.kotlin.android)
    alias(libs.plugins.ksp)
}

val localProperties = Properties()
val localPropertiesFile = rootProject.file("local.properties")
if (localPropertiesFile.isFile) {
    localPropertiesFile.inputStream().use { localProperties.load(it) }
}
val mapsApiKey = localProperties.getProperty("MAPS_API_KEY", "")

android {
    namespace = "com.trackguard.android"
    compileSdk = 35

    defaultConfig {
        applicationId = "com.trackguard.android"
        minSdk = 26
        targetSdk = 35
        versionCode = 1
        versionName = "1.0"
        manifestPlaceholders["MAPS_API_KEY"] = mapsApiKey
        buildConfigField("boolean", "HAS_MAPS_API_KEY", mapsApiKey.isNotBlank().toString())

        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro"
            )
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    kotlinOptions {
        jvmTarget = "17"
    }

    buildFeatures {
        compose = true
        buildConfig = true
    }

    composeOptions {
        kotlinCompilerExtensionVersion = "1.5.14"
    }

    packaging {
        resources {
            excludes += "/META-INF/{AL2.0,LGPL2.1}"
        }
    }
}

val preserveAndExcludeWindowsMetadata = tasks.register("preserveAndExcludeWindowsMetadata") {
    doLast {
        val androidSourceRoot = file("src/main")
        val preservedMetadataRoot = layout.buildDirectory.dir("preserved-windows-metadata").get().asFile
        if (androidSourceRoot.isDirectory) {
            fileTree(androidSourceRoot).matching { include("**/desktop.ini") }.files.forEach { metadata ->
                val relativePath = androidSourceRoot.toPath().relativize(metadata.toPath()).toString()
                val preservedFile = preservedMetadataRoot.resolve(relativePath)
                preservedFile.parentFile.mkdirs()
                metadata.copyTo(preservedFile, overwrite = true)
                metadata.setWritable(true)
                if (!metadata.delete()) {
                    throw GradleException("Could not move Windows metadata out of Android sources: $metadata")
                }
            }
        }
    }
}

tasks.named("preBuild").configure {
    dependsOn(preserveAndExcludeWindowsMetadata)
}

tasks.withType<org.gradle.api.tasks.Copy>().configureEach {
    exclude("**/desktop.ini")
}

dependencies {
    implementation(platform(libs.androidx.compose.bom))
    implementation(libs.androidx.core.ktx)
    implementation(libs.androidx.lifecycle.runtime.ktx)
    implementation(libs.androidx.activity.compose)
    implementation(libs.androidx.navigation.compose)
    implementation(libs.androidx.lifecycle.viewmodel.compose)
    implementation(libs.androidx.compose.ui)
    implementation(libs.androidx.compose.ui.graphics)
    implementation(libs.androidx.compose.ui.tooling.preview)
    implementation(libs.androidx.compose.material3)
    implementation(libs.androidx.material.icons.extended)
    implementation(libs.androidx.room.runtime)
    implementation(libs.androidx.room.ktx)
    ksp(libs.androidx.room.compiler)
    implementation(libs.androidx.datastore.preferences)
    implementation(libs.androidx.work.runtime.ktx)
    implementation(libs.androidx.activity.ktx)
    implementation(libs.google.play.services.location)
    implementation(libs.google.maps.compose)
    implementation(libs.okhttp)
    implementation(libs.retrofit)
    implementation(libs.retrofit.kotlinx.serialization)
    implementation(libs.kotlinx.serialization.json)
    implementation(libs.kotlinx.coroutines.android)
    implementation(libs.kotlinx.coroutines.play.services)

    debugImplementation(libs.androidx.compose.ui.tooling)
    debugImplementation(libs.androidx.compose.ui.test.manifest)
}

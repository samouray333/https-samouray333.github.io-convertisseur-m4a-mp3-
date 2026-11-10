import java.util.Properties

plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

// Signature : android/keystore/keystore.properties (storeFile, storePassword, keyAlias, keyPassword).
// Toutes les versions doivent être signées avec la même clé pour s'installer par-dessus la précédente.
val ksProps = Properties()
val ksFile = rootProject.file("keystore/keystore.properties")
if (ksFile.exists()) ksFile.inputStream().use { ksProps.load(it) }

android {
    namespace = "com.qmtech.telechargys"
    compileSdk = 35

    defaultConfig {
        applicationId = "com.qmtech.telechargys"
        minSdk = 24
        targetSdk = 35
        versionCode = 1
        versionName = "1.0.0"
        ndk { abiFilters += listOf("arm64-v8a", "armeabi-v7a") + if (project.hasProperty("x86")) listOf("x86_64") else emptyList() } // -Px86 : pour tester sur émulateur
    }
    signingConfigs {
        if (ksFile.exists()) create("release") {
            storeFile = rootProject.file("keystore/" + ksProps.getProperty("storeFile"))
            storePassword = ksProps.getProperty("storePassword")
            keyAlias = ksProps.getProperty("keyAlias")
            keyPassword = ksProps.getProperty("keyPassword")
        }
    }
    buildTypes {
        release {
            isMinifyEnabled = true
            isShrinkResources = true
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro")
            if (ksFile.exists()) signingConfig = signingConfigs.getByName("release")
        }
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions { jvmTarget = "17" }
    packaging { jniLibs { useLegacyPackaging = false } }
}

dependencies {
    implementation(files("libs/engine.aar"))
    implementation("androidx.core:core-ktx:1.15.0")
}

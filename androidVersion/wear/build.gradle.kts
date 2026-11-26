import java.util.Properties

// SOUND · Galaxy Watch (Wear OS): telefondaki SOUND'un kumandası. Telefonla aynı uygulama kimliği ve aynı imza olmalı,
// yoksa Wearable Data Layer iki uygulamayı eşleştirmez (debug ↔ debug, release ↔ release).
plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

val signingProps = rootDir.resolve("keystore/keystore.properties").takeIf { it.exists() }?.let { file ->
    Properties().apply { file.inputStream().use { load(it) } }
}

android {
    namespace = "com.sound.wear"
    compileSdk = 36

    defaultConfig {
        applicationId = "com.sound.app"  // telefondakiyle aynı
        minSdk = 30
        targetSdk = 36
        versionCode = 1
        versionName = "1.0"
    }
    signingConfigs {
        signingProps?.let { p ->
            create("release") {
                storeFile = rootDir.resolve("keystore/" + p.getProperty("storeFile"))
                storePassword = p.getProperty("storePassword")
                keyAlias = p.getProperty("keyAlias")
                keyPassword = p.getProperty("keyPassword")
            }
        }
    }
    buildTypes {
        getByName("release") {
            isMinifyEnabled = false
            signingConfigs.findByName("release")?.let { signingConfig = it }
        }
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
}

kotlin { compilerOptions { jvmTarget.set(org.jetbrains.kotlin.gradle.dsl.JvmTarget.JVM_17) } }

dependencies {
    implementation("androidx.core:core-ktx:1.17.0")
    implementation("com.google.android.gms:play-services-wearable:19.0.0")
    implementation("androidx.wear.tiles:tiles:1.4.1")
    implementation("androidx.wear.protolayout:protolayout:1.2.1")
    implementation("androidx.wear.protolayout:protolayout-expression:1.2.1")
    implementation("com.google.guava:guava:33.3.1-android")
}

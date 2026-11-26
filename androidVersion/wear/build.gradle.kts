import java.util.Properties

// SOUND · Galaxy Watch (Wear OS): telefon yakındaysa telefondaki SOUND'un kumandası, değilse kendi başına çalar (Wi-Fi'dan
// ya da saate indirilen şarkılardan). Telefonla aynı uygulama kimliği ve aynı imza olmalı, yoksa Wearable Data Layer iki
// uygulamayı eşleştirmez (debug ↔ debug, release ↔ release).
plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("com.chaquo.python")
}

// Telefonsuz çalma için masaüstü SOUND'un ortak modülleri (şarkı bulma, indirme, akıllı sıra) ve telefonun yt-dlp güncelleyicisi
val soundDir = rootDir.resolve((findProperty("soundDir") as String?) ?: "../../SOUND")
val sharedDir = layout.buildDirectory.dir("generated/sound")
val syncSound by tasks.registering(Sync::class) {
    into(sharedDir)
    from(soundDir) { include("library.py", "searcher.py", "downloader.py", "recommender.py", "cloud.py", "listen.py", "devices.py", "cloud_config.json") }
    from(rootDir.resolve("app/src/main/python")) { include("updater.py") }
    doFirst { check(soundDir.resolve("downloader.py").exists()) { "SOUND klasörü bulunamadı: $soundDir" } }
}
tasks.named("preBuild") { dependsOn(syncSound) }
tasks.matching { it.name.startsWith("merge") && it.name.endsWith("PythonSources") }.configureEach { dependsOn(syncSound) }

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
        versionCode = (findProperty("wearCode") as String?)?.toInt() ?: 2  // -PwearCode: güncelleme testi için
        versionName = (findProperty("wearName") as String?) ?: "1.1"
        // Galaxy Watch4-7 32 bit Android kullanıyor; arm64 yeni saatler için. Emülatör (x86_64) yalnızca debug derlemede.
        ndk { abiFilters += listOf("armeabi-v7a", "arm64-v8a") }
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
        getByName("debug") { ndk { abiFilters += "x86_64" } }
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

chaquopy {
    defaultConfig {
        version = "3.11"  // telefonla aynı: armeabi-v7a'yı destekleyen en yeni sürüm
        val localPython = System.getenv("LOCALAPPDATA")?.let { file("$it/SOUNDtools/py311/tools/python.exe") }?.takeIf { it.exists() }?.path
        ((findProperty("buildPython") as String?) ?: localPython)?.let { buildPython(it) }
        pip {
            install("yt-dlp")
            install("mutagen")
            install("ytmusicapi")
            install("requests")
            install("certifi")
            install("websocket-client")  // hesabın diğer cihazlarıyla anlık kanal (devices.py)
        }
    }
    sourceSets {
        getByName("main") {
            srcDir("src/main/python")
            srcDir(sharedDir)
        }
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
    implementation("androidx.media:media:1.7.1")  // saatte çalarken medya oturumu: kulaklık düğmeleri, sistem medya denetimleri
}

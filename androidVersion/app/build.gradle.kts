import java.util.Properties

plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("com.chaquo.python")
}

// Masaüstü SOUND tek kaynak: arka uç modülleri ve web arayüzü her derlemede oradan alınır, kopyası tutulmaz.
val soundDir = rootDir.resolve((findProperty("soundDir") as String?) ?: "../../SOUND")
val sharedDir = layout.buildDirectory.dir("generated/sound")
val sharedModules = listOf("library", "searcher", "downloader", "recommender", "lyricsfinder", "importer", "mediaserver", "webapp")

val syncSound by tasks.registering(Sync::class) {
    into(sharedDir)
    from(soundDir) { include(sharedModules.map { "$it.py" }) }
    from(soundDir.resolve("web")) {
        into("webui")
        filteringCharset = "UTF-8"
        filesMatching("index.html") {
            filter { line: String ->
                line.replace("<title>SOUND</title>", "<title>SOUND</title>\n<meta name=\"viewport\" content=\"width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no\">")
                    .replace("<link rel=\"stylesheet\" href=\"style.css\">", "<link rel=\"stylesheet\" href=\"style.css\">\n<link rel=\"stylesheet\" href=\"mobile.css\">")
                    .replace("<script src=\"app.js\"></script>", "<script src=\"android-bridge.js\"></script>\n<script src=\"app.js\"></script>\n<script src=\"mobile.js\"></script>")
            }
        }
        filesMatching("app.js") {
            filter { line: String ->
                line.replace("Bir şarkı ara ve çift tıkla", "Bir şarkı ara ve dokun")
                    .replace("Kapağa tıkla ya da sürükleyip kitaplığına bırak", "Açmak için kapağa dokun")
                    .replace("Arama sonuçlarından bir şarkıyı sürükleyip soldaki albüme bırak ya da ⋯ › Albüme ekle'yi kullan.", "Bir şarkının ⋯ menüsünden Albüme ekle'yi kullan.")
                    .replace("♡ simgesine tıkla", "♡ simgesine dokun")
                    .replace("indirme simgesine tıkla", "⋯ menüsünden indir")
                    .replace("<b>Spotify bağlantı ya da dosya</b>", "<b>Spotify liste bağlantısı</b>")
                    .replace("Premium gerekmez: liste bağlantıları ya da hesap verisi dosyanla aktarılır.", "Premium gerekmez: liste bağlantılarını yapıştırarak aktarılır.")
                    .replace("Spotify giriş penceresi açıldı; izin verince aktarma kendiliğinden başlar", "Spotify tarayıcıda açıldı; izin verdikten sonra SOUND'a geri dön")
                    .replace("GitHub'da yeni sürüm çıkınca SOUND kendini arka planda günceller; yeniden başlatınca etkin olur.", "Yeni sürüm Wi-Fi'da kendiliğinden iner, yüklemeden önce onayını ister. Mobil veride yalnızca Şimdi denetle düğmesiyle iner (yaklaşık 60 MB). Kitaplığın silinmez.")
                    .replace("data-x=\"restart\">Yeniden başlat<", "data-x=\"restart\">Yükle<")
                    .replace("\"Denetleniyor…\"", "\"Denetleniyor ve indiriliyor…\"")
            }
        }
    }
    from("src/main/web") { into("webui") }
    doFirst { check(soundDir.resolve("webapp.py").exists()) { "SOUND klasörü bulunamadı: $soundDir (-PsoundDir=... ile verilebilir)" } }
    doLast { sharedDir.get().file("webui/__init__.py").asFile.writeText("") }
}
tasks.named("preBuild") { dependsOn(syncSound) }
tasks.matching { it.name.startsWith("merge") && it.name.endsWith("PythonSources") }.configureEach { dependsOn(syncSound) }

// Yayın imzası: anahtar keystore/ klasöründe, depoya girmez. Yoksa release derlemesi imzasız kalır.
val signingProps = rootDir.resolve("keystore/keystore.properties").takeIf { it.exists() }?.let { file ->
    Properties().apply { file.inputStream().use { load(it) } }
}

android {
    namespace = "com.sound.app"
    compileSdk = 36

    defaultConfig {
        applicationId = "com.sound.app"
        minSdk = 26
        targetSdk = 36
        versionCode = 4
        versionName = "0.1.3"
        // armeabi-v7a: 64 bit işlemcili olsa da 32 bit Android kullanan telefonlar (çoğu uygun fiyatlı Samsung) için
        ndk { abiFilters += listOf("arm64-v8a", "armeabi-v7a", "x86_64") }
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
        getByName("release") { signingConfigs.findByName("release")?.let { signingConfig = it } }
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
}

chaquopy {
    defaultConfig {
        version = "3.11"  // armeabi-v7a'yı destekleyen en yeni sürüm
        // Derleyen makinede aynı sürüm gerekir (paketleri seçmek ve .pyc üretmek için)
        val localPython = System.getenv("LOCALAPPDATA")?.let { file("$it/SOUNDtools/py311/tools/python.exe") }?.takeIf { it.exists() }?.path
        ((findProperty("buildPython") as String?) ?: localPython)?.let { buildPython(it) }
        pip {
            install("yt-dlp")
            install("yt-dlp-ejs")
            install("mutagen")
            install("ytmusicapi")
            install("requests")
            install("certifi")
        }
        extractPackages("webui")
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
    implementation("androidx.activity:activity-ktx:1.11.0")
    implementation("androidx.media:media:1.7.1")
}

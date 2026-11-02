plugins {
    id("com.android.application") version "8.13.2" apply false
    id("org.jetbrains.kotlin.android") version "2.2.20" apply false
    id("com.chaquo.python") version "17.2.0" apply false
}

// Derleme çıktıları OneDrive'ın dışında dursun: binlerce ara dosya eşitlenmesin, Windows yol sınırına takılmasın.
System.getenv("LOCALAPPDATA")?.let { local ->
    allprojects { layout.buildDirectory.set(file("$local/SOUNDbuild/${project.name}")) }
}

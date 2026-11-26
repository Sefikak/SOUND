pluginManagement {
    repositories { google(); mavenCentral(); gradlePluginPortal() }
}
dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories { google(); mavenCentral() }
}
rootProject.name = "SOUND"
include(":app", ":wear")  // wear: Galaxy Watch uygulaması (telefondaki SOUND'u kumanda eder)

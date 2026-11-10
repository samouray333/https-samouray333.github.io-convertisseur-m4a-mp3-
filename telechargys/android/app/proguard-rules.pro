# Moteur Go (gomobile) : classes appelées par JNI, à conserver telles quelles.
-keep class go.** { *; }
-keep class mobile.** { *; }
# Méthodes appelées depuis l'interface web.
-keepclassmembers class * { @android.webkit.JavascriptInterface <methods>; }

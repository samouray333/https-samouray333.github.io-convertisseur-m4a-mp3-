#!/bin/bash
# Lance les tests d'extraction sur PC (nécessite d'avoir lancé ../build.sh avant).
set -e
cd "$(dirname "$0")"
B=../build
ANDROID_JAR=${ANDROID_JAR:-$HOME/deps/android-all.jar}
mkdir -p out
CP="$B/classes:../libs/jsoup-1.13.1.jar:$B/pdfbox/classes.jar:$ANDROID_JAR"
javac -nowarn -encoding UTF-8 -d out -cp "$CP" $(find stubs -name "*.java") src/*.java
java -Dstdout.encoding=UTF-8 $JAVA_OPTS -cp "out:$B/pdfbox/assets:$CP" TestExtract "$@"

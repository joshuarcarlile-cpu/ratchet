#!/usr/bin/env bash
# An Android project skeleton, as in chan-archiver.
set -e
git init -q
mkdir -p .claude
mkdir -p app/src/main/java/com/example/app/ui/screens
cat > .claude/PROJECT_PROFILE.md <<'EOF'
# Project Profile

## Commands
- Test: `.\gradlew.bat testDebugUnitTest assembleDebug`
- Lint/build: `.\gradlew.bat assembleDebug`

## Conventions
- Tests live in: `app/src/test/java/com/example/app/` (JUnit 4)
EOF
printf 'rootProject.name = "example"\ninclude(":app")\n' > settings.gradle.kts
printf '@echo off\r\nrem stand-in for the Gradle wrapper\r\n' > gradlew.bat
cat > app/src/main/java/com/example/app/ui/Routes.kt <<'EOF'
package com.example.app.ui

const val SETTINGS_ROUTE = "settings"
const val WATCHERS_ROUTE = "watchers"
EOF
cat > app/src/main/java/com/example/app/ui/screens/WatchersScreen.kt <<'EOF'
package com.example.app.ui.screens

import androidx.compose.material3.Text
import androidx.compose.runtime.Composable

@Composable
fun WatchersScreen() {
    Text("Watchers")
}
EOF
printf '# Changelog\n\n## Unreleased\n' > CHANGELOG.md
git add -A
git -c user.name=fixture -c user.email=fixture@example.com commit -qm init

# Integration hand-off — Fitness-Record

## Scope guard
- Native Android/Kotlin + Jetpack Compose only; fully offline, no network, accounts, API, web frontend, or cloud/Azure resources.
- Do not add a backend, online client, or remote data source. Integrate and verify the on-device Room database and Android UI only.
- Local persistence is implemented in `app/src/main/java/com/fitnessrecord/app/data/`; schema version 1 is the initial schema. There are no migrations to add for a new installation.
- No seed data.

## Project / commands
- Root: `Fitness-Record/`
- Debug APK: `gradle :app:assembleDebug` (requires JDK 17, Android SDK platform 35, and Gradle 8.9+).
- Unit tests: `gradle :app:testDebugUnitTest`
- Room persistence instrumentation test: `gradle :app:connectedDebugAndroidTest` (requires an emulator/device).
- Package: `com.fitnessrecord.app`; launcher: `.MainActivity`.

## Local data and backup
- Room database: `fitness-record.db`, `FitnessDatabase`, schema version 1.
- Entities/relations and DAOs: `app/src/main/java/com/fitnessrecord/app/data/FitnessData.kt`.
- Repository: `FitnessRepository.kt`; related writes and imports use transactions.
- Backup JSON SAF import/export: `BackupCodec.kt` and `ui/FitnessApp.kt`; validates records/references before replacement or merge.

## API / services
- API routes: none.
- Services: one Android application; Essential: local Room persistence, workout logging/history/templates, progress, body measurements, rest timer, SAF backup import/export. Enhancement: none.
- There is no web frontend/API seam; no frontend dev server or web preview applies.

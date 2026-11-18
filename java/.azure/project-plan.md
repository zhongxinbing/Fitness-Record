# Fitness-Record Project Plan

## Goal

Build a native Android application for recording daily fitness training. Deliver an Android APK that can also run on HarmonyOS devices with Android-app compatibility enabled. HarmonyOS NEXT native support is out of scope.

## Approved implementation

- Language: Kotlin
- UI: Jetpack Compose with Material 3
- Persistence: Room database stored locally on the device
- Architecture: single Android application module with a repository and ViewModels
- Network and accounts: none; all features work offline
- Backup: user-initiated JSON export and import through Android's Storage Access Framework; validate imported data before replacing or merging local data

## Features

1. Dashboard with today's workout and quick actions.
2. Workout logging by date, including exercises and sets with repetitions, weight, and optional notes.
3. Reusable workout templates that can start a new workout.
4. Workout history with a monthly calendar, marked workout dates, date navigation, and summaries.
5. Progress summaries for training volume and exercise history.
6. Body-weight and body-measurement entries with history and trends.
7. An in-app rest timer with selectable duration, pause, and reset controls.
8. Local data backup, export, and import.

## Data model

- Workout: date, title, notes, timestamps.
- Exercise entry: workout reference, exercise name, ordering, notes.
- Set entry: exercise reference, set ordering, repetitions, weight, completion state.
- Workout template: name, notes, ordered exercises, and prescribed sets.
- Body measurement: date, body weight, optional named measurements, and notes.

Use stable IDs and database transactions for related records. Keep all records on-device unless the user explicitly exports a backup.

## UX and accessibility

- Phone-first layouts, clear empty states, and Chinese-language interface.
- Provide edit and delete flows with confirmation for destructive actions.
- Use form validation for dates, weights, repetitions, and imported backups.
- Support light and dark system themes and accessible labels for controls.

## Verification

- Build the Android debug variant.
- Add focused tests for local data persistence and backup round-trip/validation.
- Verify core screens render and the app can be navigated without network access.

## Out of scope

- Cloud sync, accounts, social features, ads, subscription billing, and HarmonyOS NEXT native packaging.

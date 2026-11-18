package com.fitnessrecord.app.data

import org.junit.Assert.assertEquals
import org.junit.Assert.assertThrows
import org.junit.Test

class BackupCodecTest {
    @Test
    fun backupRoundTripKeepsWorkoutAndSetData() {
        val workout = Workout("workout-1", "2026-11-18", "力量训练", "训练备注", 1L, 2L)
        val exercise = ExerciseEntry("exercise-1", workout.id, "深蹲", 0)
        val set = SetEntry("set-1", exercise.id, 0, 8, 60.0, completed = true)

        val decoded = BackupCodec.decodeAndValidate(
            BackupCodec.encode(BackupPayload(workouts = listOf(workout), exercises = listOf(exercise), sets = listOf(set)))
        )

        assertEquals(workout, decoded.workouts.single())
        assertEquals(exercise, decoded.exercises.single())
        assertEquals(set, decoded.sets.single())
    }

    @Test
    fun rejectsSetWithMissingExerciseReference() {
        val invalid = BackupPayload(
            workouts = listOf(Workout("w", "2026-11-18", "训练", createdAt = 1L, updatedAt = 1L)),
            sets = listOf(SetEntry("s", "missing-exercise", 0, 8, 40.0))
        )

        assertThrows(IllegalArgumentException::class.java) {
            BackupCodec.decodeAndValidate(BackupCodec.encode(invalid))
        }
    }

    @Test
    fun rejectsInvalidDateAndOutOfRangeWeight() {
        val invalid = BackupPayload(
            workouts = listOf(Workout("w", "2026/11/18", "训练", createdAt = 1L, updatedAt = 1L))
        )
        assertThrows(IllegalArgumentException::class.java) {
            BackupCodec.decodeAndValidate(BackupCodec.encode(invalid))
        }
    }
}

package com.fitnessrecord.app.data

import androidx.room.Room
import androidx.test.core.app.ApplicationProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import android.content.Context
import kotlinx.coroutines.runBlocking
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class FitnessDaoTest {
    private lateinit var database: FitnessDatabase
    private lateinit var dao: FitnessDao

    @Before
    fun createDatabase() {
        database = Room.inMemoryDatabaseBuilder(
            ApplicationProvider.getApplicationContext<Context>(),
            FitnessDatabase::class.java
        ).allowMainThreadQueries().build()
        dao = database.dao()
    }

    @After
    fun closeDatabase() = database.close()

    @Test
    fun workoutAndSetsPersistAsRelatedRecords() = runBlocking {
        val workout = Workout("w-1", "2026-11-18", "力量训练", createdAt = 1L, updatedAt = 1L)
        val exercise = ExerciseEntry("e-1", workout.id, "深蹲", 0)
        val set = SetEntry("s-1", exercise.id, 0, 8, 60.0, completed = true)
        dao.putWorkout(workout)
        dao.putExercise(exercise)
        dao.putSet(set)

        val restored = dao.workoutDetails(workout.id)
        assertEquals(workout, restored?.workout)
        assertEquals(exercise, restored?.exercises?.single()?.exercise)
        assertEquals(set, restored?.exercises?.single()?.sets?.single())
    }

    @Test
    fun updatingWorkoutMetadataPreservesRelatedExerciseAndSets() = runBlocking {
        val workout = Workout("w-2", "2026-11-18", "旧名称", createdAt = 1L, updatedAt = 1L)
        val exercise = ExerciseEntry("e-2", workout.id, "硬拉", 0)
        val set = SetEntry("s-2", exercise.id, 0, 5, 80.0)
        dao.putWorkout(workout)
        dao.putExercise(exercise)
        dao.putSet(set)

        dao.updateWorkout(workout.copy(title = "新名称"))

        assertEquals(set, dao.workoutDetails(workout.id)?.exercises?.single()?.sets?.single())
    }
}

package com.fitnessrecord.app.data

import androidx.room.withTransaction
import kotlinx.coroutines.flow.Flow
import java.time.Instant
import java.util.UUID

class FitnessRepository(private val database: FitnessDatabase) {
    private val dao = database.dao()

    val workouts: Flow<List<Workout>> = dao.observeWorkouts()
    val measurements: Flow<List<BodyMeasurement>> = dao.observeMeasurements()
    val templates: Flow<List<WorkoutTemplate>> = dao.observeTemplates()

    suspend fun detail(id: String) = dao.workoutDetails(id)
    suspend fun forDate(date: String) = dao.workoutForDate(date)

    suspend fun createWorkout(date: String, title: String): String {
        return database.withTransaction {
            val now = System.currentTimeMillis()
            val existing = dao.workoutForDate(date)
            if (existing != null) return@withTransaction existing.id
            val item = Workout(UUID.randomUUID().toString(), date, title.ifBlank { "今日训练" }, createdAt = now, updatedAt = now)
            dao.putWorkout(item)
            item.id
        }
    }

    suspend fun updateWorkout(id: String, title: String, notes: String) {
        val old = dao.workout(id) ?: return
        dao.updateWorkout(old.copy(title = title.trim().ifBlank { "训练记录" }, notes = notes, updatedAt = System.currentTimeMillis()))
    }

    suspend fun addExercise(workoutId: String, name: String) {
        database.withTransaction {
            val detail = dao.workoutDetails(workoutId) ?: return@withTransaction
            val exId = UUID.randomUUID().toString()
            dao.putExercise(ExerciseEntry(exId, workoutId, name.trim(), detail.exercises.size))
            dao.putSet(SetEntry(UUID.randomUUID().toString(), exId, 0, 10, 0.0))
        }
    }

    suspend fun addSet(exerciseId: String) {
        val details = dao.allExercises().firstOrNull { it.id == exerciseId } ?: return
        val sets = dao.workoutDetails(details.workoutId)?.exercises?.firstOrNull { it.exercise.id == exerciseId }?.sets.orEmpty()
        dao.putSet(SetEntry(UUID.randomUUID().toString(), exerciseId, sets.size, 10, 0.0))
    }

    suspend fun updateSet(item: SetEntry) = dao.putSet(item)
    suspend fun removeExercise(id: String) = dao.deleteExercise(id)
    suspend fun removeWorkout(id: String) = dao.deleteWorkout(id)
    suspend fun removeTemplate(id: String) = dao.deleteTemplate(id)

    suspend fun saveTemplate(workoutId: String, name: String) {
        database.withTransaction {
            val detail = dao.workoutDetails(workoutId) ?: return@withTransaction
            val templateId = UUID.randomUUID().toString()
            dao.putTemplate(WorkoutTemplate(templateId, name.trim(), detail.workout.notes, System.currentTimeMillis()))
            detail.exercises.forEachIndexed { index, exercise ->
                val templateExerciseId = UUID.randomUUID().toString()
                dao.putTemplateExercise(TemplateExercise(templateExerciseId, templateId, exercise.exercise.name, index, exercise.exercise.notes))
                exercise.sets.forEachIndexed { setIndex, set ->
                    dao.putTemplateSet(TemplateSet(UUID.randomUUID().toString(), templateExerciseId, setIndex, set.repetitions, set.weightKg))
                }
            }
        }
    }

    suspend fun startTemplate(template: WorkoutTemplate, date: String): String {
        return database.withTransaction {
            val workoutId = dao.workoutForDate(date)?.id ?: run {
                val now = System.currentTimeMillis()
                val workout = Workout(UUID.randomUUID().toString(), date, template.name, createdAt = now, updatedAt = now)
                dao.putWorkout(workout)
                workout.id
            }
            val current = dao.workoutDetails(workoutId) ?: return@withTransaction workoutId
            if (current.exercises.isNotEmpty()) return@withTransaction workoutId
            dao.updateTemplateNote(workoutId, template.notes)
            dao.templateExercises(template.id).forEach { exercise ->
                val exerciseId = UUID.randomUUID().toString()
                dao.putExercise(ExerciseEntry(exerciseId, workoutId, exercise.name, exercise.orderIndex, exercise.notes))
                dao.templateSets(exercise.id).forEach { set ->
                    dao.putSet(SetEntry(UUID.randomUUID().toString(), exerciseId, set.orderIndex, set.repetitions, set.weightKg))
                }
            }
            workoutId
        }
    }

    suspend fun addMeasurement(date: String, weightKg: Double?, namedMeasurementsJson: String, notes: String) {
        dao.putMeasurement(BodyMeasurement(UUID.randomUUID().toString(), date, weightKg, namedMeasurementsJson, notes, System.currentTimeMillis()))
    }

    suspend fun exportBackup(): String {
        return database.withTransaction {
            val payload = BackupPayload(
                exportedAt = Instant.now().toString(),
                workouts = dao.allWorkouts(),
                exercises = dao.allExercises(),
                sets = dao.allSets(),
                templates = dao.allTemplates(),
                templateExercises = dao.allTemplateExercises(),
                templateSets = dao.allTemplateSets(),
                measurements = dao.allMeasurements()
            )
            BackupCodec.encode(payload)
        }
    }

    suspend fun importBackup(json: String, merge: Boolean) {
        val payload = BackupCodec.decodeAndValidate(json)
        database.withTransaction {
            if (!merge) {
                dao.clearWorkouts()
                dao.clearTemplates()
                dao.clearMeasurements()
            }
            dao.mergeWorkouts(payload.workouts)
            dao.mergeExercises(payload.exercises)
            dao.mergeSets(payload.sets)
            dao.mergeTemplates(payload.templates)
            dao.mergeTemplateExercises(payload.templateExercises)
            dao.mergeTemplateSets(payload.templateSets)
            dao.mergeMeasurements(payload.measurements)
        }
    }
}

private suspend fun FitnessDao.updateTemplateNote(workoutId: String, note: String) {
    val item = workout(workoutId) ?: return
    updateWorkout(item.copy(notes = note, updatedAt = System.currentTimeMillis()))
}

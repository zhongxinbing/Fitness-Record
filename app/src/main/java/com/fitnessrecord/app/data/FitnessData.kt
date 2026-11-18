package com.fitnessrecord.app.data

import androidx.room.Dao
import androidx.room.Database
import androidx.room.Entity
import androidx.room.ForeignKey
import androidx.room.Index
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.PrimaryKey
import androidx.room.Query
import androidx.room.RoomDatabase
import androidx.room.Transaction
import androidx.room.Update
import kotlinx.coroutines.flow.Flow

@Entity(tableName = "workouts", indices = [Index("date")])
data class Workout(
    @PrimaryKey val id: String,
    val date: String,
    val title: String,
    val notes: String = "",
    val createdAt: Long,
    val updatedAt: Long
)

@Entity(
    tableName = "exercises",
    foreignKeys = [ForeignKey(entity = Workout::class, parentColumns = ["id"], childColumns = ["workoutId"], onDelete = ForeignKey.CASCADE)],
    indices = [Index("workoutId")]
)
data class ExerciseEntry(
    @PrimaryKey val id: String,
    val workoutId: String,
    val name: String,
    val orderIndex: Int,
    val notes: String = ""
)

@Entity(
    tableName = "sets",
    foreignKeys = [ForeignKey(entity = ExerciseEntry::class, parentColumns = ["id"], childColumns = ["exerciseId"], onDelete = ForeignKey.CASCADE)],
    indices = [Index("exerciseId")]
)
data class SetEntry(
    @PrimaryKey val id: String,
    val exerciseId: String,
    val orderIndex: Int,
    val repetitions: Int,
    val weightKg: Double,
    val completed: Boolean = false,
    val notes: String = ""
)

@Entity(tableName = "workout_templates")
data class WorkoutTemplate(
    @PrimaryKey val id: String,
    val name: String,
    val notes: String = "",
    val createdAt: Long
)

@Entity(
    tableName = "template_exercises",
    foreignKeys = [ForeignKey(entity = WorkoutTemplate::class, parentColumns = ["id"], childColumns = ["templateId"], onDelete = ForeignKey.CASCADE)],
    indices = [Index("templateId")]
)
data class TemplateExercise(
    @PrimaryKey val id: String,
    val templateId: String,
    val name: String,
    val orderIndex: Int,
    val notes: String = ""
)

@Entity(
    tableName = "template_sets",
    foreignKeys = [ForeignKey(entity = TemplateExercise::class, parentColumns = ["id"], childColumns = ["templateExerciseId"], onDelete = ForeignKey.CASCADE)],
    indices = [Index("templateExerciseId")]
)
data class TemplateSet(
    @PrimaryKey val id: String,
    val templateExerciseId: String,
    val orderIndex: Int,
    val repetitions: Int,
    val weightKg: Double
)

@Entity(tableName = "body_measurements", indices = [Index("date")])
data class BodyMeasurement(
    @PrimaryKey val id: String,
    val date: String,
    val weightKg: Double?,
    val namedMeasurementsJson: String = "{}",
    val notes: String = "",
    val createdAt: Long
)

data class ExerciseWithSets(
    @androidx.room.Embedded val exercise: ExerciseEntry,
    @androidx.room.Relation(parentColumn = "id", entityColumn = "exerciseId")
    val sets: List<SetEntry>
)

data class WorkoutWithExercises(
    @androidx.room.Embedded val workout: Workout,
    @androidx.room.Relation(parentColumn = "id", entityColumn = "workoutId", entity = ExerciseEntry::class)
    val exercises: List<ExerciseWithSets>
)

data class ExerciseStat(
    val name: String,
    val sessionCount: Int,
    val totalRepetitions: Int
)

@Dao
interface FitnessDao {
    @Query("SELECT * FROM workouts ORDER BY date DESC, createdAt DESC")
    fun observeWorkouts(): Flow<List<Workout>>

    @Query("SELECT * FROM workouts WHERE date = :date ORDER BY createdAt DESC LIMIT 1")
    suspend fun workoutForDate(date: String): Workout?

    @Query("SELECT * FROM workouts WHERE id = :id LIMIT 1")
    suspend fun workout(id: String): Workout?

    @Transaction
    @Query("SELECT * FROM workouts WHERE id = :id")
    suspend fun workoutDetails(id: String): WorkoutWithExercises?

    @Query("SELECT * FROM body_measurements ORDER BY date DESC, createdAt DESC")
    fun observeMeasurements(): Flow<List<BodyMeasurement>>

    @Query("SELECT * FROM workout_templates ORDER BY name COLLATE NOCASE")
    fun observeTemplates(): Flow<List<WorkoutTemplate>>

    @Query("SELECT COALESCE(SUM(s.repetitions * s.weightKg), 0) FROM `sets` s WHERE s.completed = 1")
    fun observeCompletedVolume(): Flow<Double>

    @Query("SELECT e.name AS name, COUNT(DISTINCT e.workoutId) AS sessionCount, COALESCE(SUM(s.repetitions), 0) AS totalRepetitions FROM exercises e LEFT JOIN `sets` s ON s.exerciseId = e.id GROUP BY e.name ORDER BY sessionCount DESC, totalRepetitions DESC LIMIT 10")
    fun observeExerciseStats(): Flow<List<ExerciseStat>>

    @Query("SELECT * FROM template_exercises WHERE templateId = :templateId ORDER BY orderIndex")
    suspend fun templateExercises(templateId: String): List<TemplateExercise>

    @Query("SELECT * FROM template_sets WHERE templateExerciseId = :exerciseId ORDER BY orderIndex")
    suspend fun templateSets(exerciseId: String): List<TemplateSet>

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun putWorkout(item: Workout)
    @Update
    suspend fun updateWorkout(item: Workout)
    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun putExercise(item: ExerciseEntry)
    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun putSet(item: SetEntry)
    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun putTemplate(item: WorkoutTemplate)
    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun putTemplateExercise(item: TemplateExercise)
    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun putTemplateSet(item: TemplateSet)
    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun putMeasurement(item: BodyMeasurement)

    @Insert(onConflict = OnConflictStrategy.IGNORE)
    suspend fun mergeWorkouts(items: List<Workout>)
    @Insert(onConflict = OnConflictStrategy.IGNORE)
    suspend fun mergeExercises(items: List<ExerciseEntry>)
    @Insert(onConflict = OnConflictStrategy.IGNORE)
    suspend fun mergeSets(items: List<SetEntry>)
    @Insert(onConflict = OnConflictStrategy.IGNORE)
    suspend fun mergeTemplates(items: List<WorkoutTemplate>)
    @Insert(onConflict = OnConflictStrategy.IGNORE)
    suspend fun mergeTemplateExercises(items: List<TemplateExercise>)
    @Insert(onConflict = OnConflictStrategy.IGNORE)
    suspend fun mergeTemplateSets(items: List<TemplateSet>)
    @Insert(onConflict = OnConflictStrategy.IGNORE)
    suspend fun mergeMeasurements(items: List<BodyMeasurement>)

    @Query("DELETE FROM workouts")
    suspend fun clearWorkouts()
    @Query("DELETE FROM workout_templates")
    suspend fun clearTemplates()
    @Query("DELETE FROM body_measurements")
    suspend fun clearMeasurements()
    @Query("SELECT * FROM workouts")
    suspend fun allWorkouts(): List<Workout>
    @Query("SELECT * FROM exercises")
    suspend fun allExercises(): List<ExerciseEntry>
    @Query("SELECT * FROM `sets`")
    suspend fun allSets(): List<SetEntry>
    @Query("SELECT * FROM workout_templates")
    suspend fun allTemplates(): List<WorkoutTemplate>
    @Query("SELECT * FROM template_exercises")
    suspend fun allTemplateExercises(): List<TemplateExercise>
    @Query("SELECT * FROM template_sets")
    suspend fun allTemplateSets(): List<TemplateSet>
    @Query("SELECT * FROM body_measurements")
    suspend fun allMeasurements(): List<BodyMeasurement>
    @Query("DELETE FROM exercises WHERE id = :id")
    suspend fun deleteExercise(id: String)
    @Query("DELETE FROM workouts WHERE id = :id")
    suspend fun deleteWorkout(id: String)
    @Query("DELETE FROM workout_templates WHERE id = :id")
    suspend fun deleteTemplate(id: String)
}

@Database(
    entities = [Workout::class, ExerciseEntry::class, SetEntry::class, WorkoutTemplate::class, TemplateExercise::class, TemplateSet::class, BodyMeasurement::class],
    version = 1,
    exportSchema = true
)
abstract class FitnessDatabase : RoomDatabase() {
    abstract fun dao(): FitnessDao
}

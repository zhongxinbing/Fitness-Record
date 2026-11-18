package com.fitnessrecord.app.data

import com.google.gson.Gson
import java.time.LocalDate

data class BackupPayload(
    val formatVersion: Int = 1,
    val exportedAt: String = "",
    val workouts: List<Workout> = emptyList(),
    val exercises: List<ExerciseEntry> = emptyList(),
    val sets: List<SetEntry> = emptyList(),
    val templates: List<WorkoutTemplate> = emptyList(),
    val templateExercises: List<TemplateExercise> = emptyList(),
    val templateSets: List<TemplateSet> = emptyList(),
    val measurements: List<BodyMeasurement> = emptyList()
)

object BackupCodec {
    private val gson = Gson()

    fun encode(payload: BackupPayload): String = gson.toJson(payload)

    fun decodeAndValidate(json: String): BackupPayload {
        require(json.toByteArray(Charsets.UTF_8).size <= 10 * 1024 * 1024) { "备份文件不能超过 10 MB" }
        val payload = try {
            gson.fromJson(json, BackupPayload::class.java)
        } catch (_: Exception) {
            null
        } ?: throw IllegalArgumentException("备份文件格式无效")
        require(payload.formatVersion == 1) { "不支持此备份版本" }
        require(payload.workouts != null && payload.exercises != null && payload.sets != null &&
            payload.templates != null && payload.templateExercises != null && payload.templateSets != null &&
            payload.measurements != null) { "备份数据不完整" }
        validateIds("训练", payload.workouts.map { it.id })
        validateIds("动作", payload.exercises.map { it.id })
        validateIds("组", payload.sets.map { it.id })
        validateIds("模板", payload.templates.map { it.id })
        validateIds("模板动作", payload.templateExercises.map { it.id })
        validateIds("模板组", payload.templateSets.map { it.id })
        validateIds("测量", payload.measurements.map { it.id })
        val workoutIds = payload.workouts.map { it.id }.toSet()
        val exerciseIds = payload.exercises.map { it.id }.toSet()
        val templateIds = payload.templates.map { it.id }.toSet()
        val templateExerciseIds = payload.templateExercises.map { it.id }.toSet()
        payload.workouts.forEach {
            require(it.title.isNotBlank()) { "训练名称不能为空" }
            requireDate(it.date)
        }
        payload.exercises.forEach {
            require(it.workoutId in workoutIds && it.name.isNotBlank() && it.orderIndex >= 0) { "训练动作引用无效" }
        }
        payload.sets.forEach {
            require(it.exerciseId in exerciseIds && it.orderIndex >= 0 && it.repetitions in 1..1000 && it.weightKg.isFinite() && it.weightKg in 0.0..1000.0) {
                "组数、次数或重量无效"
            }
        }
        payload.templateExercises.forEach {
            require(it.templateId in templateIds && it.name.isNotBlank() && it.orderIndex >= 0) { "模板动作引用无效" }
        }
        payload.templates.forEach { require(it.name.isNotBlank()) { "模板名称不能为空" } }
        payload.templateSets.forEach {
            require(it.templateExerciseId in templateExerciseIds && it.orderIndex >= 0 && it.repetitions in 1..1000 && it.weightKg.isFinite() && it.weightKg in 0.0..1000.0) {
                "模板组数、次数或重量无效"
            }
        }
        payload.measurements.forEach {
            requireDate(it.date)
            require(it.weightKg == null || (it.weightKg.isFinite() && it.weightKg in 1.0..1000.0)) { "体重数值无效" }
            validateNamedMeasurements(it.namedMeasurementsJson)
        }
        return payload
    }

    private fun validateIds(label: String, ids: List<String>) {
        require(ids.all { it.isNotBlank() } && ids.toSet().size == ids.size) { "$label ID 缺失或重复" }
    }

    private fun requireDate(value: String) {
        try {
            LocalDate.parse(value)
        } catch (_: Exception) {
            throw IllegalArgumentException("日期格式无效")
        }
    }

    private fun validateNamedMeasurements(json: String) {
        try {
            require(json.isNotBlank())
            val values = gson.fromJson(json, Map::class.java) ?: emptyMap<Any, Any>()
            require(values.keys.all { it is String && it.isNotBlank() })
            require(values.values.all { it is Number && it.toDouble().isFinite() && it.toDouble() in 1.0..1000.0 })
        } catch (_: Exception) {
            throw IllegalArgumentException("围度数据格式无效")
        }
    }
}

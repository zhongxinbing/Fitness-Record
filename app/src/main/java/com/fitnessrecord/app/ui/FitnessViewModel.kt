package com.fitnessrecord.app.ui

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import androidx.room.Room
import com.fitnessrecord.app.data.BodyMeasurement
import com.fitnessrecord.app.data.FitnessDatabase
import com.fitnessrecord.app.data.FitnessRepository
import com.fitnessrecord.app.data.ExerciseStat
import com.fitnessrecord.app.data.SetEntry
import com.fitnessrecord.app.data.Workout
import com.fitnessrecord.app.data.WorkoutTemplate
import com.fitnessrecord.app.data.WorkoutWithExercises
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch

class FitnessViewModel(application: Application) : AndroidViewModel(application) {
    private val database = Room.databaseBuilder(application, FitnessDatabase::class.java, "fitness-record.db").build()
    private val repository = FitnessRepository(database)

    val workouts: StateFlow<List<Workout>> = repository.workouts.stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), emptyList())
    val measurements: StateFlow<List<BodyMeasurement>> = repository.measurements.stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), emptyList())
    val templates: StateFlow<List<WorkoutTemplate>> = repository.templates.stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), emptyList())
    val completedVolume = database.dao().observeCompletedVolume().stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), 0.0)
    val exerciseStats: StateFlow<List<ExerciseStat>> = database.dao().observeExerciseStats().stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), emptyList())
    private val _activeWorkout = MutableStateFlow<WorkoutWithExercises?>(null)
    val activeWorkout = _activeWorkout.asStateFlow()
    private val _message = MutableStateFlow<String?>(null)
    val message = _message.asStateFlow()

    fun openWorkout(date: String, title: String = "今日训练") = viewModelScope.launch {
        val id = repository.forDate(date)?.id ?: repository.createWorkout(date, title)
        loadWorkout(id)
    }

    fun loadWorkout(id: String) = viewModelScope.launch { _activeWorkout.value = repository.detail(id) }
    fun saveWorkout(title: String, notes: String) = activeWorkout.value?.let {
        viewModelScope.launch { repository.updateWorkout(it.workout.id, title, notes); loadWorkout(it.workout.id) }
    }
    fun addExercise(name: String) = activeWorkout.value?.let {
        viewModelScope.launch { repository.addExercise(it.workout.id, name); loadWorkout(it.workout.id) }
    }
    fun addSet(exerciseId: String) = viewModelScope.launch { repository.addSet(exerciseId); activeWorkout.value?.let { loadWorkout(it.workout.id) } }
    fun updateSet(set: SetEntry) = activeWorkout.value?.let {
        viewModelScope.launch { repository.updateSet(set); loadWorkout(it.workout.id) }
    }
    fun deleteExercise(id: String) = activeWorkout.value?.let {
        viewModelScope.launch { repository.removeExercise(id); loadWorkout(it.workout.id) }
    }
    fun deleteWorkout(id: String) = viewModelScope.launch {
        repository.removeWorkout(id)
        _activeWorkout.value = null
    }
    fun saveTemplate(name: String) = activeWorkout.value?.let {
        viewModelScope.launch {
            repository.saveTemplate(it.workout.id, name)
            _message.value = "模板已保存"
        }
    }
    fun useTemplate(template: WorkoutTemplate, date: String) = viewModelScope.launch {
        val id = repository.startTemplate(template, date)
        loadWorkout(id)
        _message.value = "已从模板开始训练"
    }
    fun deleteTemplate(id: String) = viewModelScope.launch { repository.removeTemplate(id) }
    fun addMeasurement(date: String, weightKg: Double?, namedMeasurementsJson: String, notes: String) = viewModelScope.launch {
        repository.addMeasurement(date, weightKg, namedMeasurementsJson, notes)
        _message.value = "身体数据已保存"
    }

    suspend fun exportBackup(): String = repository.exportBackup()
    suspend fun importBackup(json: String, merge: Boolean) {
        repository.importBackup(json, merge)
        _message.value = if (merge) "备份已合并" else "备份已恢复"
        _activeWorkout.value = null
    }
    fun showMessage(text: String) { _message.value = text }
    fun consumeMessage() { _message.value = null }

    override fun onCleared() {
        database.close()
        super.onCleared()
    }
}

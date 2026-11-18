package com.fitnessrecord.app.ui

import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.clickable
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.ArrowBack
import androidx.compose.material.icons.filled.ArrowForward
import androidx.compose.material.icons.filled.Check
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material.icons.filled.FitnessCenter
import androidx.compose.material.icons.filled.Home
import androidx.compose.material.icons.filled.MoreHoriz
import androidx.compose.material.icons.filled.ShowChart
import androidx.compose.material.icons.filled.Timer
import androidx.compose.material.icons.filled.Timeline
import androidx.compose.material.icons.filled.UploadFile
import androidx.compose.material.icons.filled.Scale
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.Checkbox
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardOptions
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.fitnessrecord.app.data.BodyMeasurement
import com.fitnessrecord.app.data.SetEntry
import com.fitnessrecord.app.data.Workout
import com.fitnessrecord.app.data.WorkoutTemplate
import com.google.gson.Gson
import com.google.gson.reflect.TypeToken
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import java.time.LocalDate
import java.time.format.DateTimeFormatter
import java.util.Locale

private enum class Page(val label: String) {
    TODAY("今日"), HISTORY("历史"), PROGRESS("进步"), MORE("更多"),
    EDITOR("训练记录"), TEMPLATES("训练模板"), BODY("身体数据"), TIMER("休息计时"), BACKUP("备份")
}

@Composable
fun FitnessTheme(content: @Composable () -> Unit) {
    val dark = androidx.compose.foundation.isSystemInDarkTheme()
    MaterialTheme(
        colorScheme = if (dark) androidx.compose.material3.darkColorScheme(
            primary = Color(0xFF9BD8C7), secondary = Color(0xFFFFB77D), surface = Color(0xFF111A18)
        ) else androidx.compose.material3.lightColorScheme(
            primary = Color(0xFF176B58), secondary = Color(0xFFB05D2A), surface = Color(0xFFF8FAF8)
        ),
        content = content
    )
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun FitnessApp(model: FitnessViewModel) {
    val workouts by model.workouts.collectAsState()
    val measurements by model.measurements.collectAsState()
    val templates by model.templates.collectAsState()
    val volume by model.completedVolume.collectAsState()
    val exerciseStats by model.exerciseStats.collectAsState()
    val activeWorkout by model.activeWorkout.collectAsState()
    val message by model.message.collectAsState()
    var page by rememberSaveable { mutableStateOf(Page.TODAY) }
    var selectedDateText by rememberSaveable { mutableStateOf(LocalDate.now().toString()) }
    val selectedDate = runCatching { LocalDate.parse(selectedDateText) }.getOrElse { LocalDate.now() }
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    var deleteWorkoutConfirmation by remember { mutableStateOf(false) }
    var pendingImport by remember { mutableStateOf<String?>(null) }

    val exportPicker = rememberLauncherForActivityResult(ActivityResultContracts.CreateDocument("application/json")) { uri ->
        if (uri != null) scope.launch {
            runCatching {
                val json = model.exportBackup()
                context.contentResolver.openOutputStream(uri)?.bufferedWriter(Charsets.UTF_8)?.use { it.write(json) }
                    ?: error("无法创建备份文件")
                model.showMessage("备份文件已导出")
            }.onFailure { model.showMessage("导出失败：${it.message ?: "未知错误"}") }
        }
    }
    val importPicker = rememberLauncherForActivityResult(ActivityResultContracts.OpenDocument()) { uri ->
        if (uri != null) scope.launch {
            runCatching {
                val json = context.contentResolver.openInputStream(uri)?.bufferedReader(Charsets.UTF_8)?.use { it.readText() }
                    ?: error("无法读取备份文件")
                pendingImport = json
            }.onFailure { model.showMessage("读取失败：${it.message ?: "文件无效"}") }
        }
    }

    LaunchedEffect(message) {
        if (message != null) {
            delay(3_000)
            model.consumeMessage()
        }
    }

    val mainPages = listOf(Page.TODAY, Page.HISTORY, Page.PROGRESS, Page.MORE)
    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text(page.label, fontWeight = FontWeight.Bold) },
                navigationIcon = {
                    if (page !in mainPages) IconButton(onClick = { page = Page.MORE }) {
                        Icon(Icons.Default.ArrowBack, contentDescription = "返回")
                    }
                },
                colors = TopAppBarDefaults.topAppBarColors(containerColor = MaterialTheme.colorScheme.surface)
            )
        },
        bottomBar = {
            if (page in mainPages) NavigationBar {
                listOf(Icons.Default.Home, Icons.Default.Timeline, Icons.Default.ShowChart, Icons.Default.MoreHoriz)
                    .zip(mainPages).forEach { (icon, item) ->
                        NavigationBarItem(
                            selected = page == item,
                            onClick = { page = item },
                            icon = { Icon(icon, contentDescription = item.label) },
                            label = { Text(item.label) }
                        )
                    }
            }
        },
        snackbarHost = {}
    ) { padding ->
        Box(Modifier.fillMaxSize().padding(padding)) {
            when (page) {
                Page.TODAY ->                 TodayPage(
                    workouts, measurements, LocalDate.now(), onOpenEditor = {
                        selectedDateText = LocalDate.now().toString()
                        model.openWorkout(LocalDate.now().toString())
                        page = Page.EDITOR
                    }, onNavigate = { page = it }
                )
                Page.HISTORY -> HistoryPage(
                    workouts, selectedDate, onDateChange = { selectedDateText = it },
                    onOpen = { workout -> selectedDateText = workout.date; model.loadWorkout(workout.id); page = Page.EDITOR },
                    onCreate = { model.openWorkout(selectedDate.toString()); page = Page.EDITOR }
                )
                Page.PROGRESS -> ProgressPage(workouts, volume, exerciseStats, measurements)
                Page.MORE -> MorePage(onNavigate = { page = it })
                Page.EDITOR -> WorkoutEditor(
                    workout = activeWorkout,
                    date = selectedDateText,
                    onDateChange = { selectedDateText = it },
                    onOpenDate = { model.openWorkout(it) },
                    onSave = { title, notes -> model.saveWorkout(title, notes) },
                    onAddExercise = { name -> model.addExercise(name) },
                    onAddSet = { id -> model.addSet(id) },
                    onUpdateSet = { set -> model.updateSet(set) },
                    onDeleteExercise = { id -> model.deleteExercise(id) },
                    onDeleteWorkout = { deleteWorkoutConfirmation = true },
                    onSaveTemplate = { name -> model.saveTemplate(name) }
                )
                Page.TEMPLATES -> TemplatesPage(
                    templates = templates, date = selectedDateText, onDateChange = { selectedDateText = it },
                    onUse = { model.useTemplate(it, selectedDateText); page = Page.EDITOR },
                    onDelete = { id -> model.deleteTemplate(id) }
                )
                Page.BODY -> BodyPage(measurements, onSave = { date, weight, named, notes ->
                    model.addMeasurement(date, weight, named, notes)
                })
                Page.TIMER -> RestTimerPage()
                Page.BACKUP -> BackupPage(
                    onExport = { exportPicker.launch("fitness-record-${LocalDate.now()}.json") },
                    onImport = { importPicker.launch(arrayOf("application/json", "text/*")) }
                )
            }
            if (message != null) {
                Surface(
                    modifier = Modifier.align(Alignment.BottomCenter).padding(16.dp),
                    color = MaterialTheme.colorScheme.inverseSurface,
                    shape = MaterialTheme.shapes.medium,
                    shadowElevation = 6.dp
                ) { Text(message.orEmpty(), color = MaterialTheme.colorScheme.inverseOnSurface, modifier = Modifier.padding(horizontal = 18.dp, vertical = 12.dp)) }
            }
        }
    }
    if (deleteWorkoutConfirmation) {
        AlertDialog(
            onDismissRequest = { deleteWorkoutConfirmation = false },
            title = { Text("删除这次训练？") },
            text = { Text("训练中的动作和组也会一起删除。此操作无法撤销。") },
            confirmButton = {
                TextButton(onClick = {
                    activeWorkout?.let { model.deleteWorkout(it.workout.id) }
                    deleteWorkoutConfirmation = false
                    page = Page.HISTORY
                }) { Text("删除") }
            },
            dismissButton = { TextButton(onClick = { deleteWorkoutConfirmation = false }) { Text("取消") } }
        )
    }
    if (pendingImport != null) {
        AlertDialog(
            onDismissRequest = { pendingImport = null },
            title = { Text("导入本地备份") },
            text = { Text("选择合并到现有记录，或先清空本地记录再恢复。导入前会校验备份内容。") },
            confirmButton = {
                TextButton(onClick = {
                    val json = pendingImport
                    pendingImport = null
                    if (json != null) scope.launch {
                        runCatching { model.importBackup(json, merge = true) }
                            .onFailure { model.showMessage("导入失败：${it.message ?: "备份无效"}") }
                    }
                }) { Text("合并") }
            },
            dismissButton = {
                Row {
                    TextButton(onClick = {
                        val json = pendingImport
                        pendingImport = null
                        if (json != null) scope.launch {
                            runCatching { model.importBackup(json, merge = false) }
                                .onFailure { model.showMessage("导入失败：${it.message ?: "备份无效"}") }
                        }
                    }) { Text("替换本机数据") }
                    TextButton(onClick = { pendingImport = null }) { Text("取消") }
                }
            }
        )
    }
}

@Composable
private fun TodayPage(
    workouts: List<Workout>,
    measurements: List<BodyMeasurement>,
    today: LocalDate,
    onOpenEditor: () -> Unit,
    onNavigate: (Page) -> Unit
) {
    val todayWorkout = workouts.firstOrNull { it.date == today.toString() }
    val lastWeight = measurements.firstNotNullOfOrNull { it.weightKg }
    LazyColumn(Modifier.fillMaxSize(), contentPadding = androidx.compose.foundation.layout.PaddingValues(20.dp), verticalArrangement = Arrangement.spacedBy(14.dp)) {
        item {
            Text(today.format(DateTimeFormatter.ofPattern("M月d日 · EEEE", Locale.SIMPLIFIED_CHINESE)), style = MaterialTheme.typography.titleMedium, color = MaterialTheme.colorScheme.secondary)
            Text("为今天的自己，留下进步。", style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.Bold, modifier = Modifier.padding(top = 5.dp))
        }
        item {
            Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.primaryContainer)) {
                Column(Modifier.fillMaxWidth().padding(20.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Icon(Icons.Default.FitnessCenter, contentDescription = null, tint = MaterialTheme.colorScheme.primary)
                        Spacer(Modifier.width(10.dp))
                        Text(if (todayWorkout == null) "今天还没有训练" else todayWorkout.title, style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold)
                    }
                    Text(if (todayWorkout == null) "准备好开始一组了吗？记录动作、次数和重量。" else "训练记录已保存，可继续添加动作或调整组数。")
                    Button(onClick = onOpenEditor, modifier = Modifier.fillMaxWidth()) {
                        Text(if (todayWorkout == null) "开始记录训练" else "打开今日训练")
                    }
                }
            }
        }
        item {
            Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                MetricCard("累计训练", "${workouts.size} 次", Modifier.weight(1f))
                MetricCard("最近体重", lastWeight?.let { "${formatNumber(it)} kg" } ?: "未记录", Modifier.weight(1f))
            }
        }
        item { SectionTitle("快速入口") }
        item {
            Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                QuickLink(Icons.Default.Timeline, "训练历史", "回顾每次训练", onClick = { onNavigate(Page.HISTORY) })
                QuickLink(Icons.Default.Scale, "身体数据", "记录体重与围度", onClick = { onNavigate(Page.BODY) })
                QuickLink(Icons.Default.Timer, "休息计时", "专注组间恢复", onClick = { onNavigate(Page.TIMER) })
            }
        }
    }
}

@Composable
private fun HistoryPage(
    workouts: List<Workout>,
    selectedDate: LocalDate,
    onDateChange: (String) -> Unit,
    onOpen: (Workout) -> Unit,
    onCreate: () -> Unit
) {
    LazyColumn(Modifier.fillMaxSize(), contentPadding = androidx.compose.foundation.layout.PaddingValues(20.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        item {
            MonthCalendar(workouts, selectedDate, onDateChange)
            DateNavigator(selectedDate, onDateChange)
            Button(onClick = onCreate, modifier = Modifier.fillMaxWidth().padding(top = 8.dp)) { Text("记录这一天的训练") }
        }
        item { SectionTitle("训练记录 · ${workouts.size}") }
        if (workouts.isEmpty()) item { EmptyCard("还没有训练记录", "完成训练后，记录会出现在这里。") }
        items(workouts, key = { it.id }) { workout ->
            Card(Modifier.fillMaxWidth().clickable { onOpen(workout) }, border = BorderStroke(1.dp, MaterialTheme.colorScheme.outlineVariant)) {
                Row(Modifier.fillMaxWidth().padding(16.dp), verticalAlignment = Alignment.CenterVertically) {
                    Column(Modifier.weight(1f)) {
                        Text(workout.date, color = MaterialTheme.colorScheme.secondary, style = MaterialTheme.typography.labelLarge)
                        Text(workout.title, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold)
                        if (workout.notes.isNotBlank()) Text(workout.notes, style = MaterialTheme.typography.bodySmall, maxLines = 2)
                    }
                    Icon(Icons.Default.ArrowForward, contentDescription = "查看训练", tint = MaterialTheme.colorScheme.primary)
                }
            }
        }
    }
}

@Composable
private fun MonthCalendar(
    workouts: List<Workout>,
    selectedDate: LocalDate,
    onDateChange: (String) -> Unit
) {
    val firstDay = selectedDate.withDayOfMonth(1)
    val dayOffset = firstDay.dayOfWeek.value - 1
    val daysInMonth = firstDay.lengthOfMonth()
    val weekCount = (dayOffset + daysInMonth + 6) / 7
    val workoutDates = workouts.mapTo(mutableSetOf()) { it.date }

    Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            IconButton(onClick = {
                val month = firstDay.minusMonths(1)
                onDateChange(month.withDayOfMonth(selectedDate.dayOfMonth.coerceAtMost(month.lengthOfMonth())).toString())
            }) { Icon(Icons.Default.ArrowBack, contentDescription = "上个月") }
            Text(
                firstDay.format(DateTimeFormatter.ofPattern("yyyy年M月", Locale.SIMPLIFIED_CHINESE)),
                modifier = Modifier.weight(1f),
                style = MaterialTheme.typography.titleMedium,
                fontWeight = FontWeight.SemiBold
            )
            IconButton(onClick = {
                val month = firstDay.plusMonths(1)
                onDateChange(month.withDayOfMonth(selectedDate.dayOfMonth.coerceAtMost(month.lengthOfMonth())).toString())
            }) { Icon(Icons.Default.ArrowForward, contentDescription = "下个月") }
        }
        Row {
            listOf("一", "二", "三", "四", "五", "六", "日").forEach { day ->
                Text(day, modifier = Modifier.weight(1f), color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
        }
        repeat(weekCount) { week ->
            Row {
                repeat(7) { weekday ->
                    val dayNumber = week * 7 + weekday - dayOffset + 1
                    if (dayNumber in 1..daysInMonth) {
                        val date = firstDay.withDayOfMonth(dayNumber)
                        val isSelected = date == selectedDate
                        val hasWorkout = date.toString() in workoutDates
                        Surface(
                            modifier = Modifier.weight(1f).height(42.dp).clickable { onDateChange(date.toString()) },
                            shape = CircleShape,
                            color = if (isSelected) MaterialTheme.colorScheme.primaryContainer else Color.Transparent
                        ) {
                            Column(
                                Modifier.fillMaxSize(),
                                horizontalAlignment = Alignment.CenterHorizontally,
                                verticalArrangement = Arrangement.Center
                            ) {
                                Text(dayNumber.toString(), color = if (isSelected) MaterialTheme.colorScheme.onPrimaryContainer else MaterialTheme.colorScheme.onSurface)
                                if (hasWorkout) Surface(Modifier.size(4.dp), shape = CircleShape, color = MaterialTheme.colorScheme.secondary) {}
                            }
                        }
                    } else {
                        Spacer(Modifier.weight(1f).height(42.dp))
                    }
                }
            }
        }
    }
}

@Composable
private fun WorkoutEditor(
    workout: com.fitnessrecord.app.data.WorkoutWithExercises?,
    date: String,
    onDateChange: (String) -> Unit,
    onOpenDate: (String) -> Unit,
    onSave: (String, String) -> Unit,
    onAddExercise: (String) -> Unit,
    onAddSet: (String) -> Unit,
    onUpdateSet: (SetEntry) -> Unit,
    onDeleteExercise: (String) -> Unit,
    onDeleteWorkout: () -> Unit,
    onSaveTemplate: (String) -> Unit
) {
    var title by remember(workout?.workout?.id) { mutableStateOf(workout?.workout?.title.orEmpty()) }
    var notes by remember(workout?.workout?.id) { mutableStateOf(workout?.workout?.notes.orEmpty()) }
    var exerciseName by remember { mutableStateOf("") }
    var templateName by remember { mutableStateOf("") }
    var confirmExerciseDelete by remember { mutableStateOf<String?>(null) }
    LazyColumn(Modifier.fillMaxSize(), contentPadding = androidx.compose.foundation.layout.PaddingValues(18.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        item {
            DateNavigator(parseOrToday(date), onDateChange, onDateSelected = onOpenDate)
        }
        if (workout == null) {
            item { EmptyCard("正在准备训练记录", "选择日期后可开始记录。") }
        } else {
            item {
                OutlinedTextField(title, { title = it }, label = { Text("训练名称") }, modifier = Modifier.fillMaxWidth(), singleLine = true)
                OutlinedTextField(notes, { notes = it }, label = { Text("训练备注（可选）") }, modifier = Modifier.fillMaxWidth())
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Button(onClick = { onSave(title, notes) }, modifier = Modifier.weight(1f)) { Text("保存训练信息") }
                    OutlinedButton(onClick = onDeleteWorkout) { Icon(Icons.Default.Delete, null); Text("删除") }
                }
            }
            item { SectionTitle("训练动作 · ${workout.exercises.size}") }
            if (workout.exercises.isEmpty()) item { EmptyCard("添加第一个动作", "例如：深蹲、卧推或慢跑。") }
            items(workout.exercises.sortedBy { it.exercise.orderIndex }, key = { it.exercise.id }) { exercise ->
                Card(Modifier.fillMaxWidth(), border = BorderStroke(1.dp, MaterialTheme.colorScheme.outlineVariant)) {
                    Column(Modifier.fillMaxWidth().padding(14.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Text(exercise.exercise.name, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold, modifier = Modifier.weight(1f))
                            IconButton(onClick = { confirmExerciseDelete = exercise.exercise.id }) {
                                Icon(Icons.Default.Delete, contentDescription = "删除${exercise.exercise.name}")
                            }
                        }
                        exercise.sets.sortedBy { it.orderIndex }.forEachIndexed { index, set ->
                            SetEditor(index + 1, set, onUpdateSet)
                        }
                        TextButton(onClick = { onAddSet(exercise.exercise.id) }) {
                            Icon(Icons.Default.Add, contentDescription = null); Text("添加一组")
                        }
                    }
                }
            }
            item {
                OutlinedTextField(
                    exerciseName, { exerciseName = it }, label = { Text("动作名称") }, modifier = Modifier.fillMaxWidth(),
                    trailingIcon = {
                        IconButton(onClick = {
                            if (exerciseName.isNotBlank()) { onAddExercise(exerciseName); exerciseName = "" }
                        }, enabled = exerciseName.isNotBlank()) { Icon(Icons.Default.Add, contentDescription = "添加动作") }
                    },
                    singleLine = true
                )
                Text("每个新动作会自动添加一组，可在组卡片中调整次数与重量。", style = MaterialTheme.typography.bodySmall)
            }
            item {
                HorizontalDivider()
                SectionTitle("保存为模板")
                OutlinedTextField(templateName, { templateName = it }, label = { Text("模板名称") }, modifier = Modifier.fillMaxWidth())
                Button(onClick = { if (templateName.isNotBlank()) { onSaveTemplate(templateName); templateName = "" } }, enabled = templateName.isNotBlank()) {
                    Text("保存当前训练为模板")
                }
            }
        }
    }
    if (confirmExerciseDelete != null) {
        AlertDialog(
            onDismissRequest = { confirmExerciseDelete = null },
            title = { Text("删除这个动作？") },
            text = { Text("动作下的所有组也会删除。") },
            confirmButton = { TextButton(onClick = { confirmExerciseDelete?.let(onDeleteExercise); confirmExerciseDelete = null }) { Text("删除") } },
            dismissButton = { TextButton(onClick = { confirmExerciseDelete = null }) { Text("取消") } }
        )
    }
}

@Composable
private fun SetEditor(index: Int, set: SetEntry, onUpdate: (SetEntry) -> Unit) {
    var reps by remember(set.id) { mutableStateOf(set.repetitions.toString()) }
    var weight by remember(set.id) { mutableStateOf(if (set.weightKg == 0.0) "" else formatNumber(set.weightKg)) }
    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
        Text("第 $index 组", style = MaterialTheme.typography.labelLarge, modifier = Modifier.width(48.dp))
        OutlinedTextField(
            value = reps, onValueChange = { reps = it.filter(Char::isDigit).take(4) },
            modifier = Modifier.weight(0.9f), label = { Text("次数") }, singleLine = true,
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number)
        )
        OutlinedTextField(
            value = weight, onValueChange = { weight = it.filter { char -> char.isDigit() || char == '.' }.take(7) },
            modifier = Modifier.weight(1.1f), label = { Text("kg") }, singleLine = true,
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal)
        )
        Checkbox(
            checked = set.completed,
            onCheckedChange = { checked ->
                val repetitions = reps.toIntOrNull()?.takeIf { it in 1..1000 }
                val kg = (weight.toDoubleOrNull() ?: 0.0).takeIf { it in 0.0..1000.0 }
                if (repetitions != null && kg != null) onUpdate(set.copy(repetitions = repetitions, weightKg = kg, completed = checked))
            },
            modifier = Modifier.semantics { contentDescription = "标记第${index}组完成" }
        )
        IconButton(onClick = {
            val repetitions = reps.toIntOrNull()?.takeIf { it in 1..1000 }
            val kg = (weight.toDoubleOrNull() ?: 0.0).takeIf { it in 0.0..1000.0 }
            if (repetitions != null && kg != null) onUpdate(set.copy(repetitions = repetitions, weightKg = kg))
        }) { Icon(Icons.Default.Check, contentDescription = "保存第${index}组") }
    }
}

@Composable
private fun TemplatesPage(
    templates: List<WorkoutTemplate>,
    date: String,
    onDateChange: (String) -> Unit,
    onUse: (WorkoutTemplate) -> Unit,
    onDelete: (String) -> Unit
) {
    var confirmDelete by remember { mutableStateOf<WorkoutTemplate?>(null) }
    LazyColumn(Modifier.fillMaxSize(), contentPadding = androidx.compose.foundation.layout.PaddingValues(20.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        item {
            Text("选择一个日期，用模板快速开始训练。", style = MaterialTheme.typography.bodyMedium)
            DateNavigator(parseOrToday(date), onDateChange)
        }
        if (templates.isEmpty()) item { EmptyCard("还没有训练模板", "在训练记录页编辑一份训练，然后保存为模板。") }
        items(templates, key = { it.id }) { template ->
            Card(Modifier.fillMaxWidth(), border = BorderStroke(1.dp, MaterialTheme.colorScheme.outlineVariant)) {
                Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text(template.name, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)
                    if (template.notes.isNotBlank()) Text(template.notes)
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        Button(onClick = { onUse(template) }, modifier = Modifier.weight(1f)) { Text("开始训练") }
                        IconButton(onClick = { confirmDelete = template }, modifier = Modifier.semantics { contentDescription = "删除模板${template.name}" }) {
                            Icon(Icons.Default.Delete, contentDescription = null)
                        }
                    }
                }
            }
        }
    }
    confirmDelete?.let { template ->
        AlertDialog(
            onDismissRequest = { confirmDelete = null },
            title = { Text("删除模板？") },
            confirmButton = { TextButton(onClick = { onDelete(template.id); confirmDelete = null }) { Text("删除") } },
            dismissButton = { TextButton(onClick = { confirmDelete = null }) { Text("取消") } }
        )
    }
}

@Composable
private fun BodyPage(measurements: List<BodyMeasurement>, onSave: (String, Double?, String, String) -> Unit) {
    var date by rememberSaveable { mutableStateOf(LocalDate.now().toString()) }
    var weight by rememberSaveable { mutableStateOf("") }
    var waist by rememberSaveable { mutableStateOf("") }
    var hip by rememberSaveable { mutableStateOf("") }
    var notes by rememberSaveable { mutableStateOf("") }
    val validWeight = weight.isBlank() || weight.toDoubleOrNull()?.let { it in 1.0..1000.0 } == true
    val validWaist = waist.isBlank() || waist.toDoubleOrNull()?.let { it in 1.0..1000.0 } == true
    val validHip = hip.isBlank() || hip.toDoubleOrNull()?.let { it in 1.0..1000.0 } == true
    val hasMeasurement = weight.isNotBlank() || waist.isNotBlank() || hip.isNotBlank()
    LazyColumn(Modifier.fillMaxSize(), contentPadding = androidx.compose.foundation.layout.PaddingValues(20.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        item { Text("记录体重与围度，观察长期变化。", style = MaterialTheme.typography.bodyMedium) }
        item { DateNavigator(parseOrToday(date), { date = it }) }
        item {
            Card {
                Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                    SectionTitle("新增测量")
                    NumberField(weight, { weight = it }, "体重 kg")
                    NumberField(waist, { waist = it }, "腰围 cm（可选）")
                    NumberField(hip, { hip = it }, "臀围 cm（可选）")
                    OutlinedTextField(notes, { notes = it }, label = { Text("备注（可选）" ) }, modifier = Modifier.fillMaxWidth())
                    Button(onClick = {
                        val kg = weight.toDoubleOrNull()
                        val named = listOfNotNull(waist.toDoubleOrNull(), hip.toDoubleOrNull())
                        if (named.any { it !in 1.0..1000.0 }) return@Button
                        val json = Gson().toJson(buildMap {
                            waist.toDoubleOrNull()?.let { if (it in 1.0..1000.0) put("腰围", it) }
                            hip.toDoubleOrNull()?.let { if (it in 1.0..1000.0) put("臀围", it) }
                        })
                        onSave(date, kg, json, notes)
                        weight = ""; waist = ""; hip = ""; notes = ""
                    }, enabled = hasMeasurement && validWeight && validWaist && validHip, modifier = Modifier.fillMaxWidth()) { Text("保存测量") }
                }
            }
        }
        item { SectionTitle("测量历史") }
        if (measurements.isEmpty()) item { EmptyCard("还没有身体数据", "你的每次测量都会保存在本机。") }
        items(measurements, key = { it.id }) { item ->
            MeasurementCard(item)
        }
    }
}

@Composable
private fun MeasurementCard(item: BodyMeasurement) {
    val measures = runCatching {
        val type = object : TypeToken<Map<String, Double>>() {}.type
        Gson().fromJson<Map<String, Double>>(item.namedMeasurementsJson, type).orEmpty()
    }.getOrDefault(emptyMap())
    Card(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Text(item.date, color = MaterialTheme.colorScheme.secondary, style = MaterialTheme.typography.labelLarge)
            Text(item.weightKg?.let { "体重 ${formatNumber(it)} kg" } ?: "身体测量", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold)
            if (measures.isNotEmpty()) Text(measures.entries.joinToString(" · ") { "${it.key} ${formatNumber(it.value)} cm" })
            if (item.notes.isNotBlank()) Text(item.notes, style = MaterialTheme.typography.bodySmall)
        }
    }
}

@Composable
private fun ProgressPage(
    workouts: List<Workout>,
    volume: Double,
    exerciseStats: List<com.fitnessrecord.app.data.ExerciseStat>,
    measurements: List<BodyMeasurement>
) {
    val weightEntries = measurements.filter { it.weightKg != null }.sortedBy { it.date }
    LazyColumn(Modifier.fillMaxSize(), contentPadding = androidx.compose.foundation.layout.PaddingValues(20.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        item { Text("稳步积累，每次训练都算数。", style = MaterialTheme.typography.bodyMedium) }
        item {
            Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                MetricCard("训练次数", "${workouts.size}", Modifier.weight(1f))
                MetricCard("已完成训练量", "${formatNumber(volume)} kg", Modifier.weight(1f))
            }
        }
        item { SectionTitle("常练动作") }
        if (exerciseStats.isEmpty()) item { EmptyCard("还没有动作统计", "完成训练组后，这里会汇总动作记录。") }
        items(exerciseStats, key = { it.name }) { stat ->
            Card(Modifier.fillMaxWidth()) {
                Row(Modifier.padding(14.dp), verticalAlignment = Alignment.CenterVertically) {
                    Column(Modifier.weight(1f)) {
                        Text(stat.name, fontWeight = FontWeight.SemiBold)
                        Text("${stat.sessionCount} 次训练 · ${stat.totalRepetitions} 次重复", style = MaterialTheme.typography.bodySmall)
                    }
                    Text("${stat.sessionCount} 次", color = MaterialTheme.colorScheme.secondary)
                }
            }
        }
        item { SectionTitle("体重趋势") }
        if (weightEntries.isEmpty()) item { EmptyCard("暂无线条可绘制", "添加至少一条体重记录后可查看变化。") }
        else item { WeightTrend(weightEntries) }
    }
}

@Composable
private fun WeightTrend(entries: List<BodyMeasurement>) {
    val first = entries.first().weightKg ?: 0.0
    val last = entries.last().weightKg ?: first
    Card(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Text("${formatNumber(first)} kg  →  ${formatNumber(last)} kg", style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold)
            Text("${entries.first().date} 至 ${entries.last().date} · ${entries.size} 次测量")
            Text(if (last < first) "整体下降 ${formatNumber(first - last)} kg" else if (last > first) "整体上升 ${formatNumber(last - first)} kg" else "体重保持稳定")
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                entries.takeLast(8).forEach { item ->
                    Surface(
                        modifier = Modifier.weight(1f).height((32 + ((item.weightKg ?: first).coerceIn(0.0, 200.0) / 5).toInt()).dp),
                        color = MaterialTheme.colorScheme.primaryContainer,
                        shape = MaterialTheme.shapes.small
                    ) {}
                }
            }
        }
    }
}

@Composable
private fun RestTimerPage() {
    var selectedDuration by rememberSaveable { mutableIntStateOf(90) }
    var remaining by rememberSaveable { mutableIntStateOf(90) }
    var running by rememberSaveable { mutableStateOf(false) }
    LaunchedEffect(running, remaining) {
        if (running && remaining > 0) {
            delay(1_000)
            remaining -= 1
        } else if (running) {
            running = false
        }
    }
    Column(
        Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(24.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.spacedBy(22.dp)
    ) {
        Text("组间休息", style = MaterialTheme.typography.titleLarge)
        Text("%02d:%02d".format(remaining / 60, remaining % 60), fontSize = 64.sp, fontWeight = FontWeight.Bold, color = MaterialTheme.colorScheme.primary)
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            listOf(60, 90, 120, 180).forEach { seconds ->
                OutlinedButton(onClick = {
                    selectedDuration = seconds
                    remaining = seconds
                    running = false
                }) { Text("${seconds / 60}:${"%02d".format(seconds % 60)}") }
            }
        }
        Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            Button(onClick = { if (remaining == 0) remaining = selectedDuration; running = !running }) {
                Text(if (running) "暂停" else if (remaining == 0) "重新开始" else "开始")
            }
            OutlinedButton(onClick = { running = false; remaining = selectedDuration }) { Text("重置") }
        }
        Text(if (remaining == 0) "休息完成，准备好下一组了吗？" else "选择适合自己的休息时间。", color = MaterialTheme.colorScheme.secondary)
    }
}

@Composable
private fun BackupPage(onExport: () -> Unit, onImport: () -> Unit) {
    Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(20.dp), verticalArrangement = Arrangement.spacedBy(14.dp)) {
        Card {
            Column(Modifier.padding(18.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Text("数据只保存在这台设备", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)
                Text("通过系统文件选择器导出或导入 JSON 备份。应用不会连接网络或上传个人记录。")
            }
        }
        Button(onClick = onExport, modifier = Modifier.fillMaxWidth()) {
            Icon(Icons.Default.UploadFile, contentDescription = null); Spacer(Modifier.width(8.dp)); Text("导出 JSON 备份")
        }
        OutlinedButton(onClick = onImport, modifier = Modifier.fillMaxWidth()) { Text("导入 JSON 备份") }
        Text("导入时可选择合并或替换。本地数据替换会先校验备份并在事务中完成。", style = MaterialTheme.typography.bodySmall)
    }
}

@Composable
private fun MorePage(onNavigate: (Page) -> Unit) {
    Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(20.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
        Text("管理训练与个人记录", style = MaterialTheme.typography.bodyMedium)
        QuickLink(Icons.Default.FitnessCenter, "训练模板", "复用常见训练安排", onClick = { onNavigate(Page.TEMPLATES) })
        QuickLink(Icons.Default.Scale, "身体数据", "体重、围度与趋势", onClick = { onNavigate(Page.BODY) })
        QuickLink(Icons.Default.Timer, "休息计时", "可暂停的组间计时器", onClick = { onNavigate(Page.TIMER) })
        QuickLink(Icons.Default.UploadFile, "本地备份", "通过系统文件选择器导入或导出", onClick = { onNavigate(Page.BACKUP) })
        Card {
            Text("健身记录 · 离线版\n所有记录储存在本机。", modifier = Modifier.padding(16.dp), style = MaterialTheme.typography.bodySmall)
        }
    }
}

@Composable
private fun DateNavigator(
    date: LocalDate,
    onDateChange: (String) -> Unit,
    onDateSelected: ((String) -> Unit)? = null
) {
    Row(Modifier.fillMaxWidth().padding(vertical = 8.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.Center) {
        IconButton(onClick = {
            val value = date.minusDays(1).toString()
            onDateChange(value)
            onDateSelected?.invoke(value)
        }) { Icon(Icons.Default.ArrowBack, contentDescription = "前一天") }
        Column(horizontalAlignment = Alignment.CenterHorizontally, modifier = Modifier.weight(1f)) {
            Text(date.format(DateTimeFormatter.ofPattern("yyyy年M月d日", Locale.SIMPLIFIED_CHINESE)), fontWeight = FontWeight.SemiBold)
            OutlinedTextField(
                value = date.toString(),
                onValueChange = {},
                readOnly = true,
                label = { Text("日期") }, singleLine = true, modifier = Modifier.width(180.dp),
                textStyle = MaterialTheme.typography.bodySmall
            )
        }
        IconButton(onClick = {
            val value = date.plusDays(1).toString()
            onDateChange(value)
            onDateSelected?.invoke(value)
        }) { Icon(Icons.Default.ArrowForward, contentDescription = "后一天") }
    }
}

@Composable
private fun NumberField(value: String, onChange: (String) -> Unit, label: String) {
    OutlinedTextField(
        value = value, onValueChange = { input -> onChange(input.filter { it.isDigit() || it == '.' }.take(7)) },
        label = { Text(label) }, modifier = Modifier.fillMaxWidth(), singleLine = true,
        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal)
    )
}

@Composable
private fun MetricCard(title: String, value: String, modifier: Modifier = Modifier) {
    Card(modifier, colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.secondaryContainer)) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(5.dp)) {
            Text(title, style = MaterialTheme.typography.labelMedium)
            Text(value, style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold)
        }
    }
}

@Composable
private fun SectionTitle(text: String) {
    Text(text, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold, modifier = Modifier.padding(top = 4.dp))
}

@Composable
private fun EmptyCard(title: String, subtitle: String) {
    Card(Modifier.fillMaxWidth(), colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant)) {
        Column(Modifier.padding(18.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Text(title, fontWeight = FontWeight.SemiBold)
            Text(subtitle, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
    }
}

@Composable
private fun QuickLink(icon: androidx.compose.ui.graphics.vector.ImageVector, title: String, subtitle: String, onClick: () -> Unit) {
    Card(Modifier.fillMaxWidth().clickable(onClick = onClick)) {
        Row(Modifier.padding(14.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            Icon(icon, contentDescription = null, tint = MaterialTheme.colorScheme.primary)
            Column(Modifier.weight(1f)) {
                Text(title, fontWeight = FontWeight.SemiBold)
                Text(subtitle, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
            Icon(Icons.Default.ArrowForward, contentDescription = "打开$title", tint = MaterialTheme.colorScheme.secondary)
        }
    }
}

private fun parseOrToday(value: String): LocalDate =
    runCatching { LocalDate.parse(value) }.getOrElse { LocalDate.now() }

private fun formatNumber(number: Double): String =
    String.format(Locale.US, if (number % 1.0 == 0.0) "%.0f" else "%.1f", number)

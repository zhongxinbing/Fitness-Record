package com.fitnessrecord.app

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.lifecycle.viewmodel.compose.viewModel
import com.fitnessrecord.app.ui.FitnessApp
import com.fitnessrecord.app.ui.FitnessViewModel
import com.fitnessrecord.app.ui.FitnessTheme

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            FitnessTheme {
                val model: FitnessViewModel = viewModel()
                FitnessApp(model)
            }
        }
    }
}

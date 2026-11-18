# Fitness-Record

离线优先的 Android 健身训练记录应用，使用 Kotlin、Jetpack Compose、Material 3 与 Room。界面为中文；所有记录默认保存在设备本地，不需要网络、账户或云服务。也可在支持 Android APK 兼容模式的 HarmonyOS 设备运行。

## 功能

- 按日期记录训练、动作、组数、次数、重量、完成状态和备注
- 保存并复用训练模板；通过月历快速查看训练日期并浏览历史
- 汇总完成训练量、常练动作与体重变化
- 记录体重、腰围、臀围和备注
- 可选时长、暂停与重置的组间计时器
- 通过 Android 系统文件选择器导出/导入 JSON 备份；导入前校验，可合并或替换

## 构建与验证

需要 JDK 17、Android SDK Platform 35 和 Gradle 8.9 或兼容版本：

```text
gradle :app:assembleDebug
gradle :app:testDebugUnitTest
gradle :app:connectedDebugAndroidTest
```

应用源码在 `app/`，入口为 `com.fitnessrecord.app.MainActivity`。Room 数据库不预置任何训练数据。单元测试覆盖备份往返和无效数据；仪器测试覆盖关联记录持久化。

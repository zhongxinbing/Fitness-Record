# 健身记录（Python / Kivy）

离线优先的手机健身记录应用。训练计划、训练记录和体重数据保存在应用的本机私有目录，不需要账户或网络连接。

## 功能

- 自定义训练名称和部位，逐个添加动作并设置组数、每组次数和重量
- 将训练保存为可重复使用的计划
- 查看训练历史并删除记录
- 按月统计训练次数和训练部位
- 计算训练总量（组数 × 次数 × 重量）趋势
- 记录体重并查看体重变化趋势

## Windows 桌面运行

需要 Python 3.10 或更新版本：

```powershell
cd C:\Users\xbzhong\Desktop\lint\script\Fitness-Record\python
python -m pip install -r requirements.txt
python main.py
```

数据保存在 Kivy 提供的应用私有数据目录中的 `fitness_record.json`。卸载应用或清除应用数据可能会删除这些本地记录；当前版本没有云同步或备份功能。

## 手机平台说明

- **Android**：Kivy 可打包为 APK/AAB。建议在 Linux 或 WSL 中安装 Buildozer 后构建；Windows 可用于开发和桌面运行，但不是官方 Buildozer Android 打包环境。
- **iOS**：Kivy 有 iOS 打包路径，需要 macOS、Xcode 和 kivy-ios 工具链进行构建与签名；需在目标设备上验证字体、布局和分发流程。
- **华为鸿蒙**：仅面向支持 Android APK 兼容运行的设备，实际安装与运行受系统版本及设备策略影响。此 Python/Kivy 项目不是原生 HarmonyOS/鸿蒙 NEXT 应用，也不保证鸿蒙 NEXT 兼容。

此项目提供可运行的 Kivy 源码；尚未在 Android、iOS 或鸿蒙设备上构建、签名或验证商店分发。

在 Linux/WSL 安装 Buildozer 与 Android SDK/NDK 后，可在本目录运行 `buildozer -v android debug`。生成物通常位于 `bin/`。

## 测试

数据层使用 Python 标准库，可在未安装 Kivy 的环境下运行测试：

```powershell
python -m unittest discover -s tests -v
```

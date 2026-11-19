[app]

title = 健身记录
package.name = fitnessrecord
package.domain = com.fitnessrecord
source.dir = .
source.include_exts = py,kv,png,jpg,atlas,json,ttf,otf
version = 1.0.0
requirements = python3,kivy
orientation = portrait
fullscreen = 0

android.api = 35
android.minapi = 23
android.archs = arm64-v8a, armeabi-v7a
android.accept_sdk_license = True
android.permissions = POST_NOTIFICATIONS, FOREGROUND_SERVICE, FOREGROUND_SERVICE_HEALTH, ACTIVITY_RECOGNITION, WAKE_LOCK

services = resttimer:services/rest_timer.py:foreground:sticky:foregroundServiceType=health

[buildozer]
log_level = 2
warn_on_root = 1

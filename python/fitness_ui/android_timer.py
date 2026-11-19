"""Android foreground-service and notification bridge for rest timers."""

from __future__ import annotations

import json
from typing import Any


class AndroidTimerError(RuntimeError):
    """Raised when Android timer permissions or native services are unavailable."""


SERVICE_CLASS = "com.fitnessrecord.fitnessrecord.ServiceResttimer"
NOTIFICATION_ID = 2841
NOTIFICATION_CHANNEL_ID = "fitness_rest_timer"


def request_timer_permissions() -> None:
    try:
        from jnius import JavaException, autoclass
        from android.permissions import check_permission, request_permissions
    except ImportError as error:
        raise AndroidTimerError("无法访问 Android 通知权限服务。") from error

    try:
        sdk_version = int(autoclass("android.os.Build$VERSION").SDK_INT)
        needed: list[str] = []
        if sdk_version >= 33:
            needed.append("android.permission.POST_NOTIFICATIONS")
        if sdk_version >= 34:
            needed.append("android.permission.ACTIVITY_RECOGNITION")
        missing = [permission for permission in needed if not check_permission(permission)]
        if missing:
            request_permissions(missing)
            raise AndroidTimerError(
                "请授予通知和系统要求的健身后台运行权限，然后再次启动计时。"
            )
    except JavaException as error:
        raise AndroidTimerError(f"无法检查 Android 计时权限：{error}") from error


def start_background_service(payload: dict[str, Any]) -> None:
    try:
        from jnius import JavaException, autoclass
        service_class = autoclass(SERVICE_CLASS)
        activity = autoclass("org.kivy.android.PythonActivity").mActivity
        service_class.start(
            activity,
            "icon",
            "健身休息计时",
            f"{payload['exercise']} · 倒计时运行中",
            json.dumps(payload, ensure_ascii=False),
        )
    except ImportError as error:
        raise AndroidTimerError("无法加载 Android 后台计时组件。") from error
    except JavaException as error:
        raise AndroidTimerError(f"Android 后台计时启动失败：{error}") from error


def post_completion_notification(
    title: str,
    message: str,
    *,
    service_context: Any | None = None,
) -> None:
    try:
        from jnius import JavaException, autoclass
        if service_context is None:
            service_context = autoclass("org.kivy.android.PythonActivity").mActivity
        Context = autoclass("android.content.Context")
        BuildVersion = autoclass("android.os.Build$VERSION")
        Notification = autoclass("android.app.Notification")
        NotificationBuilder = autoclass("android.app.Notification$Builder")
        NotificationManager = autoclass("android.app.NotificationManager")
        manager = service_context.getSystemService(Context.NOTIFICATION_SERVICE)

        if int(BuildVersion.SDK_INT) >= 26:
            NotificationChannel = autoclass("android.app.NotificationChannel")
            channel = NotificationChannel(
                NOTIFICATION_CHANNEL_ID,
                "训练休息计时",
                NotificationManager.IMPORTANCE_HIGH,
            )
            channel.setDescription("动作组间休息倒计时完成提醒")
            manager.createNotificationChannel(channel)
            builder = NotificationBuilder(service_context, NOTIFICATION_CHANNEL_ID)
        else:
            builder = NotificationBuilder(service_context)

        icon = int(service_context.getApplicationInfo().icon)
        if not icon:
            icon = int(autoclass("android.R$drawable").ic_lock_idle_alarm)
        builder.setSmallIcon(icon)
        builder.setContentTitle(title)
        builder.setContentText(message)
        builder.setAutoCancel(True)
        builder.setPriority(Notification.PRIORITY_HIGH)
        builder.setCategory(Notification.CATEGORY_REMINDER)
        builder.setDefaults(Notification.DEFAULT_SOUND | Notification.DEFAULT_VIBRATE)
        manager.notify(NOTIFICATION_ID, builder.build())
    except ImportError as error:
        raise AndroidTimerError("无法加载 Android 通知组件。") from error
    except JavaException as error:
        raise AndroidTimerError(f"Android 通知发送失败：{error}") from error

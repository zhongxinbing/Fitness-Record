"""Export workout data to locations users can access on each platform."""

from __future__ import annotations

import json
import logging
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

from kivy.utils import platform


LOGGER = logging.getLogger(__name__)


class ExportError(Exception):
    """Raised when an export cannot be written or shared."""


class ExportPermissionRequired(ExportError):
    """Raised when legacy Android storage permission has not been granted."""


def export_json(data: dict[str, Any], private_dir: str | Path) -> Path | str:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"fitness_record_export_{timestamp}.json"
    payload = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")

    if platform == "android":
        return _export_android(payload, filename)
    if platform == "ios":
        destination = Path(private_dir) / "exports" / filename
    else:
        destination = Path.home() / "Downloads" / filename

    _write_atomically(destination, payload)
    return destination


def share_export(path: Path) -> None:
    try:
        from pyobjus import autoclass, objc_str
    except ImportError as error:
        raise ExportError("当前 iOS 环境无法启动系统分享面板。") from error

    try:
        UIApplication = autoclass("UIApplication")
        NSURL = autoclass("NSURL")
        NSArray = autoclass("NSArray")
        activity_controller = autoclass("UIActivityViewController")
        application = UIApplication.sharedApplication()
        window = application.keyWindow()
        if window is None:
            raise ExportError("无法获取 iOS 应用窗口。")
        root_controller = window.rootViewController()
        file_url = NSURL.fileURLWithPath_(objc_str(str(path)))
        items = NSArray.arrayWithObject_(file_url)
        controller = activity_controller.alloc().initWithActivityItems_applicationActivities_(
            items,
            None,
        )
        controller.setModalPresentationStyle_(1)
        root_controller.presentViewController_animated_completion_(
            controller,
            True,
            None,
        )
    except ExportError:
        raise
    except Exception as error:
        raise ExportError("无法打开 iOS 系统分享面板。") from error


def _write_atomically(destination: Path, payload: bytes) -> None:
    temporary: Path | None = None
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=destination.parent,
            prefix=f".{destination.name}.",
            suffix=".tmp",
            delete=False,
        ) as stream:
            temporary = Path(stream.name)
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, destination)
        temporary = None
    except OSError as error:
        raise ExportError(f"无法写入导出文件：{error}") from error
    finally:
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                LOGGER.warning(
                    "Could not remove temporary export file %s",
                    temporary,
                    exc_info=True,
                )


def _export_android(payload: bytes, filename: str) -> str:
    try:
        from jnius import JavaException, autoclass
    except ImportError as error:
        raise ExportError("当前 Android 环境无法访问系统存储。") from error

    try:
        sdk_version = int(autoclass("android.os.Build$VERSION").SDK_INT)
        if sdk_version >= 29:
            return _export_android_media_store(payload, filename, autoclass)

        from android.permissions import Permission, check_permission

        if not check_permission(Permission.WRITE_EXTERNAL_STORAGE):
            raise ExportPermissionRequired("需要存储权限才能保存到下载目录。")
        downloads = autoclass("android.os.Environment").getExternalStoragePublicDirectory(
            autoclass("android.os.Environment").DIRECTORY_DOWNLOADS
        )
        destination = Path(str(downloads.getAbsolutePath())) / filename
        _write_atomically(destination, payload)
        return str(destination)
    except ExportPermissionRequired:
        raise
    except ExportError:
        raise
    except (JavaException, OSError) as error:
        raise ExportError(f"无法保存到 Android 下载目录：{error}") from error


def _export_android_media_store(payload: bytes, filename: str, autoclass: Any) -> str:
    resolver = autoclass("org.kivy.android.PythonActivity").mActivity.getContentResolver()
    media_store_downloads = autoclass("android.provider.MediaStore$Downloads")
    content_values = autoclass("android.content.ContentValues")()
    content_values.put("display_name", filename)
    content_values.put("mime_type", "application/json")
    content_values.put("relative_path", "Download/FitnessRecord")
    content_values.put("is_pending", 1)

    uri = resolver.insert(media_store_downloads.EXTERNAL_CONTENT_URI, content_values)
    if uri is None:
        raise ExportError("系统未能创建下载文件。")
    output = None
    try:
        output = resolver.openOutputStream(uri)
        if output is None:
            raise ExportError("无法打开系统下载文件。")
        java_text = autoclass("java.lang.String")(payload.decode("utf-8"))
        output.write(java_text.getBytes("UTF-8"))
        output.flush()
        output.close()
        output = None

        published_values = autoclass("android.content.ContentValues")()
        published_values.put("is_pending", 0)
        if resolver.update(uri, published_values, None, None) < 1:
            raise ExportError("系统未能完成下载文件保存。")
        return str(uri.toString())
    except Exception:
        if output is not None:
            output.close()
        resolver.delete(uri, None, None)
        raise

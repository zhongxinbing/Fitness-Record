import io
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from fitness_ui.export import export_json


class ExportTests(unittest.TestCase):
    def test_desktop_export_writes_json_to_downloads(self):
        data = {"workouts": [{"title": "胸部训练"}]}
        with tempfile.TemporaryDirectory() as temp_dir:
            home = Path(temp_dir)
            with (
                patch("fitness_ui.export.platform", "win"),
                patch("fitness_ui.export.Path.home", return_value=home),
            ):
                destination = export_json(data, home / "private")

            self.assertEqual(destination.parent, home / "Downloads")
            self.assertEqual(json.loads(destination.read_text(encoding="utf-8")), data)

    def test_ios_export_writes_a_shareable_file_in_app_storage(self):
        data = {"workouts": [{"title": "周一训练"}]}
        with tempfile.TemporaryDirectory() as temp_dir:
            app_data = Path(temp_dir)
            with patch("fitness_ui.export.platform", "ios"):
                destination = export_json(data, app_data)

            self.assertEqual(destination.parent, app_data / "exports")
            self.assertEqual(json.loads(destination.read_text(encoding="utf-8")), data)

    def test_android_export_publishes_json_in_downloads_via_media_store(self):
        class FakeContentValues:
            def __init__(self):
                self.values = {}

            def put(self, key, value):
                self.values[key] = value

        class FakeStream(io.BytesIO):
            def close(self):
                resolver.payload = self.getvalue()
                super().close()

        class FakeUri:
            def toString(self):
                return "content://downloads/export.json"

        class FakeResolver:
            def __init__(self):
                self.uri = FakeUri()
                self.payload = None
                self.inserted_values = None
                self.published_values = None

            def insert(self, _uri, values):
                self.inserted_values = values.values
                return self.uri

            def openOutputStream(self, _uri):
                return FakeStream()

            def update(self, _uri, values, _selection, _args):
                self.published_values = values.values
                return 1

            def delete(self, _uri, _selection, _args):
                return 1

        resolver = FakeResolver()

        class FakeActivity:
            def getContentResolver(self):
                return resolver

        class FakeJavaString(str):
            def getBytes(self, encoding):
                return self.encode(encoding)

        java_classes = {
            "android.os.Build$VERSION": types.SimpleNamespace(SDK_INT=33),
            "org.kivy.android.PythonActivity": types.SimpleNamespace(
                mActivity=FakeActivity()
            ),
            "android.provider.MediaStore$Downloads": types.SimpleNamespace(
                EXTERNAL_CONTENT_URI="content://downloads"
            ),
            "android.content.ContentValues": FakeContentValues,
            "java.lang.String": FakeJavaString,
        }
        jnius = types.ModuleType("jnius")
        jnius.JavaException = RuntimeError
        jnius.autoclass = lambda name: java_classes[name]

        with (
            patch("fitness_ui.export.platform", "android"),
            patch.dict(sys.modules, {"jnius": jnius}),
        ):
            result = export_json({"workouts": []}, Path("private"))

        self.assertEqual(result, "content://downloads/export.json")
        self.assertEqual(
            resolver.inserted_values["relative_path"],
            "Download/FitnessRecord",
        )
        self.assertEqual(resolver.inserted_values["is_pending"], 1)
        self.assertEqual(resolver.published_values["is_pending"], 0)
        self.assertEqual(json.loads(resolver.payload), {"workouts": []})


if __name__ == "__main__":
    unittest.main()

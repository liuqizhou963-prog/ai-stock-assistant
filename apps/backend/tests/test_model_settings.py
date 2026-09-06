import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import main


class ModelSettingsTests(unittest.TestCase):
    def test_saved_provider_setting_masks_key_and_keeps_custom_url(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            settings_path = Path(temporary_directory) / "model-settings.json"
            with patch.object(main, "MODEL_SETTINGS_PATH", settings_path):
                saved = main.save_model_provider_settings(
                    "openai",
                    api_key="sk-test-secret",
                    base_url="https://gateway.example.com/v1",
                )

                self.assertTrue(saved["configured"])
                self.assertEqual(saved["baseUrl"], "https://gateway.example.com/v1")
                self.assertEqual(saved["keyPreview"], "••••••cret")
                self.assertEqual(
                    main.openai_api_key(),
                    "sk-test-secret",
                )


if __name__ == "__main__":
    unittest.main()

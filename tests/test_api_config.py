import os
import unittest
from unittest.mock import patch

from api.main import get_minimax_token_plan_config


class ApiConfigTests(unittest.TestCase):
    def test_token_plan_config_masks_api_key_and_reports_env_source(self):
        env = {
            "LABPILOT_AI_API_KEY": "real-token-not-returned",
            "LABPILOT_AI_MODEL": "MiniMax-M2.7",
        }

        with patch.dict(os.environ, env, clear=False):
            config = get_minimax_token_plan_config()

        self.assertTrue(config.has_api_key)
        self.assertEqual(config.api_key_source, "environment")
        self.assertEqual(config.model, "MiniMax-M2.7")
        self.assertFalse(hasattr(config, "api_key"))


if __name__ == "__main__":
    unittest.main()

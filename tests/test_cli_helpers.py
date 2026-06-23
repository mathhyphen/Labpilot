"""Tests for the small helpers in cli.py (review finding B.3 + H3).

Most of cli.py is a wrapper around subprocess.Popen which is hard to
test in isolation, but the three pure helpers below carry logic that's
worth pinning:

  * ``extract_params``  — turn a CLI argv into a param string for the DB
  * ``parse_memory_str`` — parse the ``--wait-gpu 12g`` / ``10240m`` / ``any`` value
  * ``extract_ckpt_path`` — pull a checkpoint path out of a log blob
                           (review finding H3: previously truncated
                            filenames to just "checkpoint.pth")
"""

import unittest

from labpilot.cli import extract_ckpt_path, extract_params, parse_memory_str


class ParseMemoryStrTests(unittest.TestCase):
    def test_gigabytes_with_g_suffix(self):
        self.assertEqual(parse_memory_str("12g"), 12 * 1024)

    def test_gigabytes_with_gb_suffix(self):
        self.assertEqual(parse_memory_str("12gb"), 12 * 1024)

    def test_megabytes_with_m_suffix(self):
        self.assertEqual(parse_memory_str("10240m"), 10240)

    def test_megabytes_with_mb_suffix(self):
        self.assertEqual(parse_memory_str("10240mb"), 10240)

    def test_any_returns_zero(self):
        """``any`` means "any free GPU" — semantically zero threshold."""
        self.assertEqual(parse_memory_str("any"), 0)

    def test_garbage_returns_zero(self):
        self.assertEqual(parse_memory_str("not-a-number"), 0)

    def test_empty_string_returns_zero(self):
        self.assertEqual(parse_memory_str(""), 0)

    def test_case_insensitive(self):
        self.assertEqual(parse_memory_str("8G"), 8 * 1024)


class ExtractParamsTests(unittest.TestCase):
    def test_collects_flag_with_value(self):
        self.assertEqual(
            extract_params(["train.py", "--epochs", "10"]),
            "--epochs 10",
        )

    def test_collects_multiple_flags(self):
        self.assertEqual(
            extract_params(["train.py", "--epochs", "10", "--lr", "1e-4", "--batch-size", "32"]),
            "--epochs 10 --lr 1e-4 --batch-size 32",
        )

    def test_bare_flag_no_value(self):
        self.assertEqual(
            extract_params(["train.py", "--verbose"]),
            "--verbose",
        )

    def test_negative_number_value_for_long_flag(self):
        """Review finding M9: ``--lr -0.001`` must capture the
        negative number as the flag's value, not as a separate
        valueless flag."""
        self.assertEqual(
            extract_params(["train.py", "--lr", "-0.001"]),
            "--lr -0.001",
        )

    def test_negative_number_does_not_swallow_next_flag(self):
        """``--lr -0.001 --epochs 10`` — the ``--epochs 10`` pair
        must survive the negative-number disambiguation."""
        self.assertEqual(
            extract_params(["train.py", "--lr", "-0.001", "--epochs", "10"]),
            "--lr -0.001 --epochs 10",
        )

    def test_negative_number_as_value_with_another_flag_after(self):
        """A negative number immediately after a non-valued flag
        must NOT be conflated with the next flag's value."""
        self.assertEqual(
            extract_params(["train.py", "--lr", "-0.001", "--batch-size", "32"]),
            "--lr -0.001 --batch-size 32",
        )

    def test_skips_positional_args(self):
        """Positional arguments (no leading '-') are not params."""
        self.assertEqual(
            extract_params(["train.py", "data.csv", "--epochs", "10"]),
            "--epochs 10",
        )

    def test_empty_input_returns_empty_string(self):
        self.assertEqual(extract_params([]), "")


class ExtractCkptPathTests(unittest.TestCase):
    """The H3 fix: the previous implementation captured only
    ``(checkpoint, pth)`` and reassembled ``"checkpoint.pth"`` —
    throwing away the actual filename (``42``, ``final``, ``best_ema``).
    These tests pin the contract that the full path is returned.
    """

    def test_basic_checkpoint_path(self):
        log = "Saving model to /tmp/checkpoint_42.pth"
        self.assertEqual(
            extract_ckpt_path(log),
            "/tmp/checkpoint_42.pth",
        )

    def test_picks_last_match(self):
        """If the log mentions multiple checkpoints, the last one is
        typically the final saved one — that's the useful one."""
        log = "Saved checkpoint_iter_100.pth\nSaved checkpoint_iter_200.pth\nSaved final.pth"
        self.assertEqual(extract_ckpt_path(log), "final.pth")

    def test_model_extension(self):
        log = "Saved to /runs/exp1/model.bin"
        self.assertEqual(extract_ckpt_path(log), "/runs/exp1/model.bin")

    def test_safetensors_extension(self):
        log = "Saved model.safetensors"
        self.assertEqual(extract_ckpt_path(log), "model.safetensors")

    def test_no_checkpoint_returns_empty(self):
        self.assertEqual(extract_ckpt_path("just some logs, no model here"), "")

    def test_empty_log_returns_empty(self):
        self.assertEqual(extract_ckpt_path(""), "")

    def test_relative_path(self):
        log = "Saved to ./out/checkpoint_latest.pth"
        self.assertEqual(extract_ckpt_path(log), "./out/checkpoint_latest.pth")


if __name__ == "__main__":
    unittest.main()

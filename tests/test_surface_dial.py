import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch


sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

import surface_dial


class DialActionsTest(unittest.TestCase):
    def setUp(self):
        self.audio = Mock()
        self.actions = surface_dial.DialActions(
            self.audio,
            rotation_threshold=5,
            max_steps_per_batch=5,
        )

    def test_clockwise_rotation_increases_volume(self):
        self.actions.handle(
            surface_dial.InputEvent(
                surface_dial.EV_REL,
                surface_dial.REL_DIAL,
                12,
            )
        )

        self.actions.flush_rotation()

        self.audio.adjust_volume.assert_called_once_with(1, 2)

    def test_counterclockwise_rotation_decreases_volume(self):
        self.actions.handle(
            surface_dial.InputEvent(
                surface_dial.EV_REL,
                surface_dial.REL_DIAL,
                -5,
            )
        )

        self.actions.flush_rotation()

        self.audio.adjust_volume.assert_called_once_with(-1, 1)

    def test_small_rotation_is_ignored(self):
        self.actions.handle(
            surface_dial.InputEvent(
                surface_dial.EV_REL,
                surface_dial.REL_DIAL,
                4,
            )
        )

        self.actions.flush_rotation()

        self.audio.adjust_volume.assert_not_called()

    def test_large_rotation_is_capped(self):
        self.actions.handle(
            surface_dial.InputEvent(
                surface_dial.EV_REL,
                surface_dial.REL_DIAL,
                100,
            )
        )

        self.actions.flush_rotation()

        self.audio.adjust_volume.assert_called_once_with(1, 5)

    def test_press_flushes_rotation_and_toggles_mute(self):
        self.actions.handle(
            surface_dial.InputEvent(
                surface_dial.EV_REL,
                surface_dial.REL_DIAL,
                5,
            )
        )

        self.actions.handle(
            surface_dial.InputEvent(
                surface_dial.EV_KEY,
                surface_dial.BTN_0,
                1,
            )
        )

        self.audio.adjust_volume.assert_called_once_with(1, 1)
        self.audio.toggle_mute.assert_called_once_with()

    def test_release_does_not_toggle_mute(self):
        self.actions.handle(
            surface_dial.InputEvent(
                surface_dial.EV_KEY,
                surface_dial.BTN_0,
                0,
            )
        )

        self.audio.toggle_mute.assert_not_called()


class InputHandlingTest(unittest.TestCase):
    def test_decodes_linux_input_events(self):
        data = surface_dial.INPUT_EVENT.pack(
            1,
            2,
            surface_dial.EV_REL,
            surface_dial.REL_DIAL,
            -7,
        )

        events = list(surface_dial.decode_events(data))

        self.assertEqual(
            events,
            [
                surface_dial.InputEvent(
                    surface_dial.EV_REL,
                    surface_dial.REL_DIAL,
                    -7,
                )
            ],
        )

    def test_rejects_partial_input_event(self):
        with self.assertRaises(ValueError):
            list(surface_dial.decode_events(b"\0"))

    def test_discovers_multi_axis_device(self):
        with tempfile.TemporaryDirectory() as directory:
            sys_class_input = Path(directory)
            device_name = sys_class_input / "event31/device/name"
            device_name.parent.mkdir(parents=True)
            device_name.write_text(surface_dial.DEVICE_NAME)

            device = surface_dial.discover_device(sys_class_input)

        self.assertEqual(device, Path("/dev/input/event31"))


class PipeWireAudioTest(unittest.TestCase):
    @patch("surface_dial.subprocess.run")
    def test_adjusts_default_sink_volume(self, run):
        audio = surface_dial.PipeWireAudio(volume_step=2)

        audio.adjust_volume(1, 3)

        run.assert_called_once_with(
            [
                "wpctl",
                "set-volume",
                surface_dial.DEFAULT_SINK,
                "6%+",
                "--limit",
                "1.0",
            ],
            check=True,
            stdout=surface_dial.subprocess.DEVNULL,
        )

    @patch("surface_dial.subprocess.run")
    def test_toggles_default_sink_mute(self, run):
        audio = surface_dial.PipeWireAudio(volume_step=2)

        audio.toggle_mute()

        run.assert_called_once_with(
            [
                "wpctl",
                "set-mute",
                surface_dial.DEFAULT_SINK,
                "toggle",
            ],
            check=True,
            stdout=surface_dial.subprocess.DEVNULL,
        )


if __name__ == "__main__":
    unittest.main()

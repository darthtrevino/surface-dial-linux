#!/usr/bin/env python3

import argparse
import logging
import os
import select
import signal
import struct
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


DEVICE_NAME = "Surface Dial System Multi Axis"
DEFAULT_SINK = "@DEFAULT_AUDIO_SINK@"

EV_KEY = 0x01
EV_REL = 0x02
BTN_0 = 0x100
REL_DIAL = 0x07

INPUT_EVENT = struct.Struct("@llHHi")


@dataclass(frozen=True)
class InputEvent:
    event_type: int
    code: int
    value: int


class DeviceDisconnectedError(OSError):
    pass


class PipeWireAudio:
    def __init__(self, volume_step: int) -> None:
        self.volume_step = volume_step

    def adjust_volume(self, direction: int, steps: int) -> None:
        suffix = "+" if direction > 0 else "-"
        amount = f"{self.volume_step * steps}%{suffix}"
        self._run("set-volume", DEFAULT_SINK, amount, "--limit", "1.0")

    def toggle_mute(self) -> None:
        self._run("set-mute", DEFAULT_SINK, "toggle")

    @staticmethod
    def _run(*arguments: str) -> None:
        subprocess.run(
            ["wpctl", *arguments],
            check=True,
            stdout=subprocess.DEVNULL,
        )


class DialActions:
    def __init__(
        self,
        audio: PipeWireAudio,
        rotation_threshold: int,
        max_steps_per_batch: int,
    ) -> None:
        self.audio = audio
        self.rotation_threshold = rotation_threshold
        self.max_steps_per_batch = max_steps_per_batch
        self.pending_rotation = 0

    def handle(self, event: InputEvent) -> None:
        if event.event_type == EV_REL and event.code == REL_DIAL:
            self.pending_rotation += event.value
        elif (
            event.event_type == EV_KEY
            and event.code == BTN_0
            and event.value == 1
        ):
            self.flush_rotation()
            self.audio.toggle_mute()
            logging.info("Mute toggled")

    def flush_rotation(self) -> None:
        rotation = self.pending_rotation
        self.pending_rotation = 0

        steps = min(
            abs(rotation) // self.rotation_threshold,
            self.max_steps_per_batch,
        )
        if steps == 0:
            return

        direction = 1 if rotation > 0 else -1
        self.audio.adjust_volume(direction, steps)
        logging.info(
            "Volume %s by %d step(s)",
            "increased" if direction > 0 else "decreased",
            steps,
        )


def discover_device(sys_class_input: Path = Path("/sys/class/input")) -> Path | None:
    candidates: list[tuple[int, Path]] = []

    for event_path in sys_class_input.glob("event*"):
        try:
            if (event_path / "device/name").read_text().strip() != DEVICE_NAME:
                continue
            event_number = int(event_path.name.removeprefix("event"))
        except (OSError, ValueError):
            continue

        candidates.append((event_number, Path("/dev/input") / event_path.name))

    if not candidates:
        return None

    return min(candidates)[1]


def decode_events(data: bytes) -> Iterable[InputEvent]:
    if len(data) % INPUT_EVENT.size != 0:
        raise ValueError("Received a partial Linux input event")

    for _, _, event_type, code, value in INPUT_EVENT.iter_unpack(data):
        yield InputEvent(event_type, code, value)


def run_device(
    device_path: Path,
    actions: DialActions,
    batch_window: float,
    stopping: list[bool],
) -> None:
    file_descriptor = os.open(device_path, os.O_RDONLY | os.O_NONBLOCK)
    logging.info("Connected to %s", device_path)

    try:
        last_rotation_at: float | None = None

        while not stopping[0]:
            timeout = batch_window
            if last_rotation_at is not None:
                timeout = max(
                    0.0,
                    batch_window - (time.monotonic() - last_rotation_at),
                )

            readable, _, _ = select.select([file_descriptor], [], [], timeout)

            if readable:
                data = os.read(file_descriptor, INPUT_EVENT.size * 64)
                if not data:
                    raise DeviceDisconnectedError("Device was disconnected")

                for event in decode_events(data):
                    actions.handle(event)
                    if event.event_type == EV_REL and event.code == REL_DIAL:
                        last_rotation_at = time.monotonic()

            if (
                last_rotation_at is not None
                and time.monotonic() - last_rotation_at >= batch_window
            ):
                actions.flush_rotation()
                last_rotation_at = None
    finally:
        os.close(file_descriptor)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Use a Microsoft Surface Dial as a volume and mute control."
    )
    parser.add_argument(
        "--device",
        type=Path,
        help="Input event device; discovered automatically when omitted.",
    )
    parser.add_argument(
        "--volume-step",
        type=int,
        default=2,
        choices=range(1, 21),
        metavar="PERCENT",
        help="Volume change per rotation step (default: 2).",
    )
    parser.add_argument(
        "--rotation-threshold",
        type=int,
        default=5,
        choices=range(1, 101),
        metavar="EVENTS",
        help="Accumulated rotation required for one step (default: 5).",
    )
    parser.add_argument(
        "--max-steps-per-batch",
        type=int,
        default=5,
        choices=range(1, 21),
        metavar="STEPS",
        help="Maximum volume steps from one rotation burst (default: 5).",
    )
    parser.add_argument(
        "--batch-window-ms",
        type=int,
        default=50,
        choices=range(10, 501),
        metavar="MILLISECONDS",
        help="Idle time used to group rotation events (default: 50).",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable debug logging.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    stopping = [False]

    def stop(_signal_number: int, _frame: object) -> None:
        stopping[0] = True

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)

    audio = PipeWireAudio(args.volume_step)
    actions = DialActions(
        audio,
        args.rotation_threshold,
        args.max_steps_per_batch,
    )
    last_status: str | None = None

    while not stopping[0]:
        device_path = args.device or discover_device()

        if device_path is None:
            status = "Surface Dial not found; waiting for it to connect"
            if status != last_status:
                logging.info(status)
                last_status = status
            time.sleep(2)
            continue

        try:
            run_device(
                device_path,
                actions,
                args.batch_window_ms / 1000,
                stopping,
            )
            last_status = None
        except PermissionError:
            status = (
                f"Cannot read {device_path}; reconnect the Dial after running setup"
            )
            if status != last_status:
                logging.error(status)
                last_status = status
            time.sleep(2)
        except (DeviceDisconnectedError, FileNotFoundError, OSError) as error:
            logging.warning("Surface Dial unavailable: %s", error)
            last_status = None
            time.sleep(1)
        except subprocess.CalledProcessError as error:
            logging.error("wpctl failed with exit status %d", error.returncode)
            time.sleep(1)

    actions.flush_rotation()
    return 0


if __name__ == "__main__":
    sys.exit(main())

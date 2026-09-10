# Surface Dial for Linux

A dependency-free userspace controller for the Microsoft Surface Dial.

The initial release provides:

- Rotate the Dial to change the default output volume.
- Press the Dial to toggle mute.
- Automatic Bluetooth reconnect handling.
- Automatic discovery without a hard-coded `/dev/input/event*` number.
- A systemd user service and narrowly scoped udev access rule.

The daemon reads standard Linux input events directly and uses PipeWire's
installed `wpctl` command. It does not require a Python input library.

## Ubuntu installation

Pair and trust the Surface Dial in Ubuntu's Bluetooth settings, then run:

```bash
./setup.sh
```

The setup script installs the daemon for the current user, adds a udev rule
using `sudo`, and enables the systemd user service. Do not run the entire setup
script with `sudo`.

If the Dial was connected during installation and the service cannot read it,
disconnect and reconnect the Dial once.

View logs with:

```bash
journalctl --user -u surface-dial.service -f
```

Remove the installation with:

```bash
./setup.sh uninstall
```

## Manual use

Run directly from the repository:

```bash
python3 src/surface_dial.py
```

Useful options:

```text
--volume-step PERCENT
--rotation-threshold EVENTS
--max-steps-per-batch STEPS
--batch-window-ms MILLISECONDS
--device /dev/input/eventN
--verbose
```

The defaults group the Dial's high-frequency rotation events into short bursts,
change volume by 2% per threshold, and limit one burst to a 10% change.

## Development

Run the dependency-free test suite with:

```bash
python3 -m unittest discover -s tests -v
```

Planned future work includes configurable actions, haptic feedback, application
profiles, additional gestures, and a graphical configuration interface.

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE).

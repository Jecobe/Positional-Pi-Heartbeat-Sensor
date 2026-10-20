# Setup guide

This guide goes from a bag of parts to a pulsing dot in your browser. Plan on
about an hour.

## 1. Parts

- A Raspberry Pi (3, 4 or 5) and its power supply
- **Seeed Studio MR60BHA2 60 GHz mmWave Breathing and Heartbeat kit**. It comes
  with a XIAO ESP32C6 already attached. It's sold by Seeed Studio and electronics
  distributors such as Mouser and Digi-Key.
- A **microSD card** (16–32 GB, A1 or A2 rated). The setup erases it, so use a
  spare card if your Pi already has a system you want to keep.
- A **USB-A to USB-C data cable** to connect the radar kit to the Pi.

## 2. Prepare the microSD card

1. On your computer, install [Raspberry Pi Imager](https://www.raspberrypi.com/software/).
2. Choose your Pi model, then **Raspberry Pi OS (other) → Raspberry Pi OS Lite (64-bit)**,
   then your card.
3. When it asks about OS customisation, click **Edit settings** and set:
   - hostname: `heartbeat` (the UI will then be at `http://heartbeat.local:8000`)
   - a username and password
   - your Wi-Fi name and password, and your country
   - on the **Services** tab: **Enable SSH**
4. Write the card, put it in the Pi and power it on. The first boot takes a couple of minutes.
5. From your computer, connect with `ssh <your-username>@heartbeat.local`.

## 3. Flash the bridge firmware onto the radar kit

The kit ships with ESPHome firmware for Home Assistant. That firmware doesn't
expose people's x/y positions, so we replace it with a small sketch that forwards
the radar's raw data over USB. Do this from your regular computer:

1. Install the [Arduino IDE 2](https://www.arduino.cc/en/software).
2. Go to **File → Preferences → Additional boards manager URLs** and add:
   `https://espressif.github.io/arduino-esp32/package_esp32_index.json`
3. In **Tools → Board → Boards Manager**, install **esp32 by Espressif Systems** (version 3.x).
4. Open `firmware/mr60bha2_usb_bridge/mr60bha2_usb_bridge.ino` from this repo.
5. Set **Tools → Board → esp32 → XIAO_ESP32C6**.
6. Set **Tools → USB CDC On Boot → Enabled**. If you skip this, the Pi won't see any data.
7. Plug the kit into your computer, select its port under **Tools → Port**, and click **Upload**.
   - If the upload fails, unplug the kit, hold the small **B** (boot) button on
     the XIAO, plug it back in, release the button, and upload again.

> To go back to the original ESPHome firmware, use the web flasher linked from
> Seeed's [MR60BHA2 wiki page](https://wiki.seeedstudio.com/getting_started_with_mr60bha2_mmwave_kit/).

## 4. Install the software on the Pi

Plug the radar kit into one of the Pi's USB ports, then over SSH run:

```bash
sudo apt-get update && sudo apt-get install -y git
git clone https://github.com/Jecobe/Positional-Pi-Heartbeat-Sensor.git
cd Positional-Pi-Heartbeat-Sensor
./scripts/install.sh
```

The installer does four things:

- creates a Python virtualenv in `.venv`
- gives your user access to serial ports
- installs a systemd service so the app starts on every boot
- starts the app

Then open **http://heartbeat.local:8000** on your phone or computer. Use the
hostname you picked in step 2 if it's different.

### Optional: show it on an attached display

If a display is connected to the Pi, the installer can make it show the radar
full screen on boot, the same view as the web UI:

```bash
./scripts/install.sh --display
sudo reboot
```

How it works: a small kiosk program ([cage](https://github.com/cage-kiosk/cage))
runs Chromium full screen on the Pi's first screen, pointed at the local web UI.
There's no desktop, no mouse cursor and nothing else on screen.

- Works with HDMI displays, the official Raspberry Pi touch displays, and other
  displays the Pi supports out of the box.
- Small screens are supported. The layout adapts down to 480×320.
- It uses about 300–400 MB of RAM, so a Pi with 2 GB or more is comfortable.
  A 1 GB Pi will work but is tight.
- It's meant for **Raspberry Pi OS Lite**. On the desktop version, the radar
  display takes over the first screen instead of the desktop.
- To turn it off again: `./scripts/install.sh --no-display`
- Logs: `journalctl -u heartbeat-display -f`

## 5. Check that the radar is talking

Stop the service so you can read the port directly, then dump the decoded frames:

```bash
sudo systemctl stop heartbeat-radar
.venv/bin/heartbeat-radar dump
```

Sit about 1 m in front of the sensor. You should see lines like:

```
    3.12s 0x0A04 target_info     Targets(targets=(Target(x=0.21, y=0.95, ...),))
    3.40s 0x0A15 heart_rate      HeartRate(bpm=71.0)
```

Press Ctrl+C when you're done, then run `sudo systemctl start heartbeat-radar`.

- **Nothing at all?** Run `ls /dev/ttyACM*`. If nothing is listed, try another
  cable (some are charge-only). If it's listed but no frames show up, re-flash the
  bridge and check that **USB CDC On Boot** is set to Enabled.
- **Heart rate but no `target_info` lines?** Seeed says position reporting
  needs recent radar firmware. Update the radar module's firmware using Seeed's
  wiki, then try again.
- **`unknown` frame types?** These are printed in hex. Please open an issue with
  the output so the decoder can be extended.

## 6. Placement tips

- Point the sensor at where people sit or lie, with nothing metal in front of
  it. Thin plastic or fabric is fine.
- For heart rate, the person needs to be within about 1.5 m and fairly still.
  Breathing is easier to pick up than heartbeat.
- Mounting it about chest height, aimed slightly down, works well for a desk or couch.
- Fans, curtains moving in a draft, and pets can all show up as people.

## 7. Calibrate the map

Walk around in front of the sensor and watch the dot:

| What you see | Fix |
|---|---|
| Walking left moves the dot right | `--flip-x` |
| Walking toward the sensor moves the dot sideways | `--swap-xy` |
| Walking away moves the dot toward the sensor | `--flip-y` |
| Everything is bunched up near the sensor | `--max-range 3` |

Put the flags in `/etc/default/heartbeat-radar`:

```bash
sudo nano /etc/default/heartbeat-radar   # e.g. HEARTBEAT_RADAR_ARGS="--flip-x"
sudo systemctl restart heartbeat-radar
```

## Useful commands

```bash
journalctl -u heartbeat-radar -f       # live logs
sudo systemctl restart heartbeat-radar # restart after changing options
cd ~/Positional-Pi-Heartbeat-Sensor && git pull && ./scripts/install.sh   # update
```

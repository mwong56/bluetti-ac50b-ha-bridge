# BLUETTI AC50B to Home Assistant

Monitor an AC50B using a Windows PC's Bluetooth, then send readings to Home Assistant over its REST API. This runs on the Windows host, so a Home Assistant VM does not need Bluetooth passthrough or a proxy.

- Reports battery percentage, AC input, AC output, DC output and total output every 30 seconds. Confirmed on one AC50B using encrypted Bluetooth.
- Estimates AC input and output energy in kWh from power samples. Saves totals across restarts and skips gaps longer than 90 seconds rather than guessing usage.
- Adds ordinary sensor states, not a Home Assistant integration or device-registry entry. It sends no commands to the power station.

## Setup

Use Windows with Bluetooth enabled, Python 3.12 and an AC50B within range. Create a virtual environment and install `requirements.txt`, then copy `config.example.json` to `config.json`.

1. Set `ha_url` and your AC50B's `bluetooth_address` in `config.json`. The library's `bluetti-scan` command can find the address.
2. Save a Home Assistant long-lived access token in `ha-token.txt`, or set the Windows environment variable `HA_ACCESS_TOKEN`. These files are excluded from Git.
3. Run `.venv\Scripts\python.exe bridge.py --once` to verify one read and publish it to Home Assistant.
4. Run `.venv\Scripts\python.exe bridge.py` for continuous monitoring. Optionally run `install-startup.ps1` to start it now and whenever you sign into Windows.

The script can also read a literal `HA_ACCESS_TOKEN` assignment from a bashrc file: remove `token_file` from the config and set `bashrc_path` to that file's Windows-accessible path. It reads the assignment without executing the shell file. Environment-variable authentication takes precedence.

## Sensors and history

Sensors use the prefix `sensor.bluetti_ac50b_`: `battery`, `ac_input`, `ac_output`, `dc_output`, `output_total`, `ac_input_energy` and `output_energy`.

- In Home Assistant's Energy configuration, select **Output energy** under individual devices to track connected loads. Use **Total output** as its power sensor if offered.
- A statistics graph with statistic type **change**, period **hour** and chart type **bar** shows hourly energy use. Compare `ac_input_energy` with `output_energy` for energy entering from AC versus energy delivered to loads.
- Output includes AC passthrough and DC loads; it is not a measurement of battery discharge alone. Solar/DC input is not reported by this bridge.

Home Assistant records history once readings arrive. Energy charts need time to accumulate statistics.

## Operation

The PC must remain awake, in Bluetooth range and able to reach Home Assistant. Using a bashrc file in WSL also requires that file to remain accessible. A phone app connection may interfere with Bluetooth polling.

Failed reads mark sensors unavailable when Home Assistant is reachable. If Windows powers off or the process is killed, the last reading can remain visible until the bridge runs again; Home Assistant does not independently expire these REST states.

Check `bridge.log` for status. Keep `energy-totals.json` to retain the local counters. API token revocation or changing the Home Assistant URL requires updating the local configuration and restarting the process.

To stop monitoring, stop the **Bluetti AC50B to Home Assistant** task in Windows Task Scheduler. Disable or delete that task to prevent startup; the script and configuration can then be removed separately.

## Validation

Run the tests with `.venv\Scripts\python.exe -m unittest discover -s tests`. Hardware testing covered Bluetooth discovery, encrypted reads, publishing sensor states and persistent background polling on Windows 11 with Python 3.12.

Uses [bluetti-bt-lib](https://github.com/Patrick762/bluetti-bt-lib) for Bluetooth communication and [Home Assistant's REST API](https://developers.home-assistant.io/docs/api/rest/). This project is not affiliated with BLUETTI or Home Assistant.

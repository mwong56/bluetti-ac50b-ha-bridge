"""Read an AC50B over Windows BLE and publish monitoring sensors to HA."""

import argparse
import asyncio
from decimal import Decimal
import json
import logging
from logging.handlers import RotatingFileHandler
import math
import os
from pathlib import Path
import re
import shlex
import time

import aiohttp
from bluetti_bt_lib.bluetooth.device_reader import DeviceReader, DeviceReaderConfig
from bluetti_bt_lib.fields import FieldName
from bluetti_bt_lib.utils.device_builder import build_device

ROOT = Path(__file__).resolve().parent
STATE_FILE = ROOT / "energy-totals.json"
SENSORS = {
    "battery": ("Battery", "%", "battery", "measurement"),
    "ac_input": ("AC input", "W", "power", "measurement"),
    "ac_output": ("AC output", "W", "power", "measurement"),
    "dc_output": ("DC output", "W", "power", "measurement"),
    "output_total": ("Total output", "W", "power", "measurement"),
    "ac_input_energy": ("AC input energy", "kWh", "energy", "total_increasing"),
    "output_energy": ("Output energy", "kWh", "energy", "total_increasing"),
}


def energy_increment(previous_watts, elapsed):
    """Use the previous reading, without guessing across missing samples."""
    return previous_watts * elapsed / 3600000 if 0 < elapsed <= 90 else 0


def load_token(config):
    if token := os.environ.get("HA_ACCESS_TOKEN", "").strip():
        return token
    if config.get("token_file"):
        path = Path(config["token_file"])
        if not path.is_absolute():
            path = ROOT / path
        token = path.read_text().strip()
        if not token:
            raise RuntimeError("Token file is empty")
        return token
    if not config.get("bashrc_path"):
        raise RuntimeError("Set HA_ACCESS_TOKEN, token_file, or bashrc_path")
    path = Path(config["bashrc_path"])
    match = re.search(
        r"^\s*(?:export\s+)?HA_ACCESS_TOKEN\s*=\s*(.+)$", path.read_text(), re.M
    )
    if match is None:
        raise RuntimeError("HA_ACCESS_TOKEN was not found")
    return shlex.split(match[1], comments=True)[0]


async def run(once=False):
    import msvcrt

    config = json.loads((ROOT / "config.json").read_text())
    base = config["ha_url"].rstrip("/")
    address = config["bluetooth_address"]
    if not base.startswith(("http://", "https://")):
        raise RuntimeError("ha_url must start with http:// or https://")
    if not re.fullmatch(r"(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}", address):
        raise RuntimeError("Invalid Bluetooth address")
    lock = (ROOT / "bridge.lock").open("a+b")
    lock.seek(0)
    msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
    token = load_token(config)
    totals = (
        json.loads(STATE_FILE.read_text())
        if STATE_FILE.exists()
        else {"ac_input_energy": 0.0, "output_energy": 0.0}
    )
    if any(not math.isfinite(value) or value < 0 for value in totals.values()):
        raise RuntimeError("Invalid saved energy totals")
    previous = None
    reader = DeviceReader(
        address,
        build_device("AC50B12345678"),
        asyncio.Future,
        DeviceReaderConfig(timeout=35, use_encryption=True),
    )
    headers = {"Authorization": "Bearer " + token}
    timeout = aiohttp.ClientTimeout(total=15)
    async with aiohttp.ClientSession(headers=headers, timeout=timeout) as session:

        async def publish(key, state):
            name, unit, device_class, state_class = SENSORS[key]
            attributes = {
                "friendly_name": "BLUETTI AC50B " + name,
                "unit_of_measurement": unit,
                "device_class": device_class,
                "state_class": state_class,
            }
            async with session.post(
                base + "/api/states/sensor.bluetti_ac50b_" + key,
                json={"state": state, "attributes": attributes},
            ) as response:
                response.raise_for_status()
                await response.read()

        # Recover existing HA counters if the local state file was moved or lost.
        for key in ("ac_input_energy", "output_energy"):
            async with session.get(
                base + "/api/states/sensor.bluetti_ac50b_" + key
            ) as response:
                if response.status == 200:
                    state = (await response.json())["state"]
                    try:
                        value = float(state)
                        if math.isfinite(value) and value >= 0:
                            totals[key] = max(totals[key], value)
                    except ValueError:
                        pass
                elif response.status != 404:
                    response.raise_for_status()
        while True:
            started = time.monotonic()
            try:
                data = await reader.read()
                if not data:
                    raise RuntimeError("No Bluetooth readings received")
                fields = {
                    "battery": FieldName.BATTERY_SOC,
                    "ac_input": FieldName.AC_INPUT_POWER,
                    "ac_output": FieldName.AC_OUTPUT_POWER,
                    "dc_output": FieldName.DC_OUTPUT_POWER,
                }
                values = {}
                for name, field in fields.items():
                    value = data.get(field.value)
                    if not isinstance(
                        value, (int, float, Decimal)
                    ) or not math.isfinite(float(value)):
                        raise RuntimeError("Missing or invalid reading: " + name)
                    values[name] = float(value)
                if not 0 <= values["battery"] <= 100 or any(
                    values[name] < 0 for name in fields if name != "battery"
                ):
                    raise RuntimeError("Readings outside valid range")
                values["output_total"] = values["ac_output"] + values["dc_output"]
                now = time.monotonic()
                if previous is not None:
                    elapsed = now - previous["time"]
                    totals["ac_input_energy"] += energy_increment(
                        previous["ac_input"], elapsed
                    )
                    totals["output_energy"] += energy_increment(
                        previous["output_total"], elapsed
                    )
                previous = dict(values, time=now)
                temporary = STATE_FILE.with_suffix(".tmp")
                temporary.write_text(json.dumps(totals))
                temporary.replace(STATE_FILE)
                for key, state in (values | totals).items():
                    await publish(key, round(state, 6))
                logging.info(
                    "Battery %.0f%%; input %.0f W; AC output %.0f W; DC output %.0f W",
                    values["battery"],
                    values["ac_input"],
                    values["ac_output"],
                    values["dc_output"],
                )
                if once:
                    print(json.dumps(values | totals))
                    return
            except Exception as error:
                previous = None
                logging.warning(
                    "Reading or publishing failed (%s)", type(error).__name__
                )
                for key in SENSORS:
                    try:
                        await publish(key, "unavailable")
                    except Exception:
                        pass
                if once:
                    raise RuntimeError("Bridge test failed; see bridge.log") from None
            await asyncio.sleep(max(1, 30 - (time.monotonic() - started)))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    handler = RotatingFileHandler(ROOT / "bridge.log", maxBytes=1000000, backupCount=2)
    logging.basicConfig(
        level=logging.INFO,
        handlers=[handler],
        format="%(asctime)s %(levelname)s %(message)s",
    )
    logging.getLogger("bluetti_bt_lib").setLevel(logging.WARNING)
    asyncio.run(run(args.once))

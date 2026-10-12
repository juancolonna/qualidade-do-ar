import json
import os
import sys
import time
from pathlib import Path

import requests


API_KEY = os.environ.get("PURPLEAIR_API_KEY")
BASE_URL = "https://api.purpleair.com/v1"
SENSORS_FILE = Path(__file__).with_name("sensors.json")

# Limites geográficos da região de Manaus.
# Ajuste estes valores caso queira ampliar ou reduzir a área consultada.
NW_LAT = -2.90
NW_LON = -61.00
SE_LAT = -3.15
SE_LON = -59.90

ONLINE_WINDOW_SECONDS = 30 * 60
TIMEOUT_SECONDS = 120


def fetch_sensors():
    """Consulta os sensores externos na região configurada."""

    response = requests.get(
        f"{BASE_URL}/sensors",
        headers={"X-API-Key": API_KEY},
        params={
            "fields": "sensor_index,name,latitude,longitude,last_seen",
            "location_type": 0,
            "nwlat": NW_LAT,
            "nwlng": NW_LON,
            "selat": SE_LAT,
            "selng": SE_LON,
        },
        timeout=TIMEOUT_SECONDS,
    )
    response.raise_for_status()

    payload = response.json()
    fields = payload.get("fields")
    rows = payload.get("data")

    return fields, rows


def main():
    try:
        fields, rows = fetch_sensors()

        now = int(time.time())
        selected = []

        for row in rows:
            sensor = dict(zip(fields, row))
            last_seen = sensor["last_seen"]
            if last_seen is not None:
                age = now - int(last_seen)

                if age < ONLINE_WINDOW_SECONDS:
                    selected.append({
                        "id": sensor["sensor_index"],
                        "name": sensor["name"],
                        "lat": sensor["latitude"],
                        "lon": sensor["longitude"],
                    })

        selected.sort(key=lambda sensor: str(sensor["id"]))

        SENSORS_FILE.write_text(
            json.dumps(selected, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

        print(f"sensors.json atualizado: {len(selected)} sensores online.")

    except (requests.RequestException, ValueError, RuntimeError, KeyError, TypeError, OSError) as error:
        print(f"Erro ao atualizar sensors.json: {error}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

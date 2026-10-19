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
NW_LAT = -2.970470
NW_LON = -60.106201
SE_LAT = -3.168626
SE_LON = -59.841499

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
        timeout=240,
    )
    response.raise_for_status()

    payload = response.json()
    fields = payload.get("fields")
    rows = payload.get("data")

    return fields, rows


def main():
    try:
        fields, rows = fetch_sensors()
        selected = []

        for row in rows:
            sensor = dict(zip(fields, row))
            selected.append({
                "id": sensor["sensor_index"],
                "name": sensor["name"],
                "lat": sensor["latitude"],
                "lon": sensor["longitude"],
            })

        # Carrega os sensores já registrados, sem removê-los.
        if SENSORS_FILE.exists():
            existing = json.loads(SENSORS_FILE.read_text(encoding="utf-8"))
            if not isinstance(existing, list):
                raise ValueError("sensors.json deve conter uma lista de sensores.")
        else:
            existing = []

        # Usa o ID para evitar duplicatas e acrescentar somente sensores novos.
        existing_ids = {str(sensor["id"]) for sensor in existing}
        added = 0

        for sensor in selected:
            if str(sensor["id"]) not in existing_ids:
                existing.append(sensor)
                existing_ids.add(str(sensor["id"]))
                added += 1

        existing.sort(key=lambda sensor: str(sensor["id"]))

        SENSORS_FILE.write_text(
            json.dumps(existing, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

        print(
            f"sensors.json atualizado: {len(existing)} sensores no total; "
            f"{added} novos adicionados."
        )

    except (requests.RequestException, ValueError, RuntimeError, KeyError, TypeError, OSError) as error:
        print(f"Erro ao atualizar sensors.json: {error}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

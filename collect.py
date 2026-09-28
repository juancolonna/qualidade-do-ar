import os
import time
import json
import statistics
import requests

from datetime import datetime
from zoneinfo import ZoneInfo


# ============================================================
# Configuration
# ============================================================

API_KEY = os.environ["PURPLEAIR_API_KEY"]

BASE_URL = "https://api.purpleair.com/v1"

SENSORS = [
    {"id": 31509, "name": "UEA-EST", "lat": -3.091649, "lon": -60.017590},
    {"id": 315615, "name": "MIT_NAMA_UFAM", "lat": -3.089241, "lon": -59.964367},
    {"id": 98395, "name": "FAS-Ar", "lat": -3.074871, "lon": -60.008675},
    {"id": 161259, "name": "UEA_EDUCAIR_2", "lat": -3.131549, "lon": -60.004080},
    {"id": 161261, "name": "UEA_EducAIR_1", "lat": -3.130093, "lon": -60.026802},
    {"id": 161279, "name": "UEA_EducAIR_5", "lat": -3.096909, "lon": -59.969593},
    {"id": 161291, "name": "UEA_EducAIR_6", "lat": -3.128212, "lon": -59.986780},
# {"id": 165047, "name": "UEA_EducAIR_14", "lat": -3.073211, "lon": -59.993156},
    {"id": 165131, "name": "UEA_EducAIR_17", "lat": -3.022957, "lon": -60.055220},
    {"id": 177605, "name": "UEA_EducAIR_26", "lat": -3.079295, "lon": -59.933380},
    {"id": 181801, "name": "UEA_EducAIR_31", "lat": -3.103645, "lon": -60.049440},
    {"id": 181825, "name": "UEA_EducAIR_32", "lat": -3.112573, "lon": -60.011880},
    {"id": 205957, "name": "SEMA_MANAUS", "lat": -3.082140, "lon": -60.023293},
]


# ============================================================
# PurpleAir API
# ============================================================

def get_sensor_data(sensor_index):
    """Obtém as informações atuais do sensor."""

    url = f"{BASE_URL}/sensors/{sensor_index}"

    headers = {
        "X-API-Key": API_KEY
    }

    params = {
        "fields": "sensor_index,name,last_seen"
    }

    response = requests.get(
        url,
        headers=headers,
        params=params,
        timeout=30
    )

    response.raise_for_status()

    return response.json()["sensor"]


def get_sensor_history(sensor_index, start_timestamp, end_timestamp):
    """Obtém o histórico horário de PM2.5 do sensor."""

    url = f"{BASE_URL}/sensors/{sensor_index}/history"

    headers = {
        "X-API-Key": API_KEY
    }

    params = {
        "start_timestamp": start_timestamp,
        "end_timestamp": end_timestamp,
        "average": 60,
        "fields": "pm2.5_atm"
    }

    response = requests.get(
        url,
        headers=headers,
        params=params,
        timeout=30
    )

    response.raise_for_status()

    return response.json()


# ============================================================
# Time interval
# ============================================================

now = int(time.time())

# Início da hora atual
current_hour = now - (now % 3600)

# Última hora completa
start_timestamp = current_hour - 3600
end_timestamp = current_hour


# ============================================================
# Collect data
# ============================================================

pm25_values = []
sensor_results = []

for sensor in SENSORS:

    sensor_index = sensor["id"]
    sensor_name = sensor["name"]

    print(f"Consultando {sensor_name} ({sensor_index})...")

    # --------------------------------------------------------
    # 1. Consulta informações atuais do sensor
    # --------------------------------------------------------

    try:

        info = get_sensor_data(sensor_index)

    except requests.RequestException as e:

        print(
            f"  Erro ao consultar API para "
            f"{sensor_name}: {e}"
        )

        continue

    # --------------------------------------------------------
    # 2. Verifica se o sensor está online
    # --------------------------------------------------------

    last_seen = info["last_seen"]

    online = (
        last_seen is not None
        and now - last_seen <= 3600
    )

    if not online:

        print("  Sensor offline.")

        sensor_results.append({
            "id": sensor_index,
            "name": sensor_name,
            "lat": sensor["lat"],
            "lon": sensor["lon"],
            "online": False,
            "pm2_5": None
        })

        continue

    print("  Sensor online.")

    # --------------------------------------------------------
    # 3. Consulta histórico
    # --------------------------------------------------------

    try:

        history = get_sensor_history(
            sensor_index,
            start_timestamp,
            end_timestamp
        )

    except requests.RequestException as e:

        print(
            f"  Erro ao consultar histórico "
            f"de {sensor_name}: {e}"
        )

        continue

    # --------------------------------------------------------
    # 4. Extrai os dados retornados pela API
    # --------------------------------------------------------

    fields = history["fields"]
    data = history["data"]

    timestamp_index = fields.index("time_stamp")
    pm25_index = fields.index("pm2.5_atm")

    # --------------------------------------------------------
    # 5. Ordena os dados por timestamp
    # --------------------------------------------------------

    data.sort(
        key=lambda row: row[timestamp_index]
    )

    # --------------------------------------------------------
    # 6. Obtém o último valor disponível no intervalo
    # --------------------------------------------------------

    pm25 = None

    for row in data:

        value = row[pm25_index]

        if value is not None:
            pm25 = value

    # --------------------------------------------------------
    # 7. Armazena resultado do sensor
    # --------------------------------------------------------

    sensor_results.append({
        "id": sensor_index,
        "name": sensor_name,
        "lat": sensor["lat"],
        "lon": sensor["lon"],
        "online": True,
        "pm2_5": pm25
    })

    if pm25 is not None:

        pm25_values.append(pm25)

        print(
            f"  PM2.5: {pm25:.1f} µg/m³"
        )

    else:

        print(
            "  Nenhum valor de PM2.5 disponível."
        )


# ============================================================
# Statistics
# ============================================================

number_online = sum(
    1
    for sensor in sensor_results
    if sensor["online"]
)

if pm25_values:

    pm25_mean = statistics.mean(pm25_values)

else:

    pm25_mean = None


# Critical values of the two-sided t-Student distribution
# for a 95% confidence interval, with the available sample
# sizes (n = 1 to 12 sensors).
T_CRITICAL_95 = {
    1: None,
    2: 12.706,
    3: 4.303,
    4: 3.182,
    5: 2.776,
    6: 2.571,
    7: 2.447,
    8: 2.365,
    9: 2.306,
    10: 2.262,
    11: 2.228,
    12: 2.201,
}

if pm25_mean is not None and number_online >= 2:

    pm25_std = statistics.stdev(pm25_values)
    t_critical = T_CRITICAL_95[number_online]
    standard_error = pm25_std / (number_online ** 0.5)
    margin_of_error = t_critical * standard_error

    pm25_ci95_lower = pm25_mean - margin_of_error
    pm25_ci95_upper = pm25_mean + margin_of_error

else:

    pm25_ci95_lower = None
    pm25_ci95_upper = None


# ============================================================
# Manaus timezone
# ============================================================

manaus_tz = ZoneInfo("America/Manaus")

period_start = datetime.fromtimestamp(
    start_timestamp,
    tz=manaus_tz
).strftime("%d/%m/%Y %H:%M")

period_end = datetime.fromtimestamp(
    end_timestamp,
    tz=manaus_tz
).strftime("%d/%m/%Y %H:%M")

updated_at = datetime.now(
    manaus_tz
).strftime("%d/%m/%Y %H:%M")


# ============================================================
# Output
# ============================================================

result = {
    "updated_at": updated_at,
    "period_start": period_start,
    "period_end": period_end,

    "number_of_sensors": len(SENSORS),
    "number_online": number_online,

    "pm2_5_mean": (
        round(pm25_mean, 2)
        if pm25_mean is not None
        else None
    ),

    "pm2_5_ci95_lower": (
        round(pm25_ci95_lower, 2)
        if pm25_ci95_lower is not None
        else None
    ),

    "pm2_5_ci95_upper": (
        round(pm25_ci95_upper, 2)
        if pm25_ci95_upper is not None
        else None
    ),

    "sensors": sensor_results
}


# ============================================================
# Save JSON
# ============================================================

with open("data.json", "w", encoding="utf-8") as f:

    json.dump(
        result,
        f,
        ensure_ascii=False,
        indent=2
    )


# ============================================================
# Summary
# ============================================================

print()
print("========================================")
print("Coleta concluída")
print("========================================")
print(f"Período: {period_start} - {period_end}")
print(f"Sensores online: {number_online}/{len(SENSORS)}")
print(f"PM2.5 médio: {pm25_mean}")
print(f"IC 95%: {pm25_ci95_lower} - {pm25_ci95_upper}")
print("========================================")
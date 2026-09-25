import os
import time
import json
import statistics
import requests
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

# ============================================================
# CONFIGURAÇÃO
# ============================================================

API_URL = "https://api.purpleair.com/v1"

SENSORS = [
    {"sensor_index": 31509, "name": "UEA-EST"},
    {"sensor_index": 315615, "name": "MIT_NAMA_UFAM"},
    {"sensor_index": 98395, "name": "FAS-Ar"},
    {"sensor_index": 161259, "name": "UEA_EDUCAIR_2"},
    {"sensor_index": 161261, "name": "UEA_EducAIR_1"},
    {"sensor_index": 161279, "name": "UEA_EducAIR_5"},
    {"sensor_index": 161291, "name": "UEA_EducAIR_6"},
    {"sensor_index": 165047, "name": "UEA_EducAIR_14"},
    {"sensor_index": 165131, "name": "UEA_EducAIR_17"},
    {"sensor_index": 177605, "name": "UEA_EducAIR_26"},
    {"sensor_index": 181801, "name": "UEA_EducAIR_31"},
    {"sensor_index": 181825, "name": "UEA_EducAIR_32"},
    {"sensor_index": 205957, "name": "SEMA_MANAUS"},
]

API_KEY = os.environ["PURPLEAIR_API_KEY"]

HEADERS = { "X-API-Key": API_KEY }

# ============================================================
# FUNÇÕES
# ============================================================

def get_sensor_data(sensor_index):
    """Obtém o estado atual do sensor."""

    url = f"{API_URL}/sensors/{sensor_index}"

    params = { "fields": "sensor_index,name,last_seen" }

    response = requests.get(
        url,
        headers=HEADERS,
        params=params,
        timeout=30
    )

    response.raise_for_status()

    return response.json()["sensor"]


def get_sensor_history(sensor_index, start_timestamp, end_timestamp):
    """Obtém o PM2.5 médio da última hora."""

    url = f"{API_URL}/sensors/{sensor_index}/history"

    params = {
        "start_timestamp": start_timestamp,
        "end_timestamp": end_timestamp,
        "average": 60,
        "fields": "pm2.5_atm"
    }

    response = requests.get(
        url,
        headers=HEADERS,
        params=params,
        timeout=30
    )

    response.raise_for_status()

    return response.json()


# ============================================================
# COLETA
# ============================================================

now = int(time.time())
one_hour_ago = now - 3600

sensor_results = []
pm25_values = []

last_reading_timestamp = None

for sensor_info in SENSORS:

    sensor_index = sensor_info["sensor_index"]
    name = sensor_info["name"]

    try:

        # ----------------------------------------------------
        # 1. Verifica quando o sensor foi visto pela última vez
        # ----------------------------------------------------

        sensor = get_sensor_data(sensor_index)

        last_seen = sensor.get("last_seen")

        if last_seen is None:
            online = False
        else:
            online = (now - last_seen) <= 3600

        result = {
            "sensor_index": sensor_index,
            "name": name,
            "online": online,
            "pm2_5": None
        }

        # ----------------------------------------------------
        # 2. Se estiver online, pega o histórico da última hora
        # ----------------------------------------------------

        if online:

            history = get_sensor_history(
                sensor_index,
                one_hour_ago,
                now
            )

            data = history.get("data", [])
            fields = history.get("fields", [])

            if data and "time_stamp" in fields and "pm2.5_atm" in fields:

                time_index = fields.index("time_stamp")
                pm_index = fields.index("pm2.5_atm")

                # Ordena as leituras pelo horário
                data.sort(key=lambda row: row[time_index])

                # Última leitura disponível
                last_row = data[-1]

                reading_timestamp = last_row[time_index]
                pm25 = last_row[pm_index]

                if pm25 is not None:

                    pm25 = float(pm25)

                    result["pm2_5"] = round(pm25, 2)

                    pm25_values.append(pm25)

                    # Guarda o horário mais recente entre
                    # todos os sensores utilizados
                    if (
                        last_reading_timestamp is None
                        or reading_timestamp > last_reading_timestamp
                    ):
                        last_reading_timestamp = reading_timestamp

        sensor_results.append(result)

    except Exception as e:

        print(
            f"Erro no sensor {sensor_index} ({name}): {e}"
        )

        sensor_results.append({
            "sensor_index": sensor_index,
            "name": name,
            "online": False,
            "pm2_5": None
        })


# ============================================================
# ESTATÍSTICAS
# ============================================================

if pm25_values:

    pm25_mean = statistics.mean(pm25_values)
    pm25_std = statistics.pstdev(pm25_values)

else:

    pm25_mean = None
    pm25_std = None


# ============================================================
# HORÁRIOS
# ============================================================

manaus_tz = ZoneInfo("America/Manaus")

if last_reading_timestamp is not None:

    last_reading_datetime = datetime.fromtimestamp(
        last_reading_timestamp,
        tz=manaus_tz
    ).strftime("%d/%m/%Y %H:%M")

else:

    last_reading_datetime = None

update_datetime = datetime.now(manaus_tz).strftime("%d/%m/%Y %H:%M UTC")


# ============================================================
# RESULTADO
# ============================================================

result = {

    "updated_at": update_datetime,

    "last_reading": last_reading_datetime,

    "number_of_sensors": len(SENSORS),

    "number_online": sum(
        1 for sensor in sensor_results
        if sensor["online"] and sensor["pm2_5"] is not None
    ),

    "pm2_5_mean": (
        round(pm25_mean, 2)
        if pm25_mean is not None
        else None
    ),

    "pm2_5_std": (
        round(pm25_std, 2)
        if pm25_std is not None
        else None
    ),

    "sensors": sensor_results
}


# ============================================================
# SALVA JSON
# ============================================================

with open("data.json", "w", encoding="utf-8") as file:

    json.dump(
        result,
        file,
        ensure_ascii=False,
        indent=2
    )


print(json.dumps(
    result,
    ensure_ascii=False,
    indent=2
))

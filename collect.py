import os
import time
import json
import statistics
import requests
from datetime import datetime
from zoneinfo import ZoneInfo


API_KEY = os.environ["PURPLEAIR_API_KEY"]

BASE_URL = "https://api.purpleair.com/v1"

SENSORS = [
    {"sensor_index": 31509, "name": "UEA-EST", "latitude": -3.091649, "longitude": -60.01759},
    {"sensor_index": 315615, "name": "MIT_NAMA_UFAM", "latitude": -3.089241, "longitude": -59.964367},
    {"sensor_index": 98395, "name": "FAS-Ar", "latitude": -3.074871, "longitude": -60.008675},
    {"sensor_index": 161259, "name": "UEA_EDUCAIR_2", "latitude": -3.131549, "longitude": -60.00408},
    {"sensor_index": 161261, "name": "UEA_EducAIR_1", "latitude": -3.130093, "longitude": -60.026802},
    {"sensor_index": 161279, "name": "UEA_EducAIR_5", "latitude": -3.096909, "longitude": -59.969593},
    {"sensor_index": 161291, "name": "UEA_EducAIR_6", "latitude": -3.128212, "longitude": -59.98678},
#    {"sensor_index": 165047, "name": "UEA_EducAIR_14", "latitude": -3.073211, "longitude": -59.993156},
    {"sensor_index": 165131, "name": "UEA_EducAIR_17", "latitude": -3.022957, "longitude": -60.05522},
    {"sensor_index": 177605, "name": "UEA_EducAIR_26", "latitude": -3.079295, "longitude": -59.93338},
    {"sensor_index": 181801, "name": "UEA_EducAIR_31", "latitude": -3.103645, "longitude": -60.04944},
    {"sensor_index": 181825, "name": "UEA_EducAIR_32", "latitude": -3.112573, "longitude": -60.01188},
    {"sensor_index": 205957, "name": "SEMA_MANAUS", "latitude": -3.08214, "longitude": -60.023293},
]


HEADERS = {
    "X-API-Key": API_KEY
}


def get_sensor_data(sensor_index):
    url = f"{BASE_URL}/sensors/{sensor_index}"

    params = {
        "fields": "sensor_index,name,last_seen"
    }

    response = requests.get(
        url,
        headers=HEADERS,
        params=params,
        timeout=30
    )

    response.raise_for_status()

    return response.json()["sensor"]


def get_sensor_history(sensor_index, start_timestamp, end_timestamp):
    url = f"{BASE_URL}/sensors/{sensor_index}/history"

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


# ---------------------------------------------------------
# Período analisado:
# sempre a última hora COMPLETA
# ---------------------------------------------------------

now = int(time.time())

current_hour = now - (now % 3600)

start_timestamp = current_hour - 3600
end_timestamp = current_hour


# ---------------------------------------------------------
# Coleta dos sensores
# ---------------------------------------------------------

sensors_data = []
pm25_values = []

number_online = 0


for sensor in SENSORS:

    sensor_index = sensor["sensor_index"]

    try:
        sensor_info = get_sensor_data(sensor_index)

        last_seen = sensor_info.get("last_seen")

        online = (
            last_seen is not None
            and now - last_seen <= 3600
        )

        pm25 = None

        if online:

            history = get_sensor_history(
                sensor_index,
                start_timestamp,
                end_timestamp
            )

            fields = history.get("fields", [])
            data = history.get("data", [])

            if data and "time_stamp" in fields and "pm2.5_atm" in fields:

                time_index = fields.index("time_stamp")
                pm_index = fields.index("pm2.5_atm")

                # A API pode não retornar os registros ordenados.
                data.sort(key=lambda row: row[time_index])

                # Último valor dentro da hora analisada
                last_row = data[-1]

                pm25 = last_row[pm_index]

                if pm25 is not None:
                    pm25_values.append(float(pm25))

            number_online += 1

        sensors_data.append({
            "sensor_index": sensor_index,
            "name": sensor_info.get("name", sensor["name"]),
            "latitude": sensor["latitude"],
            "longitude": sensor["longitude"],
            "online": online,
            "pm2_5": pm25
        })

    except Exception as e:

        print(
            f"Erro ao consultar sensor {sensor_index}: {e}"
        )

        sensors_data.append({
            "sensor_index": sensor_index,
            "name": sensor["name"],
            "latitude": sensor["latitude"],
            "longitude": sensor["longitude"],
            "online": False,
            "pm2_5": None
        })


# ---------------------------------------------------------
# Estatísticas
# ---------------------------------------------------------

if pm25_values:

    mean_pm25 = statistics.mean(pm25_values)

    std_pm25 = (
        statistics.pstdev(pm25_values)
        if len(pm25_values) > 1
        else 0
    )

else:

    mean_pm25 = None
    std_pm25 = None


# ---------------------------------------------------------
# Horários em Manaus
# ---------------------------------------------------------

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


# ---------------------------------------------------------
# Resultado
# ---------------------------------------------------------

output = {
    "updated_at": updated_at,
    "period_start": period_start,
    "period_end": period_end,
    "number_of_sensors": len(SENSORS),
    "number_online": number_online,
    "pm2_5_mean": mean_pm25,
    "pm2_5_std": std_pm25,
    "sensors": sensors_data
}


# ---------------------------------------------------------
# Salva JSON
# ---------------------------------------------------------

with open("data.json", "w", encoding="utf-8") as f:

    json.dump(
        output,
        f,
        ensure_ascii=False,
        indent=2
    )


print("Dados atualizados com sucesso.")

print(
    f"Período analisado: "
    f"{period_start} - {period_end}"
)

print(
    f"Dashboard atualizado: "
    f"{updated_at}"
)

print(
    f"Sensores online: "
    f"{number_online}/{len(SENSORS)}"
)

print(
    f"PM2.5 médio: "
    f"{mean_pm25}"
)

print(
    f"Desvio padrão: "
    f"{std_pm25}"
)
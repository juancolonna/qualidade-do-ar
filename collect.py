import os
import time
import json
import statistics
import requests
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo


# ============================================================
# Configuration
# ============================================================

API_KEY = os.environ["PURPLEAIR_API_KEY"]

BASE_URL = "https://api.purpleair.com/v1"

SENSORS_FILE = Path(__file__).with_name("sensors.json")
with open(SENSORS_FILE, "r", encoding="utf-8") as file:
    SENSORS = json.load(file)


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
        timeout=90
    )

    response.raise_for_status()

    return response.json()["sensor"]


def get_sensor_history(sensor_index, end_timestamp, average, fields):
    """Obtém o histórico de PM do sensor."""

    start_timestamp = end_timestamp - (average * 60)

    url = f"{BASE_URL}/sensors/{sensor_index}/history"

    headers = { "X-API-Key": API_KEY }

    params = {
        "start_timestamp": start_timestamp,
        "end_timestamp": end_timestamp,
        "average": average,
        "fields": fields
    }

    response = requests.get(
        url,
        headers=headers,
        params=params,
        timeout=90
    )

    response.raise_for_status()

    return response.json()


def get_record_values(history, field_names):
    """Retorna campos do único registro agregado, tratando dados ausentes."""
    fields = history.get("fields", [])
    data = history.get("data", [])

    if not data:
        return tuple(None for _ in field_names)

    row = data[0]
    values = []

    for name in field_names:
        if name not in fields:
            values.append(None)
            continue

        index = fields.index(name)
        values.append(row[index] if index < len(row) else None)

    return tuple(values)


def corrected_pm25(history):
    """Aplica a correção EPA ao PM2.5 usando a umidade do mesmo registro."""
    value, humidity = get_record_values(
        history,
        ["pm2.5_cf_1", "humidity"]
    )

    if value is None or humidity is None:
        return None

    if value < 570:
        return 0.524 * value - 0.0862 * humidity + 5.75

    elif value < 611:
        y1 = 0.524 * value - 0.0862 * humidity + 5.75
        y3 = 4.21e-4 * value**2 + 0.392 * value + 3.44
        weight = 0.0244 * value - 13.9
        return (1 - weight) * y1 + weight * y3

    else:
        return 4.21e-4 * value**2 + 0.392 * value + 3.44


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

pm01_values = []
pm01_24h_values = []
pm25_values = []
pm25_24h_values = []
pm10_values = []
pm10_24h_values = []
sensor_results = []
humidity_values = []
temperature_values = []
pressure_values = []

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

        sensor_results.append({
            "id": sensor_index,
            "name": sensor_name,
            "lat": sensor["lat"],
            "lon": sensor["lon"],
            "online": False,
            "pm0_1": None,
            "pm0_1_24h": None,
            "pm2_5": None,
            "pm2_5_24h": None,
            "pm10": None,
            "pm10_24h": None,
            "humidity": None,
            "temperature": None,
            "pressure": None
        })
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
            "pm0_1": None,
            "pm0_1_24h": None,        
            "pm2_5": None,
            "pm2_5_24h": None,
            "pm10": None,
            "pm10_24h": None,
            "humidity": None,
            "temperature": None,
            "pressure": None
        })

        continue

    print("  Sensor online.")

    # --------------------------------------------------------
    # 3. Consulta histórico de uma hora
    # --------------------------------------------------------

    try:
        # Última hora completa
        history_1h = get_sensor_history(
            sensor_index,
            end_timestamp,
            60,
            "pm1.0_cf_1,pm2.5_cf_1,pm10.0_cf_1,humidity,temperature,pressure"
        )

    except requests.RequestException as e:
        print(
            f"  Erro ao consultar histórico de 60 minutos"
            f"de {sensor_name}: {e}"
        )

        continue

    # --------------------------------------------------------
    # 4. Consulta histórico de uma hora de 24 horas
    # --------------------------------------------------------

    try:
        # Últimas 24 horas completas
        history_24h = get_sensor_history(
            sensor_index,
            end_timestamp,
            1440,
            "pm1.0_cf_1,pm2.5_cf_1,pm10.0_cf_1,humidity"
        )

    except requests.RequestException as e:
        print(
            f"  Erro ao consultar histórico de 24 horas"
            f"de {sensor_name}: {e}"
        )

        continue

    # --------------------------------------------------------
    # 5. Extrai os dados retornados pela API
    # --------------------------------------------------------

    pm01 = get_record_values(history_1h, ["pm1.0_cf_1"])[0]
    pm01_24h = get_record_values(history_24h, ["pm1.0_cf_1"])[0]

    pm25 = corrected_pm25(history_1h)
    pm25_24h = corrected_pm25(history_24h)

    pm10 = get_record_values(history_1h, ["pm10.0_cf_1"])[0]
    pm10_24h = get_record_values(history_24h, ["pm10.0_cf_1"])[0]

    humidity = get_record_values(history_1h, ["humidity"])[0]
    temperature = get_record_values(history_1h, ["temperature"])[0]
    pressure = get_record_values(history_1h, ["pressure"])[0]

    # --------------------------------------------------------
    # 8. Armazena resultado do sensor
    # --------------------------------------------------------

    sensor_results.append({
        "id": sensor_index,
        "name": sensor_name,
        "lat": sensor["lat"],
        "lon": sensor["lon"],
        "online": True,
        "pm0_1": pm01,
        "pm0_1_24h": pm01_24h,        
        "pm2_5": pm25,
        "pm2_5_24h": pm25_24h,
        "pm10": pm10,
        "pm10_24h": pm10_24h,
        "humidity": humidity,
        "temperature": temperature,
        "pressure": pressure
    })

    if pm01 is not None:
        pm01_values.append(pm01)

    if pm01_24h is not None:
        pm01_24h_values.append(pm01_24h)

    if pm25 is not None:
        pm25_values.append(pm25)

    if pm25_24h is not None:
        pm25_24h_values.append(pm25_24h)

    if pm10 is not None:
        pm10_values.append(pm10)

    if pm10_24h is not None:
        pm10_24h_values.append(pm10_24h)

    if humidity is not None:
        humidity_values.append(humidity)

    if temperature is not None:
        temperature_values.append(temperature)

    if pressure is not None:
        pressure_values.append(pressure)

# ============================================================
# 9. Statistics
# ============================================================

def pm_statistics(pm_values, number_online):
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

    n = len(pm_values)
    if n == 0:
        return None, None, None

    pm_mean = statistics.mean(pm_values)
    if n < 2 or n not in T_CRITICAL_95 or T_CRITICAL_95[n] is None:
        return round(pm_mean, 2), None, None

    pm_std = statistics.stdev(pm_values)
    t_critical = T_CRITICAL_95[n]
    standard_error = pm_std / (n ** 0.5)
    margin_of_error = t_critical * standard_error
    pm_ci95_lower = pm_mean - margin_of_error
    pm_ci95_upper = pm_mean + margin_of_error
    return round(pm_mean, 2), round(pm_ci95_lower, 2), round(pm_ci95_upper, 2)

number_online = sum(1 for sensor in sensor_results if sensor["online"])

pm01_mean, pm01_ci95_lower, pm01_ci95_upper = pm_statistics(pm01_values, number_online) 
pm01_24h_mean, pm01_24h_ci95_lower, pm01_24h_ci95_upper = pm_statistics(pm01_24h_values, number_online)
pm25_mean, pm25_ci95_lower, pm25_ci95_upper = pm_statistics(pm25_values, number_online)
pm25_24h_mean, pm25_24h_ci95_lower, pm25_24h_ci95_upper = pm_statistics(pm25_24h_values, number_online)
pm10_mean, pm10_ci95_lower, pm10_ci95_upper = pm_statistics(pm10_values, number_online)
pm10_24h_mean, pm10_24h_ci95_lower, pm10_24h_ci95_upper = pm_statistics(pm10_24h_values, number_online)
humidity_mean, humidity_ci95_lower, humidity_ci95_upper = pm_statistics(humidity_values, number_online) 
temperature_mean, temperature_ci95_lower, temperature_ci95_upper = pm_statistics(temperature_values, number_online) 
pressure_mean, pressure_ci95_lower, pressure_ci95_upper = pm_statistics(pressure_values, number_online) 

# ============================================================
# 10. US AQI - PM2.5
# ============================================================

def calculate_us_aqi(pm_24h):
    """Calcula o US AQI baseado no pior dos PMs usando a média de 24 horas."""

    if pm_24h is None:
        return None, None

    # EPA: concentração truncada para uma casa decimal.
    concentration = int(pm_24h * 10) / 10

    breakpoints = [
        (0.0, 9.0, 0, 50, "Bom"),
        (9.1, 35.4, 51, 100, "Moderado"),
        (35.5, 55.4, 101, 150, "Insalubre para grupos sensíveis"),
        (55.5, 125.4, 151, 200, "Insalubre"),
        (125.5, 225.4, 201, 300, "Muito insalubre"),
        (225.5, 325.4, 301, 500, "Perigoso"),
    ]

    for bp_lo, bp_hi, i_lo, i_hi, category in breakpoints:

        if concentration <= bp_hi:
            aqi = (
                (i_hi - i_lo)
                / (bp_hi - bp_lo)
                * (concentration - bp_lo)
                + i_lo
            )

            return round(aqi), category

    # Acima de 325.4 µg/m³ permanece na categoria Perigoso.
    aqi = ((500 - 301)/(325.4 - 225.5)*(concentration-225.5)+301)

    return round(aqi), "Perigoso"

us_aqi, us_aqi_category = calculate_us_aqi(pm25_24h_mean)

# ============================================================
# 11. Manaus timezone
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
# 12. Output
# ============================================================

result = {
    "updated_at": updated_at,
    "period_start": period_start,
    "period_end": period_end,

    "number_of_sensors": len(SENSORS),
    "number_online": number_online,

    "pm1_0_mean": pm01_mean,
    "pm1_0_ci95_lower": pm01_ci95_lower,
    "pm1_0_ci95_upper": pm01_ci95_upper,

    "pm1_0_24h_mean": pm01_24h_mean,
    "pm1_0_24h_ci95_lower": pm01_24h_ci95_lower,
    "pm1_0_24h_ci95_upper": pm01_24h_ci95_upper,

    "pm2_5_mean": pm25_mean,
    "pm2_5_ci95_lower": pm25_ci95_lower,
    "pm2_5_ci95_upper": pm25_ci95_upper,

    "pm2_5_24h_mean": pm25_24h_mean,
    "pm2_5_24h_ci95_lower": pm25_24h_ci95_lower,
    "pm2_5_24h_ci95_upper": pm25_24h_ci95_upper,

    "pm10_0_mean": pm10_mean,
    "pm10_0_ci95_lower": pm10_ci95_lower,
    "pm10_0_ci95_upper": pm10_ci95_upper,

    "pm10_0_24h_mean": pm10_24h_mean,
    "pm10_0_24h_ci95_lower": pm10_24h_ci95_lower,
    "pm10_0_24h_ci95_upper": pm10_24h_ci95_upper,

    "humidity_mean": humidity_mean,
    "humidity_ci95_lower": humidity_ci95_lower,
    "humidity_ci95_upper": humidity_ci95_upper,
     
    "temperature_mean": temperature_mean,
    "temperature_ci95_lower": temperature_ci95_lower,
    "temperature_ci95_upper": temperature_ci95_upper,

    "pressure_mean": pressure_mean,
    "pressure_ci95_lower": pressure_ci95_lower,
    "pressure_ci95_upper": pressure_ci95_upper,

    "us_aqi": us_aqi,
    "us_aqi_category": us_aqi_category,

    "sensors": sensor_results
}

# ============================================================
# 13. Save JSON
# ============================================================

with open("data.json", "w", encoding="utf-8") as f:

    json.dump(
        result,
        f,
        ensure_ascii=False,
        indent=2
    )


# ============================================================
# 14. Summary
# ============================================================

print("\n========================================")
print("Coleta concluída")
print("========================================")
print(f"Período: {period_start} - {period_end}")
print(f"Sensores online: {number_online}/{len(SENSORS)}")
print(f"US AQI: {us_aqi} - {us_aqi_category}")
print("========================================")

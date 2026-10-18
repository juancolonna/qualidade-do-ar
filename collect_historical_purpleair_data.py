import os
import time
import json
import statistics
import requests
from scipy.stats import t
from pathlib import Path
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo


# ============================================================
# Configuration
# ============================================================

API_KEY = os.environ["PURPLEAIR_API_KEY"]
BASE_URL = "https://api.purpleair.com/v1"

SENSORS_FILE = Path(__file__).with_name("sensors.json")
with SENSORS_FILE.open("r", encoding="utf-8") as file:
    SENSORS = json.load(file)

HISTORY_DIR = Path(__file__).parent / "historico"
REQUEST_INTERVAL_SECONDS = 1
AVERAGE = 60
PERIOD_DAYS = 180
TIMEOUT_SECONDS = 120

MANAUS_TZ = ZoneInfo("America/Manaus")

# Data/hora final do intervalo no horário de Manaus.
# O início é calculado automaticamente como END_TIME - 180 dias.
# Formato: "AAAA-MM-DD HH:MM"
END_TIME = "2026-10-14 09:00"

# Os mesmos campos consultados pelo collect.py.
HISTORY_FIELDS = [
    "pm2.5_cf_1",
    "pm10.0_cf_1",
    "humidity",
    "temperature",
    "pressure",
]

HEADERS = {"X-API-Key": API_KEY}


# ============================================================
# PurpleAir API
# ============================================================

def get_sensor_history(sensor_index, start_timestamp, end_timestamp):
    """Consulta o histórico horário de um sensor.

    O tratamento de exceções fica limitado à comunicação com a API.
    Retorna None se a consulta falhar.
    """

    url = f"{BASE_URL}/sensors/{sensor_index}/history"
    params = {
        "start_timestamp": start_timestamp,
        "end_timestamp": end_timestamp,
        "average": AVERAGE,
        "fields": ",".join(HISTORY_FIELDS),
    }

    try:
        response = requests.get(
            url,
            headers=HEADERS,
            params=params,
            timeout=TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        return response.json()
    except (requests.RequestException, ValueError) as error:
        print(f"Erro na consulta do sensor {sensor_index}: {error}")
        return None


# ============================================================
# Values and calculations (same logic as collect.py)
# ============================================================

def get_record_values(history, field_names):
    """Retorna os campos solicitados de cada linha, tratando ausências."""
    fields = history.get("fields", [])
    data = history.get("data") or []

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


def corrected_pm25(value, humidity):
    """Aplica a mesma correção EPA de PM2.5 usada em collect.py."""
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


def calculate_us_aqi(pm2_5):
    """Calcula o US AQI com a mesma tabela usada em collect.py."""
    if pm2_5 is None:
        return None, None

    concentration = int(pm2_5 * 10) / 10

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
                (i_hi - i_lo) / (bp_hi - bp_lo)
                * (concentration - bp_lo)
                + i_lo
            )
            return round(aqi), category

    aqi = ((500 - 301) / (325.4 - 225.5) * (concentration - 225.5) + 301)
    return round(aqi), "Perigoso"


def pm_statistics(pm_values):
    """Calcula média e IC de 95%, como em collect.py."""
    values = [value for value in pm_values if value is not None]

    if len(values) < 2:
        return None, None, None

    pm_mean = statistics.mean(values)
    pm_std = statistics.stdev(values)

    if pm_std > 0:
        filtered_values = [
            value for value in values
            if abs(value - pm_mean) <= 5 * pm_std
        ]
    else:
        return None, None, None

    n = len(filtered_values)
    if n < 2:
        return None, None, None

    pm_mean = statistics.mean(filtered_values)
    pm_std = statistics.stdev(filtered_values)

    t_critical = t.ppf(0.975, df=n - 1)
    standard_error = pm_std / (n ** 0.5)

    pm_lower = pm_mean - t_critical * standard_error
    pm_upper = pm_mean + t_critical * standard_error

    return round(pm_mean, 2), round(pm_lower, 2), round(pm_upper, 2)


# ============================================================
# Prepare hourly records
# ============================================================

def empty_sensor_result(sensor):
    """Cria um sensor com o mesmo formato usado por collect.py."""
    return {
        "id": sensor["id"],
        "name": sensor["name"],
        "lat": sensor["lat"],
        "lon": sensor["lon"],
        "online": False,
        "pm2_5": None,
        "pm10": None,
        "humidity": None,
        "temperature": None,
        "pressure": None,
    }


def create_hourly_records(start_timestamp, end_timestamp):
    """Cria a estrutura de cada hora, usando as mesmas chaves de collect.py."""
    records = {}
    updated_at = datetime.now(MANAUS_TZ).strftime("%d/%m/%Y %H:%M")

    for timestamp in range(start_timestamp, end_timestamp, 3600):
        period_start = datetime.fromtimestamp(
            timestamp, tz=MANAUS_TZ
        ).strftime("%d/%m/%Y %H:%M")
        period_end = datetime.fromtimestamp(
            timestamp + 3600, tz=MANAUS_TZ
        ).strftime("%d/%m/%Y %H:%M")

        records[timestamp] = {
            "updated_at": updated_at,
            "period_start": period_start,
            "period_end": period_end,
            "number_of_sensors": len(SENSORS),
            "sensors_online": 0,
            "pm2_5_mean": None,
            "pm2_5_ci95_lower": None,
            "pm2_5_ci95_upper": None,
            "pm10_0_mean": None,
            "pm10_0_ci95_lower": None,
            "pm10_0_ci95_upper": None,
            "humidity_mean": None,
            "humidity_ci95_lower": None,
            "humidity_ci95_upper": None,
            "temperature_mean": None,
            "temperature_ci95_lower": None,
            "temperature_ci95_upper": None,
            "pressure_mean": None,
            "pressure_ci95_lower": None,
            "pressure_ci95_upper": None,
            "us_aqi": None,
            "us_aqi_category": None,
            "sensors": [empty_sensor_result(sensor) for sensor in SENSORS],
        }

    return records


def add_sensor_history(records, sensor, history):
    """Insere os dados históricos do sensor nos registros horários."""
    fields = history.get("fields", [])
    rows = history.get("data") or []

    sensor_id = sensor["id"]

    for row in rows:
        values = dict(zip(fields, row))
        timestamp = values.get("time_stamp")

        if timestamp is None:
            continue

        timestamp = int(timestamp)
        hour_timestamp = timestamp - (timestamp % 3600)

        if hour_timestamp not in records:
            continue

        # Os registros históricos da API são associados à hora indicada
        # pelo timestamp retornado. A saída identifica o período pelo fim
        # da hora, seguindo a convenção de collect.py.
        sensor_result = next(
            item for item in records[hour_timestamp]["sensors"]
            if item["id"] == sensor_id
        )

        pm25_raw = values.get("pm2.5_cf_1")
        pm10 = values.get("pm10.0_cf_1")
        humidity = values.get("humidity")
        temperature = values.get("temperature")
        pressure = values.get("pressure")

        sensor_result.update({
            "online": True,
            "pm2_5": corrected_pm25(pm25_raw, humidity),
            "pm10": pm10,
            "humidity": humidity,
            "temperature": temperature,
            "pressure": pressure,
        })


def calculate_hourly_statistics(record):
    """Calcula as estatísticas para a hora, com a mesma estrutura de collect.py."""
    sensors = record["sensors"]
    record["sensors_online"] = sum(
        1 for sensor in sensors if sensor["online"]
    )

    pm25_values = [s["pm2_5"] for s in sensors if s["pm2_5"] is not None]
    pm10_values = [s["pm10"] for s in sensors if s["pm10"] is not None]
    humidity_values = [s["humidity"] for s in sensors if s["humidity"] is not None]
    temperature_values = [
        s["temperature"] for s in sensors if s["temperature"] is not None
    ]
    pressure_values = [s["pressure"] for s in sensors if s["pressure"] is not None]

    (
        record["pm2_5_mean"],
        record["pm2_5_ci95_lower"],
        record["pm2_5_ci95_upper"],
    ) = pm_statistics(pm25_values)

    (
        record["pm10_0_mean"],
        record["pm10_0_ci95_lower"],
        record["pm10_0_ci95_upper"],
    ) = pm_statistics(pm10_values)

    (
        record["humidity_mean"],
        record["humidity_ci95_lower"],
        record["humidity_ci95_upper"],
    ) = pm_statistics(humidity_values)

    (
        record["temperature_mean"],
        record["temperature_ci95_lower"],
        record["temperature_ci95_upper"],
    ) = pm_statistics(temperature_values)

    (
        record["pressure_mean"],
        record["pressure_ci95_lower"],
        record["pressure_ci95_upper"],
    ) = pm_statistics(pressure_values)

    record["us_aqi"], record["us_aqi_category"] = calculate_us_aqi(
        record["pm2_5_mean"]
    )


# ============================================================
# Save files
# ============================================================

def save_hourly_records(records):
    """Salva um JSON por hora em historico/AAAA/MM/DD/HHMM.json."""
    for timestamp, record in records.items():
        calculate_hourly_statistics(record)

        period_end_dt = datetime.fromtimestamp(
            timestamp + 3600, tz=MANAUS_TZ
        )
        output_dir = (
            HISTORY_DIR
            / period_end_dt.strftime("%Y")
            / period_end_dt.strftime("%m")
            / period_end_dt.strftime("%d")
        )
        output_dir.mkdir(parents=True, exist_ok=True)

        output_file = output_dir / (
            period_end_dt.strftime("%H%M") + ".json"
        )

        with output_file.open("w", encoding="utf-8") as file:
            json.dump(record, file, ensure_ascii=False, indent=2)
            file.write("\n")

    print(f"Arquivos horários gravados: {len(records)}")
    print(f"Diretório: {HISTORY_DIR}")


# ============================================================
# Main
# ============================================================

def main():
    end_dt = datetime.strptime(END_TIME, "%Y-%m-%d %H:%M")
    end_dt = end_dt.replace(tzinfo=MANAUS_TZ)

    if end_dt.minute != 0:
        raise ValueError("END_TIME deve estar alinhado ao início de uma hora (minutos = 00).")

    end_timestamp = int(end_dt.timestamp())
    start_timestamp = int((end_dt - timedelta(days=PERIOD_DAYS)).timestamp())

    print("========================================")
    print("Download do histórico PurpleAir")
    print("========================================")
    print(f"Sensores: {len(SENSORS)}")
    print(
        "Início Manaus: "
        f"{datetime.fromtimestamp(start_timestamp, tz=MANAUS_TZ)}"
    )
    print(
        "Fim Manaus:    "
        f"{datetime.fromtimestamp(end_timestamp, tz=MANAUS_TZ)}"
    )
    print(f"Média: {AVERAGE} minutos")
    print(f"Campos solicitados: {', '.join(HISTORY_FIELDS)}")
    print("========================================")

    hourly_records = create_hourly_records(
        start_timestamp,
        end_timestamp,
    )

    for index, sensor in enumerate(SENSORS):
        if index > 0:
            time.sleep(REQUEST_INTERVAL_SECONDS)

        sensor_id = sensor["id"]
        sensor_name = sensor.get("name", "")
        print(f"Consultando {sensor_name} ({sensor_id})...")

        history = get_sensor_history(
            sensor_id,
            start_timestamp,
            end_timestamp,
        )

        if history is None:
            continue

        add_sensor_history(hourly_records, sensor, history)
        print(f"  Registros retornados: {len(history.get('data') or [])}")

    save_hourly_records(hourly_records)

    print("========================================")
    print("Coleta histórica concluída")
    print("========================================")


if __name__ == "__main__":
    main()

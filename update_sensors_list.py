import argparse
import json
import math
import os
import sys
from pathlib import Path

import requests


API_KEY = os.environ.get("PURPLEAIR_API_KEY")
BASE_URL = "https://api.purpleair.com/v1"
CITIES_FILE = Path(__file__).with_name("cidades.json")
CITIES = {}
REQUIRED_COORDINATES = ("nw_lat", "nw_lon", "se_lat", "se_lon")


def load_cities():
    """Carrega e valida as regiões definidas em cidades.json."""
    try:
        data = json.loads(CITIES_FILE.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise FileNotFoundError(
            f"Arquivo de configuração {CITIES_FILE.name} não encontrado. "
            "Mantenha cidades.json na mesma pasta do script."
        ) from error
    except json.JSONDecodeError as error:
        raise ValueError(
            f"O arquivo {CITIES_FILE.name} não contém um JSON válido: {error}"
        ) from error

    if not isinstance(data, dict) or not data:
        raise ValueError(
            f"{CITIES_FILE.name} deve conter um objeto JSON com pelo menos uma cidade."
        )

    cities = {}
    for city_name, bounds in data.items():
        if not isinstance(city_name, str) or not city_name.strip():
            raise ValueError("Todos os nomes de cidades em cidades.json devem ser textos não vazios.")

        city = city_name.strip().lower()
        if city in cities:
            raise ValueError(
                f"A cidade '{city_name}' está duplicada em cidades.json "
                "(desconsiderando maiúsculas/minúsculas e espaços)."
            )

        if not isinstance(bounds, dict):
            raise ValueError(
                f"A configuração da cidade '{city}' deve ser um objeto com as coordenadas."
            )

        missing = [key for key in REQUIRED_COORDINATES if key not in bounds]
        if missing:
            raise ValueError(
                f"Faltam coordenadas para '{city}' em {CITIES_FILE.name}: "
                + ", ".join(missing)
            )

        validated_bounds = {}
        for key in REQUIRED_COORDINATES:
            value = bounds[key]
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(
                    f"A coordenada '{key}' da cidade '{city}' deve ser numérica."
                )
            if not math.isfinite(value):
                raise ValueError(
                    f"A coordenada '{key}' da cidade '{city}' deve ser um número finito."
                )
            validated_bounds[key] = value

        cities[city] = validated_bounds

    return cities


def fetch_sensors(city):
    """Consulta os sensores externos na região da cidade informada."""
    bounds = CITIES[city]

    response = requests.get(
        f"{BASE_URL}/sensors",
        headers={"X-API-Key": API_KEY},
        params={
            "fields": "sensor_index,name,latitude,longitude,last_seen",
            "location_type": 0,
            "nwlat": bounds["nw_lat"],
            "nwlng": bounds["nw_lon"],
            "selat": bounds["se_lat"],
            "selng": bounds["se_lon"],
        },
        timeout=240,
    )
    response.raise_for_status()

    payload = response.json()
    fields = payload.get("fields")
    rows = payload.get("data")

    return fields, rows


def rows_to_sensors(fields, rows, city):
    """Converte as linhas da API, incluindo a cidade de origem de cada sensor."""
    selected = []

    for row in rows:
        sensor = dict(zip(fields, row))
        selected.append({
            "id": sensor["sensor_index"],
            "name": sensor["name"],
            "lat": sensor["latitude"],
            "lon": sensor["longitude"],
            "city": city,
        })

    return selected


def ensure_sensor_file(sensors_file):
    """Garante que o arquivo exista, inclusive antes de consultar a API."""
    sensors_file.parent.mkdir(parents=True, exist_ok=True)
    if not sensors_file.exists():
        sensors_file.write_text("[]\n", encoding="utf-8")


def update_sensor_file(sensors_file, selected, default_city=None):
    """Acrescenta sensores novos e completa o campo city quando estiver ausente."""
    ensure_sensor_file(sensors_file)

    raw_content = sensors_file.read_text(encoding="utf-8")
    try:
        existing = json.loads(raw_content)
    except json.JSONDecodeError:
        # Compatibilidade com arquivos gerados por uma versão anterior do script,
        # que podia gravar os caracteres literais "\\n" após o JSON.
        corrected_content = raw_content
        while corrected_content.endswith("\\n"):
            corrected_content = corrected_content[:-2]
        existing = json.loads(corrected_content)

    if not isinstance(existing, list):
        raise ValueError(f"{sensors_file.name} deve conter uma lista de sensores.")

    # Indexa os registros existentes para identificar sensores já cadastrados.
    existing_by_id = {}
    for sensor in existing:
        if not isinstance(sensor, dict) or "id" not in sensor:
            raise ValueError(
                f"Todos os registros de {sensors_file.name} devem ser objetos com o campo 'id'."
            )
        existing_by_id[str(sensor["id"])] = sensor

        # Nos arquivos individuais, o nome do arquivo identifica a cidade.
        # Assim, registros antigos também recebem o campo city.
        if default_city and not sensor.get("city"):
            sensor["city"] = default_city

    added = 0
    for sensor in selected:
        sensor_id = str(sensor["id"])
        if sensor_id not in existing_by_id:
            existing.append(sensor)
            existing_by_id[sensor_id] = sensor
            added += 1
        else:
            # Enriquece registros antigos sem substituir os demais dados.
            # No consolidado, a cidade é preenchida com a primeira região
            # em que o sensor foi encontrado, caso ainda não esteja definida.
            current_sensor = existing_by_id[sensor_id]
            if not current_sensor.get("city") and sensor.get("city"):
                current_sensor["city"] = sensor["city"]

    existing.sort(key=lambda sensor: str(sensor["id"]))

    sensors_file.write_text(
        json.dumps(existing, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(
        f"{sensors_file.name} atualizado: {len(existing)} sensores no total; "
        f"{added} novos adicionados."
    )


def update_city(city):
    """Atualiza o arquivo de sensores de uma cidade."""
    sensors_file = Path(__file__).with_name(f"sensors_{city}.json")
    ensure_sensor_file(sensors_file)

    fields, rows = fetch_sensors(city)
    selected = rows_to_sensors(fields, rows, city)
    update_sensor_file(sensors_file, selected, default_city=city)


def update_all_cities():
    """Consulta todas as cidades e atualiza um único arquivo sensors.json."""
    all_sensors_file = Path(__file__).with_name("sensors.json")
    ensure_sensor_file(all_sensors_file)

    all_selected = []
    failed = False

    for city in CITIES:
        try:
            fields, rows = fetch_sensors(city)
            selected = rows_to_sensors(fields, rows, city)
            all_selected.extend(selected)
            print(f"{city}: {len(selected)} sensores encontrados na API.")
        except (
            requests.RequestException,
            ValueError,
            RuntimeError,
            KeyError,
            TypeError,
            OSError,
        ) as error:
            print(f"Erro ao consultar a cidade {city}: {error}", file=sys.stderr)
            failed = True

    # O ID elimina duplicatas entre cidades e sensores já existentes em
    # sensors.json são preservados.
    try:
        update_sensor_file(all_sensors_file, all_selected)
    except (ValueError, KeyError, TypeError, OSError) as error:
        print(f"Erro ao atualizar sensors.json: {error}", file=sys.stderr)
        failed = True

    return 1 if failed else 0


def main():
    global CITIES

    try:
        CITIES = load_cities()
    except (OSError, ValueError) as error:
        print(f"Erro ao carregar {CITIES_FILE.name}: {error}", file=sys.stderr)
        return 1

    parser = argparse.ArgumentParser(
        description=(
            "Atualiza a lista de sensores PurpleAir. "
            "Sem argumentos, consulta todas as cidades definidas em cidades.json "
            "e gera sensors.json."
        )
    )
    parser.add_argument(
        "cidades",
        nargs="*",
        type=str.lower,
        help=(
            "Uma ou mais cidades para consultar individualmente. "
            "Sem informar cidades, todas as localidades serão consultadas. "
            "Disponíveis: " + ", ".join(sorted(CITIES))
        ),
    )
    args = parser.parse_args()

    # Sem argumentos, consulta todas as cidades e gera somente sensors.json.
    if not args.cidades:
        return update_all_cities()

    invalid_cities = sorted(set(args.cidades) - set(CITIES))
    if invalid_cities:
        parser.error(
            "cidade(s) desconhecida(s): "
            + ", ".join(invalid_cities)
            + ". Cidades disponíveis: "
            + ", ".join(sorted(CITIES))
        )

    failed = False
    for city in args.cidades:
        try:
            update_city(city)
        except (
            requests.RequestException,
            ValueError,
            RuntimeError,
            KeyError,
            TypeError,
            OSError,
        ) as error:
            print(f"Erro ao atualizar sensors_{city}.json: {error}", file=sys.stderr)
            failed = True

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())

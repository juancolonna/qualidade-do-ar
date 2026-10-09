#!/usr/bin/env python3
"""Executa collect.py imediatamente e depois a cada hora."""

import logging
import subprocess
import sys
import time
from pathlib import Path

import schedule

BASE_DIR = Path(__file__).resolve().parent
COLLECT_SCRIPT = BASE_DIR / "collect.py"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s: %(message)s",
    handlers=[
        logging.FileHandler(BASE_DIR / "scheduler.log"),
        logging.StreamHandler(),
    ],
)


def run_collect():
    logging.info("Iniciando collect.py.")

    try:
        subprocess.run(
            [sys.executable, str(COLLECT_SCRIPT)],
            cwd=BASE_DIR,
            check=True,
            timeout=45 * 60,
        )
        logging.info("collect.py terminou com sucesso.")

    except subprocess.TimeoutExpired:
        logging.error("collect.py excedeu o limite de 45 minutos.")

    except subprocess.CalledProcessError as exc:
        logging.error("collect.py terminou com código de erro %s.", exc.returncode)

    except Exception:
        logging.exception("Erro inesperado ao executar collect.py.")


if __name__ == "__main__":

    # Executa imediatamente ao iniciar ou reiniciar o servidor.
    run_collect()

    # Depois, executa uma vez por hora, aos 5 minutos de cada hora.
    schedule.every().hour.at(":05").do(run_collect)
    logging.info("Agendamento ativo: collect.py será executado a cada hora, aos :05.")

    while True:
        schedule.run_pending()
        time.sleep(1)

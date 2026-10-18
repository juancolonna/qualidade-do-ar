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
SENSOR_LIST_UPDATE = BASE_DIR / "update_sensors_list.py"

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


def run_update_sensors_list():
    logging.info("Iniciando update_sensors_list.py.")

    try:
        subprocess.run(
            [sys.executable, str(SENSOR_LIST_UPDATE)],
            cwd=BASE_DIR,
            check=True,
            timeout=30 * 60,
        )
        logging.info("update_sensors_list.py terminou com sucesso.")

    except subprocess.TimeoutExpired:
        logging.error("update_sensors_list.py excedeu o limite de 30 minutos.")

    except subprocess.CalledProcessError as exc:
        logging.error(
            "update_sensors_list.py terminou com código de erro %s.",
            exc.returncode,
        )

    except Exception:
        logging.exception("Erro inesperado ao atualizar a lista de sensores.")



def run_backup_historico():
    """Envia arquivos novos ou modificados do histórico para o Google Drive."""
    history_dir = BASE_DIR / "historico"
    drive_dir = "gdrive:qualidade-do-ar/historico"

    logging.info("Iniciando backup do histórico para o Google Drive.")

    try:
        subprocess.run(
            ["rclone", "copy", str(history_dir), drive_dir],
            cwd=BASE_DIR,
            check=True,
            timeout=30 * 60,
        )
        logging.info("Backup do histórico para o Google Drive concluído.")

    except subprocess.TimeoutExpired:
        logging.error("Backup do histórico excedeu o limite de 30 minutos.")

    except subprocess.CalledProcessError as exc:
        logging.error("Backup do histórico falhou com código de erro %s.", exc.returncode)

    except Exception:
        logging.exception("Erro inesperado ao enviar o histórico para o Google Drive.")


if __name__ == "__main__":

    # Executa imediatamente ao iniciar ou reiniciar o servidor.
    run_collect()

    # Depois, executa uma vez por hora, aos 5 minutos de cada hora.
    schedule.every().hour.at(":05").do(run_collect)
    logging.info("Agendamento ativo: collect.py será executado a cada hora, aos :05.")

    # Atualiza a lista de sensores todos os dias às 23:30.
    schedule.every().day.at("23:30").do(run_update_sensors_list)
    logging.info("Agendamento ativo: update_sensors_list.py será executado diariamente às 23:30.")

    # Envia o histórico para o Google Drive todos os dias às 00:30.
    schedule.every().day.at("00:30").do(run_backup_historico)
    logging.info("Agendamento ativo: backup do histórico será executado diariamente às 00:30.")

    while True:
        schedule.run_pending()
        time.sleep(1)

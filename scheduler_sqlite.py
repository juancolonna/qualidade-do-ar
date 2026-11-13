#!/usr/bin/env python3
"""Executa collect.py imediatamente e depois a cada hora."""

import logging
import os
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

import schedule

BASE_DIR = Path(__file__).resolve().parent
COLLECT_SCRIPT = BASE_DIR / "collect.py"
SENSOR_LIST_UPDATE = BASE_DIR / "update_sensors_list.py"
DATABASE = BASE_DIR / "qualidade_ar.db"
BACKUP_DIR = BASE_DIR / "backup"
DATABASE_BACKUP = BACKUP_DIR / "qualidade_ar.db"

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



def backup_sqlite_database():
    """Cria uma cópia consistente do banco usando a API de backup do SQLite."""

    if not DATABASE.exists():
        logging.warning("Banco SQLite ainda não existe: %s", DATABASE)
        return False

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    temporary_backup = BACKUP_DIR / "qualidade_ar.db.tmp"

    if temporary_backup.exists():
        temporary_backup.unlink()

    try:
        with sqlite3.connect(DATABASE, timeout=30) as source_db:
            with sqlite3.connect(temporary_backup, timeout=30) as backup_db:
                source_db.backup(backup_db)
                integrity = backup_db.execute(
                    "PRAGMA integrity_check"
                ).fetchone()[0]

        if integrity != "ok":
            raise sqlite3.DatabaseError(
                f"Falha na verificação de integridade do backup: {integrity}"
            )

        # Publica a cópia somente depois de concluída e validada.
        os.replace(temporary_backup, DATABASE_BACKUP)
        logging.info("Cópia consistente do SQLite criada: %s", DATABASE_BACKUP)
        return True

    except Exception:
        if temporary_backup.exists():
            temporary_backup.unlink()
        logging.exception("Não foi possível criar o backup consistente do SQLite.")
        return False


def run_backup_historico():
    """Envia o banco SQLite e os históricos JSON antigos para o Google Drive."""

    history_dir = BASE_DIR / "historico"
    drive_history_dir = "gdrive:qualidade-do-ar/historico"
    drive_database = "gdrive:qualidade-do-ar/qualidade_ar.db"

    logging.info("Iniciando backup para o Google Drive.")
    backup_ok = True

    # Primeiro cria e envia uma cópia consistente do banco.
    if backup_sqlite_database():
        try:
            subprocess.run(
                ["rclone", "copyto", str(DATABASE_BACKUP), drive_database],
                cwd=BASE_DIR,
                check=True,
                timeout=30 * 60,
            )
            logging.info("Backup do banco SQLite enviado ao Google Drive.")
        except subprocess.TimeoutExpired:
            backup_ok = False
            logging.error("Envio do banco SQLite excedeu o limite de 30 minutos.")
        except subprocess.CalledProcessError as exc:
            backup_ok = False
            logging.error("Envio do banco SQLite falhou (código %s).", exc.returncode)
        except Exception:
            backup_ok = False
            logging.exception("Erro inesperado ao enviar o banco SQLite.")
    else:
        backup_ok = False

    # Mantém também o backup dos arquivos JSON históricos existentes.
    if history_dir.exists():
        try:
            subprocess.run(
                ["rclone", "copy", str(history_dir), drive_history_dir],
                cwd=BASE_DIR,
                check=True,
                timeout=30 * 60,
            )
            logging.info("Histórico JSON enviado ao Google Drive.")
        except subprocess.TimeoutExpired:
            backup_ok = False
            logging.error("Envio do histórico JSON excedeu o limite de 30 minutos.")
        except subprocess.CalledProcessError as exc:
            backup_ok = False
            logging.error("Envio do histórico JSON falhou (código %s).", exc.returncode)
        except Exception:
            backup_ok = False
            logging.exception("Erro inesperado ao enviar o histórico JSON.")
    else:
        logging.info("Diretório historico/ não existe; backup JSON ignorado.")

    if backup_ok:
        logging.info("Rotina de backup concluída com sucesso.")
    else:
        logging.warning("Rotina de backup concluída com uma ou mais falhas.")


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

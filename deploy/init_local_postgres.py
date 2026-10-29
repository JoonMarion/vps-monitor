"""Create this application's tables in its dedicated local PostgreSQL database.

Run on Ubuntu as the postgres OS user, after creating the database and its
vps_monitor_owner role. Runtime access belongs to the separate vps-monitor role.
"""

import sys
from pathlib import Path

from sqlalchemy import create_engine

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "back-end"))
from database import Base


def main():
    engine = create_engine(
        "postgresql+psycopg://postgres@/vps_monitor?host=/var/run/postgresql",
        hide_parameters=True,
    )
    try:
        with engine.begin() as connection:
            connection.exec_driver_sql("SET LOCAL ROLE vps_monitor_owner")
            Base.metadata.create_all(connection)
    finally:
        engine.dispose()
    print("Tabelas do banco vps_monitor inicializadas sob a role vps_monitor_owner.")


if __name__ == "__main__":
    main()

# Copyright: 2018, ISOC and the MANRS benchmarking tool contributors
# SPDX-License-Identifier: AGPL-3.0-only

from datetime import timedelta
import logging

from sqlalchemy import create_engine

# PostgreSQL configuration.
POSTGRESQL_USER = "manrs"
POSTGRESQL_PASS = "manrs"
POSTGRESQL_DB = "manrs"
POSTGRESQL_HOST = "localhost"
POSTGRESQL_PORT = "5432"

# Database interface (SQLAlchemy) configuration.
DB_DEBUG = False
DB_ENGINE = create_engine("postgresql://{}:{}@{}:{}/{}".format(
    POSTGRESQL_USER, POSTGRESQL_PASS, POSTGRESQL_HOST, POSTGRESQL_PORT,
    POSTGRESQL_DB), echo=DB_DEBUG)

# Logging configuration.
LOGGING_LEVEL = logging.INFO
LOGGING_FORMAT = "%(asctime)s %(levelname)-8s %(name)-30.30s %(message)s"
LOGGING_FILE = "benchmark.log"

# If set the latest report will also be written to disk in json format.
# The file will be overwritten in consecutive runs. Meant for debugging.
LATEST_REPORT_FILE = "latest_report.json"
LATEST_REPORT_FILE = ""

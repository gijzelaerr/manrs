# Copyright: 2018, ISOC and the MANRS benchmarking tool contributors
# SPDX-License-Identifier: AGPL-3.0-only

from manrs.models import Base

import config


def create_schema(engine):
    Base.metadata.create_all(engine)


if __name__ == "__main__":
    create_schema(config.DB_ENGINE)

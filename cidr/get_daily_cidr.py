# Copyright: 2018, ISOC and the MANRS benchmarking tool contributors
# SPDX-License-Identifier: AGPL-3.0-only

import datetime
import logging
import os
import shutil
import sys

from bs4 import BeautifulSoup
import requests

DATA_DIR = "data"
LOG_FORMAT = "%(asctime)s %(name)-12s %(levelname)-8s %(message)s"
logging.basicConfig(format=LOG_FORMAT, filename="log.log", level=logging.INFO)


def check_if_today_is_live():
    report_day = None
    report = requests.get("https://www.cidr-report.org/as2.0/indext.html")
    soup = BeautifulSoup(report.text, 'html.parser')
    for tag in soup.select("h2"):
        if tag.string.startswith("CIDR REPORT for"):
            report_day = tag.string.split("CIDR REPORT for")[1].strip()
            report_day = datetime.datetime.strptime(report_day,
                                                    "%d %b %y").date()
            break
    if datetime.date.today() == report_day:
        return True
    return False


if __name__ == "__main__":
    if not check_if_today_is_live():
        logging.info("Report is not yet updated, quitting.")
        sys.exit(0)

    today = datetime.date.today().strftime("%Y%m%d")
    directory = "{}/{}".format(DATA_DIR, today)
    if os.path.isdir(directory):
        logging.info("Report already gathered for today.")
        sys.exit(0)

    try:
        logging.info("Creating the today directory ({}).".format(directory))
        os.makedirs(directory)
        logging.info("Getting as2 prefixes.")
        as2_prefixes = requests.get(
            "https://bgp.potaroo.net/as2.0/bgp-bogus-routes.txt").text
        logging.info("Getting as6447 prefixes.")
        as6447_prefixes = requests.get(
            "https://bgp.potaroo.net/as6447/bgp-bogus-routes.txt").text
        bogons = set()
        for line in (x for x in as2_prefixes.split("\n") if x):
            bogons.add(line)
        for line in (x for x in as6447_prefixes.split("\n") if x):
            bogons.add(line)
        logging.info("Got {} advertised bogons.".format(len(bogons)))

        with open("{}/bogon_prefixes.txt".format(directory), 'w+') as f:
            logging.info("Writing bogon prefixes.".format(today))
            for line in sorted(bogons,
                               key=lambda x: int(x.split()[1].split("AS")[1])):
                print(line, file=f)
    except Exception as e:
        logging.critical("{}: {}".format(e.__class__.__name__, e))
        logging.critical("Cleaning up...")
        shutil.rmtree(directory)

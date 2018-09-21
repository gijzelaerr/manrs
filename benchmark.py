# Copyright: 2018, ISOC and the MANRS benchmarking tool contributors
# SPDX-License-Identifier: AGPL-3.0-only

import argparse
from datetime import datetime, timedelta
import logging
import os
import statistics
import json

from sqlalchemy.orm import sessionmaker

from manrs import settings
from manrs.data_sources.bgpstream import BGPStreamSourceData
from manrs.data_sources.ripestat import RIPEstatSourceData
from manrs.data_sources.cidr import CIDRSourceData
from manrs.util import get_manrs_participants, WeightGeneratorFactory
from manrs.metrics import get_results_per_asn
from manrs.models import Report, ReportType, Result, GlobalStats
import config


def parse_cmd():
    """
    Parse command line arguments.

    """

    def define_period(args):
        """
        Based on user input, sanitize and calculate start and end times
        of the testing period.

        If no input was given the previous month is going to be used as the
        testing period.

        Otherwise both start and end date need to be given as input.

        """

        # If start and end dates were not given use the previous month
        if not (args.start_date or args.end_date):
            now = datetime.now()
            current_month = now.month
            current_year = now.year
            if current_month == 1:
                previous_month = 12
                previous_year = current_year - 1
            else:
                previous_month = current_month - 1
                previous_year = current_year

            args.end_date = datetime(
                year=current_year, month=current_month, day=1)
            args.start_date = datetime(
                year=previous_year, month=previous_month, day=1)
        elif args.start_date and args.end_date:
            if not args.start_date < args.end_date:
                raise argparse.ArgumentTypeError(
                    "start_date needs to be earlier than end_date!")
        else:
            raise argparse.ArgumentTypeError(
                "When specifiying start and end dates both need to be "
                "specified!")

    def parse_date(string):
        """
        Parse date in YYYYmmdd format.

        """
        try:
            return datetime.strptime(string, "%Y%m%d")
        except Exception:
            raise argparse.ArgumentTypeError(
                "Invalid date. Date needs to be in YYYYmmdd format.")

    def parse_type(string):
        """
        Parse type of report. Defaults to ``manual``.

        """
        if string not in ["auto", "manual"]:
            raise argparse.ArgumentTypeError(
                "Invalid report type. Valid values are 'auto' or 'manual'.")
        if string == "auto":
            return ReportType.auto
        else:
            return ReportType.manual

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-s", "--start-date", type=parse_date,
        help="Period start date in YYYYmmdd format. If specified, --end-date "
             "needs to be specified as well. If not specified the previous "
             "month is picked as the testing period.")
    parser.add_argument(
        "-e", "--end-date", type=parse_date,
        help="Period end date in YYYYmmdd format. If specified, --start-date "
             "needs to be specified as well. If not specified the previous "
             "month is picked as the testing period.")
    parser.add_argument("-t", "--report-type",
        type=parse_type, required=False, default=ReportType.manual,
        help="Set the report type: {manual(default), auto}.")
    parser.add_argument("-v", "--verbosity",
        choices=["debug", "info", "warning", "error", "critical"],
        help="Set the logging level: {debug, info, warning(default), "
        "error, critical}")

    args = parser.parse_args()
    define_period(args)
    return args


def configure_logging(verbosity):
    """
    Configure logging.

    Command line option for level has precedence.
    Format and file are configured from the config file.

    """
    if not verbosity:
        level = config.LOGGING_LEVEL
    else:
        level = getattr(logging, verbosity.upper())

    if config.LOGGING_FILE:
        logging.basicConfig(level=level,
                            format=config.LOGGING_FORMAT,
                            filename=config.LOGGING_FILE)
    else:
        logging.basicConfig(level=level,
                            format=config.LOGGING_FORMAT)


def check_db_connection():
    """
    Check that we have a connection to the database.
    Throw early error if there is a connection problem (ie. postgres not
    running/listening)

    """
    Session = sessionmaker(config.DB_ENGINE)
    session = Session()
    _ = session.query(Report).get(1)
    session.close()


def main():
    """
    Parse command line arguments and configure together with settings file.
    Gather the necessary data from the data modules, calculate the metrics and
    statistics and save everything in the DB.

    """
    args = parse_cmd()
    configure_logging(args.verbosity)
    period_start = args.start_date
    period_end = args.end_date
    weight_generator_factory = WeightGeneratorFactory(
        settings.WEIGHT_GENERATOR_TYPE, settings.WEIGHT_GENERATOR_START,
        settings.WEIGHT_GENERATOR_INTERVAL, settings.WEIGHT_GENERATOR_END)
    cidr_data_dir = settings.CIDR_DATA_DIRECTORY

    check_db_connection()

    logging.info("Getting participants")
    participants = get_manrs_participants()

    asns = set()
    for participant in participants:
        for asn in participant['asns']:
            asns.add(asn)

    logging.info("Starting modules")
    bgp_stream = BGPStreamSourceData(period_start=period_start,
                                     period_end=period_end)
    ripestat = RIPEstatSourceData(asns)
    cidr = CIDRSourceData(cidr_data_dir,
                          period_start=period_start,
                          period_end=period_end)
    logging.info("Modules started")

    bgp_stream.fetch_data()
    bgp_stream_results = bgp_stream.get_results(weight_generator_factory)

    ripestat.fetch_data()
    ripestat_results = ripestat.get_results()

    cidr.fetch_data()
    cidr_results = cidr.get_results()

    logging.info("Calculating metrics")
    results = get_results_per_asn(asns, bgp_stream_results, cidr_results,
                                  ripestat_results)

    report = {
        'period_start': period_start,
        'period_end': period_end,
        'generated': datetime.now(),
        'results': results,
    }

    if config.LATEST_REPORT_FILE:
        logging.info("Writing report to '{}'".format(
           os.path.abspath(config.LATEST_REPORT_FILE)))
        with open(config.LATEST_REPORT_FILE, 'w') as f:
            json.dump(report, f, indent=4, default=str)

    logging.info("Storing report in DB")
    store_report(report, args.report_type)
    logging.info("Finished")


def store_report(report, report_type):
    """
    Store report in DB.

    """
    Session = sessionmaker(config.DB_ENGINE)
    session = Session()

    # Create report record
    report_db = Report(
        period_start=report['period_start'],
        period_end=report['period_end'],
        date_started=None,
        date_finished=report['generated'],
        type=report_type)
    session.add(report_db)
    session.commit()

    # Create records for the results
    results_db = []
    for asn, results in report['results'].items():
        kwargs = {'asn': asn, 'report_id': report_db.id}
        for key in results:
            kwargs[key] = results[key]
        result = Result(**kwargs)
        results_db.append(result)
    session.add_all(results_db)
    session.commit()

    # Calculate statistics for this report
    kwargs = {'report_id': report_db.id}
    statistic_calculations = GlobalStats.get_statistics_calculations()
    for metric, calculations in statistic_calculations.items():
        for calc in calculations:
            key = "{}_{}".format(metric, calc)
            value = getattr(statistics, calc)(
                (getattr(x, metric)
                 for x in results_db
                 if getattr(x, metric) is not None))
            kwargs[key] = value
    global_stats = GlobalStats(**kwargs)
    session.add(global_stats)
    session.commit()
    session.close()


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logging.critical("Execution failed!")
        logging.critical("{}: {}".format(e.__class__.__name__, e))

# Copyright: 2018, ISOC and the MANRS benchmarking tool contributors
# SPDX-License-Identifier: AGPL-3.0-only

from collections import defaultdict
from datetime import datetime, timedelta
import logging
import os
import sys

from manrs import settings


class CIDRError(Exception):
    """
    General error for CIDR report.

    """
    pass


class CIDRInputError(CIDRError):
    """
    Error indicating invalid input when calling the module.

    """
    pass


class CIDRSourceData(object):
    """
    Class to handle parsing of the daily saved data from CIDR.

    """
    def __init__(self, data_dir, period_start=None, period_end=None):
        self.logger = logging.getLogger(__name__)
        self.logger.info("Starting module")
        if not os.path.isdir(data_dir):
            raise CIDRInputError("Data directory ({}) does not exist!"
                                 "".format(data_dir))
        if period_start:
            if period_end and period_start > period_end:
                raise CIDRInputError("Period start later than period end!")
            if period_start > datetime.now():
                raise CIDRInputError("Period start in the future!")
        if not period_end:
            period_end = datetime.now()
        if not period_start:
            period_start = period_end - timedelta(days=1)
        self.period_start = period_start
        self.period_end = period_end
        self.data_dir = data_dir

    @staticmethod
    def _parse_bogon_prefix(filename):
        """
        Parse the data in the bogon_prefix file and return a
        (prefix, asn, description) tuple.

        """
        parsed_data = []
        with open(filename, 'r') as f:
            for line in f:
                contents = line.strip().split(maxsplit=2)
                prefix = contents[0]
                asn = int(contents[1].split("AS")[1])
                description = contents[2]
                parsed_data.append((prefix, asn, description))
        return parsed_data

    @staticmethod
    def _period_dates_generator(period_start, period_end):
        """
        Generate all the possible dates in this period in the format
        expected for the folder's name.

        """
        curr_date = period_start
        while curr_date < period_end:
            yield curr_date.strftime("%Y%m%d")
            curr_date += timedelta(days=1)

    def _get_files_in_period(self):
        """
        Get the files that have data for the tested period.

        """
        filenames = []
        for date in self._period_dates_generator(self.period_start,
                                                 self.period_end):
            filename = "{}/{}/{}".format(
                    self.data_dir, date, settings.BOGON_PREFIX_FILENAME)
            if os.path.isfile(filename):
                filenames.append((date, filename))
        return filenames

    def fetch_data(self):
        """
        Fetch and parse the locally stored data.

        """
        self.logger.info("Gathering and parsing data")
        data = {}
        filenames = self._get_files_in_period()
        for date, filename in filenames:
            data[date] = {
                'bogon_prefixes': None
            }
            data[date]['bogon_prefixes'] = self._parse_bogon_prefix(filename)
        self.data = data

    def get_results(self):
        """
        Get the results per check and per culprit.

        """
        self.logger.info("Getting results")
        results = {
            'bogon_prefixes': {
                # A bit ugly but we will need
                # culprits[asn][prefix]['dates'] to be a set.
                # If we need to print this we can later subclass defaultdict
                # and overide __repr__ to convert each nested defaultdict to
                # dict.
                # 'culprits': defaultdict(lambda:
                #                         defaultdict(lambda:
                #                                     defaultdict(set))),
                'culprits': defaultdict(list),
            },
        }
        for date, checks in self.data.items():
            for check, data in checks.items():
                for prefix, asn, description in data:
                    # results[check]['culprits'][asn][prefix]['dates'].add(date)
                    start_time = datetime.strptime(date, "%Y%m%d")
                    end_time = start_time + timedelta(days=1)
                    results[check]['culprits'][asn].append({
                        'prefix': prefix,
                        'start_time': start_time,
                        'end_time': end_time,
                        'weight': 1.0,
                    })
        self.logger.info("Done")
        return results

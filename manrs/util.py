# Copyright: 2018, ISOC and the MANRS benchmarking tool contributors
# SPDX-License-Identifier: AGPL-3.0-only

import requests
from bs4 import BeautifulSoup


def get_manrs_participants():
    """
    Scrape the MANRS web page to get the MANRS members.

    """
    def _get_name(row):
        return row.select(".column-1 a")[0].string.strip()

    def _get_countries(row):
        countries = row.select(".column-2")[0].string.strip()
        countries = countries.split(",")
        return list(map(lambda x: x.strip(), countries))

    def _get_asns(row):
        res = []
        asns = row.select(".column-3")[0].string.strip()
        asns = asns.split(",")
        for asn in asns:
            try:
                res.append(int(asn.strip()))
            except ValueError:
                start, end = asn.split("-")
                res.extend(range(int(start), int(end)+1))
        return res

    def _get_commitment(row, class_selector):
        if row.select("{} img".format(class_selector)):
            return True
        return False

    url = "https://www.manrs.org/participants/"
    participants = []
    resp = requests.get(url).text
    # Hack for broken HTML
    resp = resp.replace(
        "<a href=\"http://www.claranet.com\" />",
        "<a href=\"http://www.claranet.com\" >")
    soup = BeautifulSoup(resp, 'html.parser')
    for participant_row in soup.select("#tablepress-1 tbody tr"):
        participant = {}
        participant['name'] = _get_name(participant_row)
        participant['countries'] = _get_countries(participant_row)
        participant['asns'] = _get_asns(participant_row)
        participant['filtering'] = _get_commitment(participant_row,
                                                   ".column-4")
        participant['spoofing'] = _get_commitment(participant_row,
                                                  ".column-5")
        participant['coordination'] = _get_commitment(participant_row,
                                                      ".column-6")
        participant['validation'] = _get_commitment(participant_row,
                                                    ".column-7")
        participants.append(participant)

    return participants


class GeometricGenerator:
    """
    Custom generator to return numbers in a confined geometric progression
    from start to end.

    """
    def __init__(self, start, step, end):
        self.start = start
        self.step = step
        self.end = end
        self.value = start
        if end < start:
            self.limiter = max
        else:
            self.limiter = min

    def __iter__(self):
        return self

    def __next__(self):
        return_value = self.value
        self.value = self.limiter(self.value*self.step, self.end)
        return return_value

    def reset(self):
        self.value = self.start


class WeightGeneratorFactoryError(Exception):
    """
    Generic exception for WeightGeneratorFactory.

    """
    pass


class WeightGeneratorFactory:
    """
    Class to create weight generators.

    """
    def __init__(self, gen_type, start, step, end):
        self.gen_type = gen_type
        self.start = start
        self.step = step
        self.end = end

    def get(self):
        if self.gen_type == "geometric":
            return GeometricGenerator(self.start, self.step, self.end)
        raise WeightGeneratorFactoryError("Unknown generator type: '{}'"
                                          "".format(self.gen_type))


def tries(num_tries, logger, action_name):
    """
    Helper generator for retrying things.

    It is intended to be used in for loop. If the end of the loop is reached it
    should be treated as failure. Likewise if the operation was succesful, the
    the loop should be broken.

    """
    while num_tries > 0:
        yield num_tries
        num_tries -= 1
        logger.warning("Have to retry for [{}]. Tries left: {}"
                       "".format(action_name, num_tries))

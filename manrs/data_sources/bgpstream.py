# Copyright: 2018, ISOC and the MANRS benchmarking tool contributors
# SPDX-License-Identifier: AGPL-3.0-only

from collections import OrderedDict
from datetime import datetime, timedelta
import logging
import requests
import json


class BGPStreamError(Exception):
    """
    General error for bgpstream.

    """
    pass


class BGPStreamInsaneDataError(BGPStreamError):
    """
    Error indicating a change on the data format.

    """
    pass


class BGPStreamInputError(BGPStreamError):
    """
    Error indicating invalid input when calling the module.

    """
    pass


class BGPStreamSourceData(object):
    API_URL = ("http://portal.bgpmon.net/bgpstream_server.php?"
               "action=get_events&days={days}")

    API_JSON = {
        'main_members': ['status', 'error', 'events'],
        'event_types': ['bgp_leak', 'bgp_hijack', 'outage'],
        'event_members': {
            'bgp_leak': [
                'bgplay_json',
                'end_time',
                'event_id',
                'event_type',
                'leak_as_path',
                'leak_peer_count',
                'leaked_prefix',
                'leaked_to',
                'leaker_asn',
                'leaker_asn_name',
                'origin_asn',
                'origin_asn_name',
                'start_time'
            ],
            'outage': [
                'asn',
                'asn_name',
                'bgplay_json',
                'country',
                'end_time',
                'event_id',
                'event_type',
                'outage_count_percentage',
                'outage_count_prefix',
                'outage_example_prefix',
                'outage_graph',
                'start_time'
            ],
            'bgp_hijack': [
                'base_asn',
                'base_asn_name',
                'bgplay_json',
                'end_time',
                'event_id',
                'event_type',
                'hijack_announced_prefix',
                'hijack_as_path',
                'hijack_base_prefix',
                'hijack_peer_count',
                'hijack_type',
                'origin_asn',
                'origin_asn_name',
                'start_time'
            ],
        },
    }

    def __init__(self, period_start=None, period_end=None, leeway=30):
        """
        Class to handle communication/parsing for the BGPStream data source.

        The data gathered are limited by the period's duration.
        An extra 'leeway' variable can help by also targeting events that
        started before the specified period but are still active in the
        given period.

        """
        self.logger = logging.getLogger(__name__)
        self.logger.info("Starting module")
        if period_start:
            if period_end and period_start > period_end:
                raise BGPStreamInputError("Period start later "
                                          "than period end!")
            if period_start > datetime.now():
                raise BGPStreamInputError("Period start in the future!")
        if not period_end:
            period_end = datetime.now()
        if not period_start:
            period_start = period_end - timedelta(days=1)

        self.period_start = period_start
        self.period_end = period_end
        self.leeway = leeway
        self.data = None

    def _create_event(self, event, weight_generator):
        # First check that the event is in the period.
        if ((event['start_time'] < self.period_start
                and event['end_time'] < self.period_start)
                or (event['start_time'] > self.period_end
                    and event['end_time'] > self.period_end)):
            return None

        if event['event_type'] == "bgp_leak":
            return LeakEvent(event, self.period_start, self.period_end,
                             weight_generator)
        elif event['event_type'] == "bgp_hijack":
            return HijackEvent(event, self.period_start, self.period_end,
                               weight_generator)

    def _analyze_json_structure(self, data=None):
        """
        Print bgpstream's json structure for debugging.

        """
        if not data:
            data = self.data

        main_members = []
        event_types = set()
        for key in data:
            main_members.append(key)
        print("Main structure:\n{}".format(main_members))
        print("status: {}".format(data['status']))
        print("error: {}".format(data['error']))
        event_members = set()
        for event in data['events']:
            event_types.add(event['event_type'])
            event_members = []
            for key in event:
                event_members.append(key)
            event_members.add(frozenset(event_members))

        for s in event_members:
            print("set:\n{}\n\n".format(sorted(list(s))))
        print("event_types: {}".format(event_types))

    def _elaborate_data(self, original):
        """
        Filter and sanitize data.

        """
        main_members = set(self.API_JSON['main_members'])
        event_types = set(self.API_JSON['event_types'])
        event_members = self.API_JSON['event_members']

        data = original.copy()
        data['events'] = []

        # Check main_members
        for key in data:
            try:
                main_members.remove(key)
            except KeyError:
                raise BGPStreamInsaneDataError(
                    "Main members have changed! "
                    "Could not find '{}' in the specification.".format(key))
        if main_members:
            raise BGPStreamInsaneDataError(
                "Main members have changed! {} are no longer part of the "
                "specification.".format(main_members))

        for event in original['events']:
            # Check event_types
            if event['event_type'] not in event_types:
                raise BGPStreamInsaneDataError("New event type!")

            # Filter out the outage type
            if event['event_type'] == "outage":
                continue

            # Check event members
            members = set(event_members[event['event_type']])
            for key in event:
                try:
                    members.remove(key)
                except KeyError:
                    raise BGPStreamInsaneDataError(
                        "New key in '{}' event type!".format(
                         event['event_type']))

            if members:
                raise BGPStreamInsaneDataError(
                    "Event members have changed for '{}' event type".format(
                     event['event_type']))

            time_format = "%Y-%m-%d %H:%M:%S"
            start_time = datetime.strptime(event['start_time'], time_format)
            try:
                end_time = datetime.strptime(event['end_time'], time_format)
            except ValueError:  # Parsing '0000-00-00 00:00:00'
                end_time = self.period_end

            # Check if the event is within the period
            if (start_time < self.period_start
                    and (end_time and not end_time > self.period_start)):
                continue

            event['start_time'] = start_time
            event['end_time'] = end_time
            data['events'].append(event)

        return data

    def fetch_data(self):
        """
        Fetch the raw data after filtering and sanitization.

        """
        self.logger.info("Gathering raw data")
        days = (datetime.now() - self.period_start).days
        days += self.leeway
        resp = requests.get(self.API_URL.format(days=days))
        data = self._elaborate_data(resp.json())
        self.data = data

    def get_results(self, weight_generator_factory):
        """
        Get the results per check and per culprits and accomplices.

        """
        self.logger.info("Getting results")
        results = {
            'bgp_leak': {
                'culprits': [],
                'accomplices': [],
            },
            'bgp_hijack': {
                'culprits': [],
                'accomplices': [],
            },
        }
        for event_dict in self.data['events']:
            event = self._create_event(event_dict, weight_generator_factory)
            if not event:
                continue
            culprit = event.get_culprit()
            accomplices = event.get_accomplices()
            results[event.event_type]['culprits'].append(culprit)
            results[event.event_type]['accomplices'].extend(accomplices)
        self.logger.info("Done")
        return results


class BGPEvent(object):
    """
    Abstract class for BGPStream events.

    """
    def __init__(self, dictionary, period_start, period_end,
                 weight_generator_factory):
        self._variables = []
        for k, v in dictionary.items():
            setattr(self, k, v)
            self._variables.append(k)

        self._curate_start_end_times(period_start, period_end)
        self._calculate_duration()
        self.weight_generator = weight_generator_factory.get()

    def _curate_start_end_times(self, period_start, period_end):
        """
        Curate the start and end times to reflect time spent inside the given
        period.

        """
        curated_start_time = max(self.start_time, period_start)
        curated_end_time = max(min(self.end_time, period_end),
                               curated_start_time)
        self.curated_start_time = curated_start_time
        self.curated_end_time = curated_end_time
        self._variables.extend([
            'curated_start_time',
            'curated_end_time',
        ])

    def _calculate_duration(self):
        """
        Calculates the event's duration based on the period.

        """
        duration = int((self.curated_end_time
                        - self.curated_start_time).total_seconds())
        self.duration = duration
        self._variables.append('duration')

    def __str__(self):
        """
        View the object's variables. Meant for debugging.

        """
        res = {}
        for variable in self._variables:
            res[variable] = getattr(self, variable)
        return "{}".format(res)

    def __repr__(self):
        return self.__str__()


class LeakEvent(BGPEvent):
    """
    Class for 'bgp_leak' BGPStream events.

    """
    def get_culprit(self):
        """
        Get the culprit of the leak.

        """
        return {
            'asn': int(self.leaker_asn),
            'prefix': self.leaked_prefix,
            'start_time': self.curated_start_time,
            'end_time': self.curated_end_time,
            'weight': 1.0,
            'duration': self.duration,
            'bgpstream_eventid': self.event_id,
        }

    def get_accomplices(self):
        """
        Get all the accomplices.

        Accomplices are ASNs that were reported as leaked_to from bgpstream.
        ASNs in the provided AS Path are also considered accomplices but the
        weight for these is significantly reduced the further away they are
        from the culprit.

        """
        accomplices = []

        if not ASPATH_ONLY_NEXT_HOP_AS_ACCOMPLICE:
            # The last ASN in the path is the reporter, ignore it.
            asns_in_path = self.leak_as_path.split()[1:]
            # We ignore the leaked_to ASN for now; it is going to be included
            # further down.
            leaker_index = asns_in_path.index(self.leaker_asn)
            leaked_to = asns_in_path[leaker_index-1]
            leaked_to_index = asns_in_path.index(leaked_to)
            unique_ordered_asns = OrderedDict()
            for asn in reversed(asns_in_path[:leaked_to_index]):
                unique_ordered_asns[asn] = None
            for asn in unique_ordered_asns:
                accomplices.append({
                    'asn': int(asn),
                    'prefix': self.leaked_prefix,
                    'start_time': self.curated_start_time,
                    'end_time': self.curated_end_time,
                    'weight': next(self.weight_generator),
                    'duration': self.duration,
                    'bgpstream_eventid': self.event_id,
                })

        # Add all the leaked_to ASNs. These get full weight.
        leaked_to = self.leaked_to.split(",")
        leaked_to = [x.split("=")[0] for x in leaked_to]
        for asn in leaked_to:
            accomplices.append({
                'asn': int(asn),
                'prefix': self.leaked_prefix,
                'start_time': self.curated_start_time,
                'end_time': self.curated_end_time,
                'weight': 1.0,
                'duration': self.duration,
                'bgpstream_eventid': self.event_id,
            })

        return accomplices


class HijackEvent(BGPEvent):
    """
    Class for 'bgp_hijack' BGPStream events.

    """
    def get_culprit(self):
        """
        Get the culprit of the leak.

        """
        return {
            'asn': int(self.origin_asn),
            'prefix': self.hijack_announced_prefix,
            'start_time': self.curated_start_time,
            'end_time': self.curated_end_time,
            'weight': 1.0,
            'duration': self.duration,
            'bgpstream_eventid': self.event_id,
        }

    def get_accomplices(self):
        """
        Get all the accomplices.

        All the ASNs in the reported AS Path except from the culprit and the
        reporter are considered accomplices. The weight for is significantly
        reduced the further away they are from the culprit.

        """
        accomplices = []
        # The last ASN in the path is the reporter and the first is the
        # hijacker; ignore them.
        asns_in_path = self.hijack_as_path.split()[1:-1]
        if not asns_in_path:
            return accomplices

        hijacked_to = asns_in_path[-1]
        accomplices.append({
            'asn': int(hijacked_to),
            'prefix': self.hijack_announced_prefix,
            'start_time': self.curated_start_time,
            'end_time': self.curated_end_time,
            'weight': 1.0,
            'duration': self.duration,
            'bgpstream_eventid': self.event_id,
        })

        if not ASPATH_ONLY_NEXT_HOP_AS_ACCOMPLICE:
            hijacked_to_index = asns_in_path.index(hijacked_to)
            unique_ordered_asns = OrderedDict()
            for asn in reversed(asns_in_path[:hijacked_to_index]):
                unique_ordered_asns[asn] = None
            for asn in unique_ordered_asns:
                accomplices.append({
                    'asn': int(asn),
                    'prefix': self.hijack_announced_prefix,
                    'start_time': self.curated_start_time,
                    'end_time': self.curated_end_time,
                    'weight': next(self.weight_generator),
                    'duration': self.duration,
                    'bgpstream_eventid': self.event_id,
                })

        return accomplices

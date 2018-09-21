# Copyright: 2018, ISOC and the MANRS benchmarking tool contributors
# SPDX-License-Identifier: AGPL-3.0-only

from datetime import datetime
import logging

from manrs.settings import *

logger = logging.getLogger(__name__)

# For details on what the metrics in this file represent see the relevant
# documentation file in doc/Metrics.{rst, pdf}

def _stringify_datetimes(dictionary):
    """
    If an item is an instance of datetime replace it with the isoformat for
    JSON serialisation.

    """
    for key in dictionary:
        if isinstance(dictionary[key], datetime):
            dictionary[key] = dictionary[key].isoformat()


def _calculate_weighted_duration(events):
    """
    Create incidents from continuous events and weight them based on their
    combined duration. Note that only events that share the same weight can
    form an incident.

    More specifically:

    An incident is considered to be one or multiple events that happen at the
    same time span. These events could happen at the same time and/or may
    also be a chain of events.

    Each incident is normalized based on duration and weight like so:
        - 0,                duration == 0;
        - 0.5 * weight,     duration < INCIDENT_ACCEPTABLE_DURATION;
        - 1.0 * weight,     duration < INCIDENT_TOLERANT_DURATION;
        - 1.0 * weight * 2, penalty for every INCIDENT_TOLERANT_DURATION.

    The total is then the sum of all the incident's score.

    """
    incidents = {}
    incident_id = 0
    for event in events:
        keep_looking = True
        curr_incident = {
            'start_time': event['start_time'],
            'end_time':event['end_time'],
            'weight': event['weight'],
        }
        _stringify_datetimes(event)
        while keep_looking:
            for id, incident in incidents.items():
                # Events sharing an incident need to have the same weight.
                if curr_incident['weight'] != incident['weight']:
                    continue
                # curr_incident is not touching this incident; continue
                elif (
                    curr_incident['start_time'] < incident['start_time']
                    and curr_incident['end_time'] < incident['start_time']
                    or (curr_incident['start_time'] > incident['end_time']
                        and curr_incident['end_time'] > incident['end_time'])):
                    logger.debug("new")
                    continue
                # curr_incident is within this incident;
                # ignore curr_incident
                elif (curr_incident['start_time'] > incident['start_time']
                        and curr_incident['end_time'] < incident['end_time']):
                    logger.debug("ignore")
                    keep_looking = False
                    break
                # need to merge these incidents
                # remove incident and keep looking in case another incident
                #  may now be merged
                else:
                    curr_incident['start_time'] = min(
                        curr_incident['start_time'], incident['start_time'])
                    curr_incident['end_time'] = max(
                        curr_incident['end_time'], incident['end_time'])
                    logger.debug("Popping: {}".format(incident))
                    incidents.pop(id)
                    break
            # No breaks, means new incident
            else:
                logger.debug("Creating: {}".format(curr_incident))
                incidents[incident_id] = curr_incident
                incident_id += 1
                keep_looking = False

    # Calculate score
    scores = []
    for _, incident in incidents.items():
        duration = (incident['end_time']
                    - incident['start_time']).total_seconds()
        if not duration:
            continue

        intolerant_num, seconds = divmod(duration, INCIDENT_TOLERANT_DURATION)
        if intolerant_num:
            if INCIDENT_INTOLERANT_PENALTY == "exponential":
                score = 2**intolerant_num
            elif INCIDENT_INTOLERANT_PENALTY == "linear":
                score = intolerant_num + 1
            else:
                logger.critical("Unknown value for INCIDENT_INTOLERANT_PENALTY"
                                ": '{}'".format(INCIDENT_INTOLERANT_PENALTY))
        else:
            if seconds < INCIDENT_ACCEPTABLE_DURATION:
                score = INCIDENT_ACCEPTABLE_SCORE
            else:
                score = INCIDENT_TOLERANT_SCORE
        score *= incident['weight']
        scores.append(score)

    return sum(scores)


def _update_results_m1(asns, results, bgp_stream_results):
    """
    Calculate metric m1 and also attach the appropriate data.

    """
    logger.info("Calculating m1")
    for culprit in bgp_stream_results['bgp_leak']['culprits']:
        if culprit['asn'] in asns:
            asn = culprit.pop('asn')
            results[asn]['m1_data'].append(culprit)
    for asn, result in results.items():
        result['m1'] = _calculate_weighted_duration(result['m1_data'])


def _update_results_m1c(asns, results, bgp_stream_results):
    """
    Calculate metric m1c and also attach the appropriate data.

    """
    logger.info("Calculating m1c")
    for accomplice in bgp_stream_results['bgp_leak']['accomplices']:
        if accomplice['asn'] in asns:
            asn = accomplice.pop('asn')
            results[asn]['m1c_data'].append(accomplice)
    for asn, result in results.items():
        result['m1c'] = _calculate_weighted_duration(result['m1c_data'])


def _update_results_m2(asns, results, bgp_stream_results):
    """
    Calculate metric m2 and also attach the appropriate data.

    """
    logger.info("Calculating m2")
    for culprit in bgp_stream_results['bgp_hijack']['culprits']:
        if culprit['asn'] in asns:
            asn = culprit.pop('asn')
            results[asn]['m2_data'].append(culprit)
    for asn, result in results.items():
        result['m2'] = _calculate_weighted_duration(result['m2_data'])


def _update_results_m2c(asns, results, bgp_stream_results):
    """
    Calculate metric m2c and also attach the appropriate data.

    """
    logger.info("Calculating m2c")
    for accomplice in bgp_stream_results['bgp_hijack']['accomplices']:
        if accomplice['asn'] in asns:
            asn = accomplice.pop('asn')
            results[asn]['m2c_data'].append(accomplice)
    for asn, result in results.items():
        result['m2c'] = _calculate_weighted_duration(result['m2c_data'])


def _update_results_m3(asns, results, cidr_results):
    """
    Calculate metric m3 and also attach the appropriate data.

    Because data is gathered daily from CIDR report the minimum duration of an
    incident is 1 day.

    """
    logger.info("Calculating m3")
    for asn, prefixes in cidr_results['bogon_prefixes']['culprits'].items():
        if asn in asns:
            results[asn]['m3_data'].extend(prefixes)
    for asn, result in results.items():
        result['m3'] = _calculate_weighted_duration(result['m3_data'])


def _update_results_m6_m7irr_m8(asns, results, ripestat_results):
    """
    Calculate metrics m6, m7irr and m8 and also attach the appropriate data.

    Because the same data source is used for these metrics they are all
    calculated together for efficiency.

    """
    logger.info("Calculating m6 / m7irr / m8")
    for asn, data in ripestat_results.items():
        # m6
        m6_data = data['imports_exports']
        results[asn]['m6_data'] = m6_data
        has_imports = m6_data['has_imports']
        has_exports = m6_data['has_exports']
        if has_imports is not None and has_exports is not None:
            if not (has_imports and has_exports):
                results[asn]['m6'] = False
            else:
                results[asn]['m6'] = True

        # m7irr
        m7irr_data = data['unregistered_routes']
        results[asn]['m7irr_data'] = m7irr_data
        total_routes_num = m7irr_data['total_routes_num']
        unregistered_routes_num = m7irr_data['unregistered_routes_num']
        if (unregistered_routes_num is not None
                and total_routes_num is not None):
            if total_routes_num == 0:
                if unregistered_routes_num:
                    results[asn]['m7irr'] = 0.0
                else:
                    results[asn]['m7irr'] = 1.0
            else:
                results[asn]['m7irr'] = (
                    (1 - unregistered_routes_num / total_routes_num))

        # m8
        m8_data = data['contact_info']
        results[asn]['m8_data'] = m8_data
        results[asn]['m8'] = m8_data['has_contact_info']


def get_results_per_asn(asns,
                        bgp_stream_results,
                        cidr_results,
                        ripestat_results):
    """
    Based on the gathered data calculate metrics and also return only the
    data that were essential in calculating the metrics.

    """
    results = {}
    for asn in asns:
        results[asn] = {
            'm1': 0,
            'm1c': 0,
            'm2': 0,
            'm2c': 0,
            'm3': 0,
            'm6': None,
            'm7irr': None,
            'm8': None,
            'm1_data': [],
            'm1c_data': [],
            'm2_data': [],
            'm2c_data': [],
            'm3_data': [],
            'm6_data': [],
            'm7irr_data': [],
            'm8_data': [],
        }
    _update_results_m1(asns, results, bgp_stream_results)
    _update_results_m1c(asns, results, bgp_stream_results)
    _update_results_m2(asns, results, bgp_stream_results)
    _update_results_m2c(asns, results, bgp_stream_results)
    _update_results_m3(asns, results, cidr_results)
    _update_results_m6_m7irr_m8(asns, results, ripestat_results)
    return results

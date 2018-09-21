# Copyright: 2018, ISOC and the MANRS benchmarking tool contributors
# SPDX-License-Identifier: AGPL-3.0-only

from datetime import date, datetime, timedelta
import ipaddress
import logging
import json
from timeit import default_timer

import aiohttp
import asyncio
import requests

from manrs.util import tries


class RIPEstatError(Exception):
    """
    General error for RIPEstat.

    """
    pass


class RIPEstatChangedVersionError(RIPEstatError):
    """
    Error indicating a version change for a data call.

    """
    pass


class RIPEstatSourceData(object):
    CONCURRENCY_LIMIT = 8
    DATA_CALLS = {
        'as_routing_consistency': {
            'url': (
                "https://stat.ripe.net/data/as-routing-consistency/data.json?"
                "preferred_version={version}"
                "&sourceapp=nlnetlabs_manrs"
                "&resource=AS{asn}"),
            'versions_url': (
                "https://stat.ripe.net/data/as-routing-consistency/meta/"
                "versions/"),
            'version': "1.2",
        },
        'whois': {
            'url': (
                "https://stat.ripe.net/data/whois/data.json?"
                "preferred_version={version}"
                "&sourceapp=nlnetlabs_manrs"
                "&resource=AS{asn}"),
            'versions_url': "https://stat.ripe.net/data/whois/meta/versions/",
            'version': "4.1",
        },
    }

    def __init__(self, asns):
        """
        Class to handle communication/parsing for the RIPEstat data source.

        Data is gathered from RIPEstat's data calls.
        There are no sanity checks on the data returned from the data calls as
        they rely on a given version of their API.

        If the known version is no longer the default version a warning will be
        logged. If the known version is no longer part of the API a
        `RIPEstatChangedVersionError` will be raised.

        """
        self.logger = logging.getLogger(__name__)
        self.logger.info("Starting module")
        self.asns = asns
        self.checked_on = date.today().isoformat()
        self.data = None

    async def _fetch_url(self, semaphore, session, url, asn):
        """
        Fetch the data. In case we didn't get a successful answer (HTTP 200)
        retry before answering with None.

        .. note:: Even with the retry data calls which need to return a lot of
        data may still return an HTTP 500 error from ripestat due to the
        servers' overreaching their capacity.

        """
        async with semaphore:
            for _ in tries(3, self.logger, "_fetch_url"):
                async with session.get(url) as response:
                    if response.status == 200:
                        res = await response.json()
                        return (asn, res)

            self.logger.warning("{} error for '{}'"
                                "".format(response.status, url))
            return (asn, None)

    async def _async_resolve(self, queries, data, data_call):
        """
        Resolve the queries and update the data dictionary with the results.

        Uses a BoundedSemaphore to limit the number of concurrent connections
        to the ripestat servers.

        As a precaution in case the session in invalidaded by the ripestat
        servers it will try again.

        """
        exception = None
        for _ in tries(3, self.logger, "_async_resolve"):
            try:
                semaphore = asyncio.BoundedSemaphore(self.CONCURRENCY_LIMIT)
                async with aiohttp.ClientSession() as session:
                    futures = [self._fetch_url(semaphore, session, url, asn)
                               for asn, url in queries]
                    for i, future in enumerate(asyncio.as_completed(futures)):
                        asn, res = await future
                        data[asn][data_call] = res
                exception = None
                break
            except aiohttp.ClientError as e:
                exception = e
        if exception:
            raise exception

    def _update_data(self, data_call, data):
        """
        Build the needed queries and an async loop to fetch the data
        asynchronously usign the data_call.

        """
        api_url = self.DATA_CALLS[data_call]['url']
        api_version = self.DATA_CALLS[data_call]['version']
        queries = [(asn, api_url.format(asn=asn, version=api_version))
                   for asn in self.asns]

        loop = asyncio.get_event_loop()
        loop.run_until_complete(self._async_resolve(queries, data,
                                                    data_call))

    def _update_as_routing_consistency_data(self, data):
        """
        Update the data dictionary with data from the as_routing_consinstency
        data call.

        """
        self._update_data('as_routing_consistency', data)

    def _update_whois_data(self, data):
        """
        Update the data dictionary with data from the whois data call.

        """
        self._update_data('whois', data)

    def _check_data_call_version(self):
        """
        Check that versions of the data calls we support are still supported
        by ripestat.

        """
        for name, data_call in self.DATA_CALLS.items():
            supported_version = data_call['version']
            versions_url = data_call['versions_url']
            meta = requests.get(versions_url).json()
            is_supported = False
            if meta['default_version'] != supported_version:
                logging.warning(
                    "Version '{}' for '{}' is no longer the default version! "
                    "Consider updating the data call's definition in "
                    "ripestat.py.".format(supported_version, name))
            for version in meta['versions']:
                if version == supported_version:
                    is_supported = True
                    break
            if is_supported:
                continue
            raise RIPEstatChangedVersionError(
                "Version '{}' for '{}' is no longer available! "
                "You need to update the data call's definition in ripestat.py."
                "".format(supported_version, name))

    def fetch_data(self):
        """
        Fetch all the required data.

        """
        self.logger.info("Gathering and parsing data")
        self._check_data_call_version()
        data = {}
        for asn in self.asns:
            data[asn] = {}
        self._update_as_routing_consistency_data(data)
        self._update_whois_data(data)
        self.data = data

    def _get_whois_result(self, asn, data):
        """
        Check the whois data and return if the ASN has contact information
        properly registered.

        """
        result = {
            'has_contact_info': None,
            'checked_on': self.checked_on,
        }
        if not data:
            return result

        no_contact = True
        contact_keys = {
            'ripe': ['admin-c', 'tech-c'],
            'apnic': ['admin-c', 'tech-c'],
            'afrinic': ['admin-c', 'tech-c'],
            'arin': ['OrgTechRef', 'OrgNocRef'],
        }
        is_lacnic = False
        search_keys = set()
        for authority in data['data']['authorities']:
            if authority == "lacnic":
                is_lacnic = True
            else:
                search_keys.update(contact_keys[authority])

        if search_keys:
            for whois_records in data['data']['records']:
                for record in whois_records:
                    if record['key'] in search_keys and record['value']:
                        no_contact = False
                        break
                if not no_contact:
                    break

        if is_lacnic and no_contact:
            for whois_records in data['data']['records']:
                person = False
                email = False
                phone = False
                for record in whois_records:
                    if record['value']:
                        if record['key'] == 'person':
                            person = True
                        elif record['key'] == 'email':
                            email = True
                        elif record['key'] == 'phone':
                            phone = True
                if person and any([email, phone]):
                    no_contact = False
                    break

        result['has_contact_info'] = not no_contact
        return result

    def _get_as_routing_consistency_result(self, asn, data):
        """
        Check the as_routing_consistency data and return if the ASN has
        registered imports and exports and the status of the registered routes.

        """
        result = {
            'imports_exports': {
                'has_imports': None,
                'has_exports': None,
                'checked_on': self.checked_on
            },
            'unregistered_routes': {
                'total_routes_num': None,
                'unregistered_routes_num': None,
                'unregistered_routes': None,
                'checked_on': self.checked_on
            },
        }
        if not data:
            return result

        # Check imports
        no_imports = True
        for import_record in data['data']['imports']:
            if import_record['in_whois']:
                no_imports = False
                break
        result['imports_exports']['has_imports'] = not no_imports

        # Check exports
        no_exports = True
        for export_record in data['data']['exports']:
            if export_record['in_whois']:
                no_exports = False
                break
        result['imports_exports']['has_exports'] = not no_exports

        # Check unregistered routes
        registered = []
        unregistered = []
        for prefix_record in data['data']['prefixes']:
            prefix = prefix_record['prefix']
            if prefix_record['in_whois']:
                registered.append(prefix)
            else:
                unregistered.append(prefix)
        # Check if the unregistered is just a more specific advertisement
        # of a registered prefix.
        unregistered_routes = []
        registered_networks = []
        if unregistered:
            registered_networks = [ipaddress.ip_network(x) for x in registered]
        for prefix in unregistered:
            is_more_specific = False
            ip_network = ipaddress.ip_network(prefix)
            for other_network in registered_networks:
                if ip_network.version != other_network.version:
                    continue
                if (other_network.overlaps(ip_network)
                        and not ip_network == other_network):
                    is_more_specific = True
                    break
            if not is_more_specific:
                unregistered_routes.append(prefix)
        result['unregistered_routes']['unregistered_routes'] = (
            unregistered_routes)
        result['unregistered_routes']['total_routes_num'] = (
            len(registered) + len(unregistered))
        result['unregistered_routes']['unregistered_routes_num'] = (
            len(unregistered_routes))

        return result

    def get_results(self):
        """
        Parse the data and return results per ASN.

        """
        self.logger.info("Getting results")
        results = {}
        for asn in self.asns:
            results[asn] = {}
            whois_data = self.data[asn]['whois']
            routing_data = self.data[asn]['as_routing_consistency']
            whois_result = self._get_whois_result(asn, whois_data)
            routing_result = self._get_as_routing_consistency_result(
                asn, routing_data)

            results[asn]['contact_info'] = whois_result
            for check in routing_result:
                results[asn][check] = routing_result[check]
        self.logger.info("Done")
        return results

# Copyright: 2018, ISOC and the MANRS benchmarking tool contributors
# SPDX-License-Identifier: AGPL-3.0-only

#-- Settings for ASNs found in reported AS-PATHS
ASPATH_ONLY_NEXT_HOP_AS_ACCOMPLICE = True


#-- Weight generator settings
# Used to calculate weights for ASNs found in
# the AS-PATH. ASNs furhter away from the culprit get lower weights.
# Current supported types:
# - geometric (uses geometric progression; n = (n-1)* interval)
# Only works if the ASPATH_ONLY_NEXT_HOP_AS_ACCOMPLICE setting above is set to
# False.
WEIGHT_GENERATOR_TYPE = "geometric"
WEIGHT_GENERATOR_INTERVAL = 0.5
WEIGHT_GENERATOR_START = 1.0 * WEIGHT_GENERATOR_INTERVAL
WEIGHT_GENERATOR_END = 0.01


#-- Settings for the CIDR report locally stored data.
CIDR_DATA_DIRECTORY = "cidr/data"
BOGON_PREFIX_FILENAME = "bogon_prefixes.txt"


#-- Settings for weighting incidents based on their duration.
INCIDENT_ACCEPTABLE_DURATION = 1800  # 30 mins
INCIDENT_ACCEPTABLE_SCORE = 0.5
INCIDENT_TOLERANT_DURATION = 86400  # 24 hours
INCIDENT_TOLERANT_SCORE = 1.0
# available values: (linear, exponential)
INCIDENT_INTOLERANT_PENALTY = "linear"

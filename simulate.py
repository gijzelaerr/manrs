#!/usr/bin/env python3

from dateutil.relativedelta import relativedelta
from datetime import datetime
from random import random, sample, choice
from typing import Iterable, List
from argparse import ArgumentParser
import logging

from sqlalchemy.orm import sessionmaker
from sqlalchemy import func
import numpy as np

from manrs.models import Report, Result
import config

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)-8s %(message)s',)

Session = sessionmaker(config.DB_ENGINE)

month = relativedelta(months=1)


def get_asns(session: Session):
    asns = session.query(Result.asn).distinct().all()
    logger.info(f"Fetched {len(asns)} from the database")
    return [i[0] for i in asns]


def get_reports(session: Session):
    reports = session.query(Report.id, Report.period_start).all()
    logger.info(f"Fetched {len(reports)} from the database")
    return reports


def get_last_report(session: Session):
     return session.query(func.max(Report.period_start)).one()[0]


def gen_dates(start: datetime, number: int):
    cursor = start
    # while cursor < datetime.now() + relativedelta(years=1):
    for _ in range(number):
        cursor += month
        yield cursor


def sampler(mu: float, sigma: float, num: int) -> np.array:
    """
    samples from a random distribution and clips values below 0
    """
    if mu == np.nan or sigma == np.nan:
        return [None] * num

    samples = np.random.normal(mu, sigma, num)
    return np.clip(samples, a_min=0, a_max=None)


def get_old_reports(session: Session):
    reports = session.query(Report).all()
    logger.info(f"Fetched {len(reports)} old reports from database")
    return reports


def generate_reports(new_dates: Iterable[datetime]):
    """"Add new fanasy reports to the database"""
    reports = []
    for date in new_dates:
        end = date + month
        report = Report(period_start=date, period_end=end, date_finished=end, type="auto")
        reports.append(report)
    return reports


def get_stats(session: Session, asn: int):
    """Build up a statistical model of a specific asn"""
    R = Result  # simple shortcut alias
    float_rows = session.query(R.m1, R.m1c, R.m2, R.m2c, R.m3, R.m7irr).filter(Result.asn == asn).all()
    array = np.array(float_rows, dtype=float)
    mu = np.nanmean(array, axis=0)
    sigma = np.nanstd(array, axis=0)
    
    bool_rows = session.query(R.m6, R.m8).filter(Result.asn == asn).all()
    m6, m8 = list(zip(*bool_rows))
    
    m6_total = sum(type(i) == bool for i in m6)
    if m6_total:
        m6_ratio = sum(bool(i) for i in m6) / m6_total
    else:
        m6_ratio = 0
    
    m8_total = sum(type(i) == bool for i in m8)
    if m8_total:
        m8_ratio = sum(bool(i) for i in m8) / m8_total
    else:
        m8_ratio = 0
        
    return mu, sigma, m6_ratio, m8_ratio


def generate_stats(reports: List[Report], asn: int, mu: List[float], sigma: List[float],
                   m6_ratio: float, m8_ratio: float):
    """
    Simulates datapoints for a ASN for every report based on the stats defined in mu and sigma arrays.
    """
    num = len(reports)
    logger.info(f"Generating datapoints for ASN {asn} and with {num} reports")
    
    m1s    = sampler(mu[0], sigma[0], num)
    m1cs   = sampler(mu[1], sigma[1], num)
    m2s    = sampler(mu[2], sigma[2], num)
    m2cs   = sampler(mu[3], sigma[3], num)
    m3s    = sampler(mu[4], sigma[4], num)
    m7irrs = sampler(mu[5], sigma[5], num)
    
    m6s = (random() < m6_ratio for _ in range(num))
    m8s = (random() < m8_ratio for _ in range(num))

    # 99% of ASN have an m4 of 0, 1% in a value between 1 and 100
    if random() < 0.99:
        m4s = [0] * num
    else:
        m4s = (random() * 100 for _ in range(num))

    # 10% of ASNs have m5=0, 80% 0.5 and 10% between 1 and 4
    m5_random = random()
    if m5_random < 0.1:
        m5s = [0] * num
    elif 0.1 < m5_random < 0.9:
        m5s = [0.5] * num
    else:
        m5s = (1 + (random() * 3) for _ in range(num))

    # 10% of ASNs have mc5 = 0, 70% 0.5 and 20% between 1 and 20
    m5c_random = random()
    if m5c_random < 0.1:
        m5cs = [0] * num
    elif 0.1 < m5c_random < 0.8:
        m5cs = [0.5] * num
    else:
        m5cs = (1 + (random() * 19) for _ in range(num))

    # 70% of ASN have an m7rpki of 1, 5% in a value between 0 and 0.5
    if random() < 0.7:
        m7rpkis = [1] * num
    else:
        m7rpkis = (random() / 2. for _ in range(num))

    # 98% of ASN have an m7rpkin of 0, 2% in a value between 0.1 and 0.2
    if random() < 0.7:
        m7rpkins = [1] * num
    else:
        m7rpkins = (random() / 2. for _ in range(num))

    zipped = zip(reports, m1s, m1cs, m2s, m2cs, m3s, m4s, m5s, m5cs, m6s, m7irrs, m7rpkis, m7rpkins, m8s)
    
    results = []
    for report, m1, m1c, m2, m2c, m3, m4, m5, m5c, m6, m7irr, m7rpki, m7rpkin, m8 in zipped:
        results.append(Result(asn=asn, report=report, m1=m1, m1c=m1c, m2=m2, m2c=m2c, m3=m3, m4=m4, m5=m5, m5c=m5c,
                              m6=m6, m7irr=m7irr, m7rpki=m7rpki, m7rpkin=m7rpkin, m8=m8))
    return results
        

def generate_new_reports(session: Session, new_dates: List[datetime], asns: List[int]):
    """
    generate new reports objects in the database. For every date and ASN given it will create an entry in
    the results table
    """
    reports = generate_reports(new_dates)
    session.add_all(reports)

    results = []
    for asn in asns:
        mu, sigma, m6_ratio, m8_ratio = get_stats(session, asn)
        results += generate_stats(reports, asn, mu, sigma, m6_ratio, m8_ratio)
    return results


def get_all_stats(session: Session, asns: List[int]):
    """
    returns all statistical values for the given list of ASNs
    """
    logger.info(f"Gathering statistics for {len(asns)} ASNs" )
    all_stats = []
    for asn in asns:
        all_stats.append(get_stats(session, asn))
    return all_stats


def generate_asn_data(asn_stats: List, real_asns: List[int], reports: List[Report], min_: int=0, max_: int=65000,
                      amount: int=60000):
    """
    Generate new ASN data based on a list of existing ASNs
    """
    # generate new ASNs, making sure we don't have duplicates
    logger.info(f"Generating list of {amount} ASNs from the range {min_} to {max_} while skipping "
                f"{len(real_asns)} existing ASns")

    if amount == 0:
        new_asns = set(range(min_, max_)) - set(real_asns)
    else:
        try:
            new_asns = sample(set(range(min_, max_)) - set(real_asns), amount)
        except ValueError:
            logger.error(f"Not enough free ASNs in range {min_}-{max_}! Number of existing ASNs: {len(real_asns)}")
            return []

    results = []
    logger.info("Generating statistics and reports for each ASN")
    for asn in new_asns:
        mu, sigma, m6_ratio, m8_ratio = choice(asn_stats)
        results += generate_stats(reports, asn, mu, sigma, m6_ratio, m8_ratio)
    return results


def asns_subcommand(args):
    # generate new ASN data
    logger.info(f"Generating fake data for {args.number} ASNs")
    session = Session()
    old_reports = get_old_reports(session)
    asns = get_asns(session)
    asn_stats = get_all_stats(session, asns)
    results = generate_asn_data(asn_stats, asns, old_reports, min_=args.min, max_=args.max, amount=args.number)
    session.add_all(results)
    logger.info(f"Inserting {len(results)} new rows to the results")
    if args.commit:
        logger.info("committed. bye.")
        session.commit()
    else:
        logger.warning("Not committing changes to database, supply -c to commit")


def reports_subcommand(args):
    session = Session()
    logger.info(f"Generating {args.number} new reports")
    last_report = get_last_report(session)
    logger.info(f"Last report in database has timestamp {last_report}")
    new_dates = list(gen_dates(last_report, args.number))
    asns = get_asns(session)
    logger.warning(f"Going to create reports for {len(new_dates)} dates and {len(asns)} ASNs, "
                   f"starting at {new_dates[0]} and ending at {new_dates[-1]}.")
    asns = get_asns(session)
    results = generate_new_reports(session, new_dates, asns)
    session.add_all(results)
    logger.info(f"Inserting {len(results)} new rows to the database")
    if args.commit:
        logger.info("committed. bye.")
        session.commit()
    else:
        logger.warning("Not committing changes to database, supply -c to commit")


def parse():
    parser = ArgumentParser()
    subparsers = parser.add_subparsers(title='subcommands',
                                       description='valid subcommands',
                                       help='additional help')

    parser.set_defaults(func=lambda x: parser.print_help())

    asn_parser = subparsers.add_parser('asns')
    asn_parser.add_argument('-n', '--number', type=int, help='Number of ASNs you want to simulate, '
                                                             'set to 0 for full range', default=60000)
    asn_parser.add_argument('-i', '--min', type=int, help='Minimum ASN number', default=0)
    asn_parser.add_argument('-a', '--max', type=int, help='Maximum ASN number', default=65000)
    asn_parser.add_argument('-c', '--commit', help='Commit changes to database', action='store_true')
    asn_parser.set_defaults(func=asns_subcommand)

    result_parser = subparsers.add_parser('results')
    result_parser.add_argument('-n', '--number', type=int, help='Number of results you want to simulate', default=10)
    result_parser.add_argument('-c', '--commit', help='Commit changes to database', action='store_true')
    result_parser.set_defaults(func=reports_subcommand)

    args = parser.parse_args()
    args.func(args)


if __name__ == '__main__':
    parse()
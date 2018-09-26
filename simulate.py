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
logging.basicConfig(level=logging.INFO)

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


def sampler(mu: float, sigma: float, num: int):
    """
    samples from a random distribution and clips values below 0
    """
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
    mu = np.mean(array, axis=0)
    sigma = np.std(array, axis=0)
    
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
    
    m6 = (random() < m6_ratio for _ in range(num))
    m8 = (random() < m8_ratio for _ in range(num))
    
    zipped = zip(reports, m1s, m1cs, m2s, m2cs, m3s, m6, m7irrs, m8)
    
    results = []
    for report, m1, m1c, m2, m2c, m3, m6, m7irr, m8 in zipped:
        results.append(Result(asn=asn, report=report, m1=m1, m1c=m1c, m2=m2,
                              m2c=m2c, m3=m3, m6=m6, m7irr=m7irr, m8=m8))
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

    asn_parser = subparsers.add_parser('asns')
    asn_parser.add_argument('-n', '--number', type=int, help='Number of ASNs you want to simulate', default=60000)
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
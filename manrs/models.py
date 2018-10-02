# Copyright: 2018, ISOC and the MANRS benchmarking tool contributors
# SPDX-License-Identifier: AGPL-3.0-only

import enum

from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import Column, ForeignKey
from sqlalchemy import Boolean, Integer, String, DateTime, Enum, Float
from sqlalchemy.orm import relationship
from sqlalchemy.schema import ForeignKeyConstraint
from sqlalchemy.dialects.postgresql import JSONB

Base = declarative_base()


class Result(Base):
    __tablename__ = 'results'

    asn = Column(Integer, primary_key=True)
    report_id = Column(Integer, ForeignKey('reports.id'), primary_key=True)
    m1 = Column(Float)
    m1_data = Column(JSONB)
    m1c = Column(Float)
    m1c_data = Column(JSONB)
    m2 = Column(Float)
    m2_data = Column(JSONB)
    m2c = Column(Float)
    m2c_data = Column(JSONB)
    m3 = Column(Float)
    m3_data = Column(JSONB)
    m4 = Column(Float)
    m4_data = Column(JSONB)
    m5 = Column(Float)
    m5_data = Column(JSONB)
    m5c = Column(Float)
    m5c_data = Column(JSONB)
    m6 = Column(Boolean)
    m6_data = Column(JSONB)
    m7irr = Column(Float)
    m7irr_data = Column(JSONB)
    m7rpki = Column(Float)
    m7rpki_data = Column(JSONB)
    m7rpkin = Column(Float)
    m7rpkin_data = Column(JSONB)
    m8 = Column(Boolean)
    m8_data = Column(JSONB)

    report = relationship("Report", back_populates="results")

    @classmethod
    def valid_metrics(cls):
        return ['m1', 'm1c', 'm2', 'm2c', 'm3', 'm4', 'm5', 'm5c', 'm6', 'm7irr', 'm7rpki', 'm7rpkin, ''m8']


class ReportType(enum.Enum):
    auto = 1
    manual = 2


class Report(Base):
    __tablename__ = 'reports'

    id = Column(Integer, primary_key=True)
    period_start = Column(DateTime)
    period_end = Column(DateTime)
    date_started = Column(DateTime)
    date_finished = Column(DateTime)
    type = Column(Enum(ReportType))

    results = relationship("Result",
                           order_by=Result.report_id,
                           back_populates="report")
    stats = relationship("GlobalStats",
                         back_populates="report")


class GlobalStats(Base):
    __tablename__ = 'global_stats'

    report_id = Column(Integer, primary_key=True)
    m1_mean = Column(Float)
    m1_median = Column(Float)
    m1c_mean = Column(Float)
    m1c_median = Column(Float)
    m2_mean = Column(Float)
    m2_median = Column(Float)
    m2c_mean = Column(Float)
    m2c_median = Column(Float)
    m3_mean = Column(Float)
    m3_median = Column(Float)
    m4 = Column(Float)
    m4_data = Column(JSONB)
    m5 = Column(Float)
    m5_data = Column(JSONB)
    m5c = Column(Float)
    m5c_data = Column(JSONB)
    m6_mode = Column(Boolean)
    m7irr_mean = Column(Float)
    m7irr_median = Column(Float)
    m7rpkis = Column(Float)
    m7rpkis_data = Column(JSONB)
    m7rpkin = Column(Float)
    m7rpkin_data = Column(JSONB)
    m8_mode = Column(Boolean)

    report = relationship("Report", back_populates="stats")

    __table_args__ = (ForeignKeyConstraint(('report_id', ), [Report.id]),)

    @classmethod
    def get_statistics_calculations(cls):
        return {
            'm1': ['mean', 'median'],
            'm1c': ['mean', 'median'],
            'm2': ['mean', 'median'],
            'm2c': ['mean', 'median'],
            'm3': ['mean', 'median'],
            'm4': ['mean', 'median'],
            'm5': ['mean', 'median'],
            'm5c': ['mean', 'median'],
            'm6': ['mode'],
            'm7irr': ['mean', 'median'],
            'm7rpki': ['mean', 'median'],
            'm7rpkin': ['mean', 'median'],
            'm8': ['mode'],
        }

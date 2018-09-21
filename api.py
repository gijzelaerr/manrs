# Copyright: 2018, ISOC and the MANRS benchmarking tool contributors
# SPDX-License-Identifier: AGPL-3.0-only

from collections import defaultdict
from contextlib import contextmanager
from datetime import datetime
import logging
from wsgiref import simple_server

import falcon
from sqlalchemy import and_
from sqlalchemy.orm import sessionmaker, joinedload

from manrs.models import Report, ReportType, Result, GlobalStats
import config


class StorageInterface(object):
    """
    Class interfacing with the DB.

    It has its own session maker so that every query can create its own session
    for the request/response cycle.

    """
    def __init__(self, engine):
        self._Session = sessionmaker(engine)
        self.logger = logging.getLogger(__name__ + self.__class__.__name__)

    @contextmanager
    def session_scope(self):
        """
        Provide a transactional scope around a series of operations.

        """
        session = self._Session()
        try:
            yield session
            session.commit()
        except Exception as e:
            session.rollback()
            raise e
        finally:
            session.close()

    def get_reports(self, session, period_start, period_end, asns, type):
        """
        Get all the reports between period_start and period_end.

        If ASNs are given filter the reports that include any of the ASNs.

        """
        query = (session.query(Report)
                 .filter(and_(Report.period_start >= period_start,
                              Report.period_end <= period_end)))
        if type:
            query = query.filter(Report.type == type)
        if asns:
            query = query.join(Result).filter(Result.asn.in_(asns))

        try:
            reports = query.all()
        except Exception as e:
            self.logger.error("{}: {}".format(e.__class__.__name__, e))
            self.logger.error("DB access error!")
            description = "Resource currently unavailable."
            raise falcon.HTTPServiceUnavailable(
                'Service Outage',
                description,
                60)

        res = []
        for report in reports:
            date_started = report.date_started
            if date_started:
                date_started = date_started.isoformat()
            res.append({
                'id': report.id,
                'period_start': report.period_start.isoformat(),
                'period_end': report.period_end.isoformat(),
                'type': report.type.name,
                'date_started': date_started,
                'date_finished': report.date_finished.isoformat(),
            })
        return res

    def get_report(self, session, id):
        """
        Get report by id.

        """
        try:
            report = session.query(Report).get(id)
        except Exception as e:
            self.logger.error("{}: {}".format(e.__class__.__name__, e))
            self.logger.error("DB access error!")
            description = "Resource currently unavailable."
            raise falcon.HTTPServiceUnavailable(
                'Service Outage',
                description,
                60)
        if not report:
            return None

        date_started = report.date_started
        if date_started:
            date_started = date_started.isoformat()
        res = {
            'id': report.id,
            'period_start': report.period_start.isoformat(),
            'period_end': report.period_end.isoformat(),
            'type': report.type.name,
            'date_started': date_started,
            'date_finished': report.date_finished.isoformat(),
        }
        return res

    def get_report_with_results(self, session, id):
        """
        Get report by id. Also attach the results.

        """
        report = self.get_report(session, id)

        try:
            results = (session.query(Result)
                       .filter(Result.report_id == id)
                       .all())
        except Exception as e:
            self.logger.error("{}: {}".format(e.__class__.__name__, e))
            self.logger.error("DB access error!")
            description = "Resource currently unavailable."
            raise falcon.HTTPServiceUnavailable(
                'Service Outage',
                description,
                60)
        if not results:
            return None

        report_results = []
        for result in results:
            report_results.append({
                x.name: getattr(result, x.name)
                for x in result.__table__.columns
                if x.name != "report_id"
            })

        try:
            stats = session.query(GlobalStats).get(id)
        except Exception as e:
            self.logger.error("{}: {}".format(e.__class__.__name__, e))
            self.logger.error("DB access error!")
            description = "Resource currently unavailable."
            raise falcon.HTTPServiceUnavailable(
                'Service Outage',
                description,
                60)
        report_stats = {}
        if stats:
            report_stats.update({
                x.name: getattr(stats, x.name)
                for x in stats.__table__.columns
                if x.name != "report_id"
            })

        report['results'] = report_results
        report['stats'] = report_stats
        return report

    def get_results(self, session, period_start, period_end, asns, metrics,
                    only_metrics):
        """
        Get all the results and statistics between period_start and period_end.

        If ASNs are given filter the reports that include any of the ASNs.
        If metrics are given return only the metrics specified.
        If only_metrics is given do not return the metric's data.

        """
        # If only_metrics don't include metric's data in the query.
        requested_metrics = []
        for metric in metrics:
            requested_metrics.append(metric)
            if not only_metrics:
                requested_metrics.append("{}_data".format(metric))
        # Check which metrics we need in statistics.
        requested_stats = [
            x.name
            for x in GlobalStats.__table__.columns
            if x.name.startswith(tuple(["{}_".format(m)
                                        for m in metrics]))]

        # Construct the query based on the metrics requested.
        select_targets = [Report, Result.asn]
        select_targets.extend([getattr(Result, x) for x in requested_metrics])
        query = (session.query(*select_targets).join(Result)
                 .filter(and_(Report.period_start >= period_start,
                              Report.period_end <= period_end)))
        if asns:
            query = query.filter(Result.asn.in_(asns))

        query = query.order_by(Report.period_start)
        # Get also the GlobalStats for each Report we use, we will need them
        # later.
        query = query.options(joinedload(Report.stats))

        try:
            results = query.all()
        except Exception as e:
            self.logger.error("{}: {}".format(e.__class__.__name__, e))
            self.logger.error("DB access error!")
            description = "Resource currently unavailable."
            raise falcon.HTTPServiceUnavailable(
                'Service Outage',
                description,
                60)
        if not results:
            return None

        res = {'asns': defaultdict(list), 'stats': defaultdict(list)}
        reports_seen = set()
        for report, asn, *rest in results:
            # Get the results per ASN.
            temp = {
                    'period_start': report.period_start.isoformat(),
                    'period_end': report.period_end.isoformat(),
                   }
            temp.update({i: x for i, x in zip(requested_metrics, rest)})
            res['asns'][asn].append(temp)

            # Each Report has a GlobalStats associated with it.
            # Record it once for each unique report we see.
            if report.id not in reports_seen:
                for stat in requested_stats:
                    res['stats'][stat].append({
                        'period_start': report.period_start.isoformat(),
                        'period_end': report.period_end.isoformat(),
                        'value': getattr(report.stats[0], stat)
                    })
                reports_seen.add(report.id)

        return res


class Resource(object):
    """
    Abstract Resource class.

    """

    def __init__(self, db):
        """
        Every Resource has its own DB interface instance and logger.

        """
        self.db = db
        self.logger = logging.getLogger(__name__ + self.__class__.__name__)
        self.valid_metrics = Result.valid_metrics()

    def _sanitize_period(self, period_start, period_end):
        """
        Helper function to sanitize period_start and period_end input
        parameters.

        """
        period_start = self._sanitize_period_time(period_start)
        period_end = self._sanitize_period_time(period_end)
        if period_start >= period_end:
            description = (
                "Parameter value 'period_start' must be earlier than "
                "'period_end'.")
            raise falcon.HTTPBadRequest(
                'Invalid Input',
                description)
        return period_start, period_end

    def _sanitize_period_time(self, period_time):
        """
        Helper function to sanitize datetimes input parameters.

        """
        try:
            return datetime.strptime(period_time, "%Y-%m-%d")
        except Exception as e:
            description = (
                "Parameters 'period_start' and 'period_end' must both be"
                "present with YYYY-MM-DD format.")
            raise falcon.HTTPBadRequest(
                'Invalid Input',
                description)

    def _sanitize_report_id(self, id):
        """
        Helper function to sanitize the id input parameter.

        """
        try:
            return int(id)
        except Exception as e:
            description = "The 'id' parameter should be a valid integer."
            raise falcon.HTTPBadRequest(
                'Invalid Input',
                description)

    def _sanitize_report_type(self, type):
        """
        Helper function to sanitize the report type input parameter.

        """
        try:
            return ReportType[type]
        except Exception as e:
            description = (
                "The 'type' parameter should be one of {}."
                "".format([x for x in ReportType.__members__.keys()]))
            raise falcon.HTTPBadRequest(
                'Invalid Input',
                description)

    def _sanitize_asns(self, asns):
        """
        Helper function to sanitize the ASNs list input parameter.

        """
        description = "The 'asns' parameter needs to be a list of ASN numbers."
        if not isinstance(asns, list):
            raise falcon.HTTPBadRequest("Invalid Input", description)
        try:
            return [int(x) for x in asns]
        except Exception as e:
            raise falcon.HTTPBadRequest("Invalid Input", description)

    def _sanitize_metrics(self, metrics):
        """
        Helper function to sanitize the metrics list input parameter.

        """
        description = (
            "The 'metrics' parameter needs to be a list. Valid metrics are: {}"
            "".format(self.valid_metrics))
        if not isinstance(metrics, list):
            raise falcon.HTTPBadRequest("Invalid Input", description)
        for metric in metrics:
            if metric not in self.valid_metrics:
                raise falcon.HTTPBadRequest("Invalid Input", description)
        if not metrics:
            metrics = self.valid_metrics
        return metrics


class ReportCollection(Resource):
    """
    Resource for handling a collection of Reports.

    """

    def on_post(self, req, resp):
        """
        Get reports filtered by period, ASNs and type.
        POST is used specifically for easier input of ASNs.

        """
        period_start = req.media.get('period_start')
        period_end = req.media.get('period_end')
        asns = req.media.get('asns', [])
        type = req.media.get('type', ReportType.auto.name)

        period_start, period_end = self._sanitize_period(period_start,
                                                         period_end)
        asns = self._sanitize_asns(asns)
        type = self._sanitize_report_type(type)

        with self.db.session_scope() as session:
            reports = self.db.get_reports(
                session, period_start, period_end, asns, type)

        response = {}
        response['message'] = "OK"
        response['data'] = reports
        resp.media = response


class ReportItem(Resource):
    """
    Resource for handling an individual report.

    """

    def on_get(self, req, resp, id):
        """
        GET a report based on the report's id.

        """
        id = self._sanitize_report_id(id)
        with self.db.session_scope() as session:
            report = self.db.get_report(session, id)

        if not report:
            message = "Not Found"
            data = []
            status = falcon.HTTP_404
        else:
            message = "OK"
            data = report
            status = falcon.HTTP_200

        response = {}
        response['message'] = message
        response['data'] = data
        resp.media = response
        resp.status = status


class ReportResultsItem(Resource):
    """
    Resource for handling an individual report along with the
    report's results.

    """

    def on_get(self, req, resp, id):
        """
        GET a report based on the report's id; include also the results and
        statistics.

        """
        id = self._sanitize_report_id(id)
        with self.db.session_scope() as session:
            report = self.db.get_report_with_results(session, id)

        if not report:
            message = "Not Found"
            data = []
            status = falcon.HTTP_404
        else:
            message = "OK"
            data = report
            status = falcon.HTTP_200

        response = {}
        response['message'] = message
        response['data'] = data
        resp.media = response
        resp.status = status


class ResultCollection(Resource):
    """
    Resource for handling a collection of Results.

    """

    def on_post(self, req, resp):
        """
        Get all the results and their statistics between period_start and
        period_end.

        If ASNs are given filter the reports that include any of the ASNs.
        If metrics are given return only the metrics specified.
        If only_metrics is given do not return the metric's data.

        """
        period_start = req.media.get('period_start')
        period_end = req.media.get('period_end')
        asns = req.media.get('asns', [])
        metrics = req.media.get('metrics', [])
        only_metrics = req.media.get('only_metrics', True)

        period_start, period_end = self._sanitize_period(period_start,
                                                         period_end)
        asns = self._sanitize_asns(asns)
        metrics = self._sanitize_metrics(metrics)

        with self.db.session_scope() as session:
            results = self.db.get_results(session, period_start, period_end,
                                          asns, metrics, only_metrics)

        if not results:
            message = "Not Found"
            data = []
            status = falcon.HTTP_404
        else:
            message = "OK"
            data = results
            status = falcon.HTTP_200

        response = {}
        response['message'] = message
        response['data'] = data
        resp.media = response
        resp.status = status


app = application = falcon.API()

db = StorageInterface(config.DB_ENGINE)
reports = ReportCollection(db)
report = ReportItem(db)
report_results = ReportResultsItem(db)
results = ResultCollection(db)

app.add_route('/reports/', reports)
app.add_route('/reports/{id}', report)
app.add_route('/reports/{id}/results', report_results)
app.add_route('/results/', results)

if __name__ == "__main__":
    httpd = simple_server.make_server('127.0.0.1', 8000, app)
    httpd.serve_forever()

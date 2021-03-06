import itertools
import logging

from django.core.cache import cache
from django.db import connection

from .models import Publication
from .graphviz.data import NetworkVisualization,AggregatedDistributionVisualization

from .graphviz.globals import RelationClassifier, CacheNames, NetworkGroupByType

logger = logging.getLogger(__name__)


def initialize_contributor_cache():
    with connection.cursor() as cursor:
        # NOTE : need to change to Django ORM
        cursor.execute(
            "select p.id, u.username, COUNT(u.username) as contribution, MAX(c.date_added) as date_added from "
            "citation_publication as p inner join citation_auditlog as a on a.pub_id_id = p.id or "
            "(a.row_id = p.id and a.table='publication') inner join citation_auditcommand as c on "
            "c.id = a.audit_command_id and c.action = 'MANUAL' inner join auth_user as u on c.creator_id=u.id "
            "where p.is_primary=True group by p.id,u.username, p.title order by p.id ")
        contributor_logs = _dictfetchall(cursor)

        cursor.execute(
            "select p.id, COUNT(p.id) as count from citation_publication as p inner join citation_auditlog as a "
            "on a.pub_id_id = p.id or (a.row_id = p.id and a.table='publication') inner join citation_auditcommand as c "
            "on c.id = a.audit_command_id and c.action = 'MANUAL' inner join auth_user as u on c.creator_id=u.id "
            "where p.is_primary=True  group by p.id order by p.id ")
        contributor_count = _dictfetchall(cursor)

        # Calculates the contribution percentages and combine the above two different table values into one
        combine = []
        for log in contributor_logs:
            temp = {}
            for count in contributor_count:
                if count['id'] == log['id']:
                    temp.update(id= log['id'], contribution= "{0:.2f}".format(log['contribution'] * 100 / count['count']),
                                creator= log['username'], date_added= log['date_added'])
                    combine.append(temp)

    # Creating a dict for publication having more than one contributor
    for k, v in itertools.groupby(combine, key=lambda x: x['id']):
        ls = []
        for dct in v:
            tmp = {}
            tmp.update(dct)
            ls.append(tmp)
        cache.set(CacheNames.CONTRIBUTION_DATA.value + str(dct['id']), ls, 86410)
    logger.debug("Contribution data cache completed.")

def _dictfetchall(cursor):
    "Return all rows from a cursor as a dict"
    columns = [col[0] for col in cursor.description]
    return [
        dict(zip(columns, row))
        for row in cursor.fetchall()
    ]

""" 
    Method to cache the default distribution of publication across the year 
    along with on which platform the code is made available information
"""
def initialize_publication_code_platform_cache():
    logger.debug("Caching publication distribution data")
    aggregation = AggregatedDistributionVisualization()
    distribution_data = aggregation.get_data(RelationClassifier.GENERAL.value, "Publications")
    cache.set(CacheNames.DISTRIBUTION_DATA.value, distribution_data.data, 86410)
    cache.set(CacheNames.CODE_ARCHIVED_PLATFORM.value, distribution_data.group, 86410)
    logger.debug("Publication code platform distribution data cache completed.")

"""
    Method to cache information about how the publication are connected
"""
def initialize_network_cache():
    logger.debug("Caching Network")
    logger.debug("updated citation caching file to see it reflected or not")
    #FIXME use more informational static filters over here
    sponsors_name = Publication.api.get_top_records('sponsors__name', 5)
    sponsors_filter = {'sponsors__name__in' : sponsors_name, 'is_primary':True, 'status':'REVIEWED'}
    network = NetworkVisualization(sponsors_filter, NetworkGroupByType.SPONSOR)
    network_data = network.get_data()
    cache.set(CacheNames.NETWORK_GRAPH_GROUP_BY_SPONSORS.value, network_data.data, 86410)
    cache.set(CacheNames.NETWORK_GRAPH_SPONSOS_FILTER.value, network_data.group, 86410)
    logger.info("Network cache for group_by sponsors completed using static filter: " + str(sponsors_name))

    tags_name = Publication.api.get_top_records('tags__name', 5)
    tags_filter = {'tags__name__in': tags_name, 'is_primary':True, 'status': 'REVIEWED'}
    network = NetworkVisualization(tags_filter, NetworkGroupByType.TAGS)
    network_data = network.get_data()
    cache.set(CacheNames.NETWORK_GRAPH_GROUP_BY_TAGS.value, network_data.data, 86410)
    cache.set(CacheNames.NETWORK_GRAPH_TAGS_FILTER.value, network_data.group, 86410)
    logger.info("Network cache for group_by tags completed using static filter: " + str(tags_name))



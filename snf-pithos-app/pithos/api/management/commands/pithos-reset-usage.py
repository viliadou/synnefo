# Copyright 2012 GRNET S.A. All rights reserved.
#
# Redistribution and use in source and binary forms, with or
# without modification, are permitted provided that the following
# conditions are met:
#
#   1. Redistributions of source code must retain the above
#      copyright notice, this list of conditions and the following
#      disclaimer.
#
#   2. Redistributions in binary form must reproduce the above
#      copyright notice, this list of conditions and the following
#      disclaimer in the documentation and/or other materials
#      provided with the distribution.
#
# THIS SOFTWARE IS PROVIDED BY GRNET S.A. ``AS IS'' AND ANY EXPRESS
# OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
# WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR
# PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL GRNET S.A OR
# CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL,
# SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT
# LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF
# USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED
# AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT
# LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN
# ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.
#
# The views and conclusions contained in the software and
# documentation are those of the authors and should not be
# interpreted as representing official policies, either expressed
# or implied, of GRNET S.A.

from django.core.management.base import NoArgsCommand, CommandError

from collections import namedtuple
from optparse import make_option
from sqlalchemy import func
from sqlalchemy.sql import select, and_, or_

from pithos.api.util import get_backend
from pithos.backends.modular import (
    CLUSTER_NORMAL, CLUSTER_HISTORY, CLUSTER_DELETED
)
clusters = (CLUSTER_NORMAL, CLUSTER_HISTORY, CLUSTER_DELETED)

Statistics = namedtuple('Statistics', ('node', 'path', 'size', 'cluster'))

ResetHoldingPayload = namedtuple('ResetHoldingPayload', (
                'entity', 'resource', 'key',
                'imported', 'exported', 'returned', 'released'))
ENTITY_KEY = '1'

backend = get_backend()
table = {}
table['nodes'] = backend.node.nodes
table['versions'] = backend.node.versions
table['statistics'] = backend.node.statistics
table['policy'] = backend.node.policy
conn = backend.node.conn


def _compute_statistics(nodes):
    statistics = []
    append = statistics.append
    for path, node in nodes:
        select_children = select(
            [table['nodes'].c.node]).where(table['nodes'].c.parent == node)
        select_descendants = select([table['nodes'].c.node]).where(
            or_(table['nodes'].c.parent.in_(select_children),
                table['nodes'].c.node.in_(select_children)))
        s = select([table['versions'].c.cluster,
                    func.sum(table['versions'].c.size)])
        s = s.group_by(table['versions'].c.cluster)
        s = s.where(table['nodes'].c.node == table['versions'].c.node)
        s = s.where(table['nodes'].c.node.in_(select_descendants))
        d2 = dict(conn.execute(s).fetchall())

        for cluster in clusters:
            try:
                size = d2[cluster]
            except KeyError:
                size = 0
            append(Statistics(
                node=node,
                path=path,
                size=size,
                cluster=cluster))
    return statistics


def _get_verified_usage(statistics):
    """Verify statistics and set quotaholder account usage"""
    reset_holding = []
    append = reset_holding.append
    for item in statistics:
        s = select([table['statistics'].c.size])
        s = s.where(table['statistics'].c.node == item.node)
        s = s.where(table['statistics'].c.cluster == item.cluster)
        db_item = conn.execute(s).fetchone()
        if not db_item:
            continue
        try:
            assert item.size == db_item.size, \
                    '%d[%s][%d], size: %d != %d' % (
                            item.node, item.path, item.cluster,
                            item.size, db_item.size)
        except AssertionError, e:
            print e
        if item.cluster == CLUSTER_NORMAL:
            append(ResetHoldingPayload(
                    entity=item.path,
                    resource='pithos+.diskspace',
                    key=ENTITY_KEY,
                    imported=item.size,
                    exported=0,
                    returned=0,
                    released=0))
    return reset_holding


class Command(NoArgsCommand):
    help = "Set quotaholder account usage"

    option_list = NoArgsCommand.option_list + (
        make_option('-a',
                    dest='accounts',
                    action='append',
                    help="Account to reset quota"),
    )

    def handle_noargs(self, **options):
        try:
            if not backend.quotaholder_enabled:
                raise CommandError('Quotaholder component is not enabled')

            if not backend.quotaholder_url:
                raise CommandError('Quotaholder component url is not set')

            if not backend.quotaholder_token:
                raise CommandError('Quotaholder component token is not set')

            # retrieve account nodes
            s = select([table['nodes'].c.path, table['nodes'].c.node])
            s = s.where(and_(table['nodes'].c.node != 0,
                             table['nodes'].c.parent == 0))
            if options['accounts']:
                s = s.where(table['nodes'].c.path.in_(options['accounts']))
            account_nodes = conn.execute(s).fetchall()

            if not account_nodes:
                raise CommandError('No accounts found.')

            # compute account statistics
            statistics = _compute_statistics(account_nodes)

            # verify and send usage
            reset_holding = _get_verified_usage(statistics)

            while True:
                result = backend.quotaholder.reset_holding(
                    context={},
                    clientkey='pithos',
                    reset_holding=reset_holding)

                if not result:
                    break

                missing_entities = [reset_holding[x].entity for x in result]
                self.stdout.write(
                        'Unknown quotaholder accounts: %s\n' %
                        ', '.join(missing_entities))
                m = 'Retrying sending quota usage for the rest...\n'
                self.stdout.write(m)
                missing_indexes = set(result)
                reset_holding = [x for i, x in enumerate(reset_holding)
                                 if i not in missing_indexes]
        finally:
            backend.close()

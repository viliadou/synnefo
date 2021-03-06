# Copyright (C) 2010-2014 GRNET S.A.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import logging
from django.template import RequestContext, loader
from django.http import HttpResponseNotFound
from synnefo_admin.admin.exceptions import AdminHttp404, AdminHttp405
from synnefo_admin.admin.views import default_dict

ADMIN_404_TEMPLATE = 'admin/admin_404.html'
ADMIN_405_TEMPLATE = 'admin/admin_405.html'


def update_request_context(request, extra_context={}, **kwargs):
    """Update request context.

    Update request context as Django does internally in `direct_to_template`
    generic view.
    """
    for key, value in kwargs.items():
        if callable(value):
            extra_context[key] = value()
        else:
            extra_context[key] = value
    return RequestContext(request, extra_context)


class AdminMiddleware(object):

    """Middleware for the admin app."""

    def process_exception(self, request, exception):
        """Create a 404 page only for exceptions generated by the admin app."""
        if isinstance(exception, AdminHttp404):
            template = ADMIN_404_TEMPLATE
        elif isinstance(exception, AdminHttp405):
            template = ADMIN_405_TEMPLATE
        else:
            return

        c = update_request_context(request, default_dict,
                                   msg=exception.message)
        t = loader.get_template(template)
        response = t.render(c)
        return HttpResponseNotFound(response)

# Copyright 2011, 2012, 2013 GRNET S.A. All rights reserved.
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

from astakos.im.tests.common import *
from astakos.im.settings import astakos_services, BASE_HOST
from synnefo.lib.services import get_service_path
from synnefo.lib import join_urls

from django.core.urlresolvers import reverse

from datetime import date

#from xml.dom import minidom

import json

ROOT = "/%s/%s/%s/" % (
    astakos_settings.BASE_PATH, astakos_settings.ACCOUNTS_PREFIX, 'v1.0')
u = lambda url: ROOT + url


class QuotaAPITest(TestCase):
    def test_0(self):
        client = Client()
        backend = activation_backends.get_backend()

        component1 = Component.objects.create(name="comp1")
        register.add_service(component1, "service1", "type1", [])
        # custom service resources
        resource11 = {"name": "service1.resource11",
                      "desc": "resource11 desc",
                      "service_type": "type1",
                      "service_origin": "service1",
                      "ui_visible": True}
        r, _ = register.add_resource(resource11)
        register.update_resources([(r, 100)])
        resource12 = {"name": "service1.resource12",
                      "desc": "resource11 desc",
                      "service_type": "type1",
                      "service_origin": "service1",
                      "unit": "bytes"}
        r, _ = register.add_resource(resource12)
        register.update_resources([(r, 1024)])

        # create user
        user = get_local_user('test@grnet.gr')
        backend.accept_user(user)
        non_moderated_user = get_local_user('nonmon@example.com',
                                            is_active=False)
        r_user = get_local_user('rej@example.com',
                                is_active=False, email_verified=True)
        backend.reject_user(r_user, "reason")

        component2 = Component.objects.create(name="comp2")
        register.add_service(component2, "service2", "type2", [])
        # create another service
        resource21 = {"name": "service2.resource21",
                      "desc": "resource11 desc",
                      "service_type": "type2",
                      "service_origin": "service2",
                      "ui_visible": False}
        r, _ = register.add_resource(resource21)
        register.update_resources([(r, 3)])

        resource_names = [r['name'] for r in
                          [resource11, resource12, resource21]]

        # get resources
        r = client.get(u('resources'))
        self.assertEqual(r.status_code, 200)
        body = json.loads(r.content)
        for name in resource_names:
            assertIn(name, body)

        # get quota
        r = client.get(u('quotas'))
        self.assertEqual(r.status_code, 401)

        headers = {'HTTP_X_AUTH_TOKEN': user.auth_token}
        r = client.get(u('quotas/'), **headers)
        self.assertEqual(r.status_code, 200)
        body = json.loads(r.content)
        system_quota = body['system']
        assertIn('system', body)
        for name in resource_names:
            assertIn(name, system_quota)

        nmheaders = {'HTTP_X_AUTH_TOKEN': non_moderated_user.auth_token}
        r = client.get(u('quotas/'), **nmheaders)
        self.assertEqual(r.status_code, 401)

        q = quotas.get_user_quotas(non_moderated_user)
        self.assertEqual(q, {})

        q = quotas.get_user_quotas(r_user)
        self.assertEqual(q, {})

        r = client.get(u('service_quotas'))
        self.assertEqual(r.status_code, 401)

        s1_headers = {'HTTP_X_AUTH_TOKEN': component1.auth_token}
        r = client.get(u('service_quotas'), **s1_headers)
        self.assertEqual(r.status_code, 200)
        body = json.loads(r.content)
        assertIn(user.uuid, body)

        r = client.get(u('commissions'), **s1_headers)
        self.assertEqual(r.status_code, 200)
        body = json.loads(r.content)
        self.assertEqual(body, [])

        # issue some commissions
        commission_request = {
            "force": False,
            "auto_accept": False,
            "name": "my commission",
            "provisions": [
                {
                    "holder": user.uuid,
                    "source": "system",
                    "resource": resource11['name'],
                    "quantity": 1
                },
                {
                    "holder": user.uuid,
                    "source": "system",
                    "resource": resource12['name'],
                    "quantity": 30000
                }]}

        post_data = json.dumps(commission_request)
        r = client.post(u('commissions'), post_data,
                        content_type='application/json', **s1_headers)
        self.assertEqual(r.status_code, 413)

        commission_request = {
            "force": False,
            "auto_accept": False,
            "name": "my commission",
            "provisions": [
                {
                    "holder": user.uuid,
                    "source": "system",
                    "resource": resource11['name'],
                    "quantity": 1
                },
                {
                    "holder": user.uuid,
                    "source": "system",
                    "resource": resource12['name'],
                    "quantity": 100
                }]}

        post_data = json.dumps(commission_request)
        r = client.post(u('commissions'), post_data,
                        content_type='application/json', **s1_headers)
        self.assertEqual(r.status_code, 201)
        body = json.loads(r.content)
        serial1 = body['serial']
        assertGreater(serial1, 0)

        post_data = json.dumps(commission_request)
        r = client.post(u('commissions'), post_data,
                        content_type='application/json', **s1_headers)
        self.assertEqual(r.status_code, 201)
        body = json.loads(r.content)
        serial2 = body['serial']
        assertGreater(serial2, serial1)

        post_data = json.dumps(commission_request)
        r = client.post(u('commissions'), post_data,
                        content_type='application/json', **s1_headers)
        self.assertEqual(r.status_code, 201)
        body = json.loads(r.content)
        serial3 = body['serial']
        assertGreater(serial3, serial2)

        r = client.get(u('commissions'), **s1_headers)
        self.assertEqual(r.status_code, 200)
        body = json.loads(r.content)
        self.assertEqual(len(body), 3)

        r = client.get(u('commissions/' + str(serial1)), **s1_headers)
        self.assertEqual(r.status_code, 200)
        body = json.loads(r.content)
        self.assertEqual(body['serial'], serial1)
        assertIn('issue_time', body)
        provisions = sorted(body['provisions'], key=lambda p: p['resource'])
        self.assertEqual(provisions, commission_request['provisions'])
        self.assertEqual(body['name'], commission_request['name'])

        r = client.get(u('service_quotas?user=' + user.uuid), **s1_headers)
        self.assertEqual(r.status_code, 200)
        body = json.loads(r.content)
        user_quota = body[user.uuid]
        system_quota = user_quota['system']
        r11 = system_quota[resource11['name']]
        self.assertEqual(r11['usage'], 3)
        self.assertEqual(r11['pending'], 3)

        # resolve pending commissions
        resolve_data = {
            "accept": [serial1, serial3],
            "reject": [serial2, serial3, serial3 + 1],
        }
        post_data = json.dumps(resolve_data)

        r = client.post(u('commissions/action'), post_data,
                        content_type='application/json', **s1_headers)
        self.assertEqual(r.status_code, 200)
        body = json.loads(r.content)
        self.assertEqual(body['accepted'], [serial1])
        self.assertEqual(body['rejected'], [serial2])
        failed = body['failed']
        self.assertEqual(len(failed), 2)

        r = client.get(u('commissions/' + str(serial1)), **s1_headers)
        self.assertEqual(r.status_code, 404)

        # auto accept
        commission_request = {
            "auto_accept": True,
            "name": "my commission",
            "provisions": [
                {
                    "holder": user.uuid,
                    "source": "system",
                    "resource": resource11['name'],
                    "quantity": 1
                },
                {
                    "holder": user.uuid,
                    "source": "system",
                    "resource": resource12['name'],
                    "quantity": 100
                }]}

        post_data = json.dumps(commission_request)
        r = client.post(u('commissions'), post_data,
                        content_type='application/json', **s1_headers)
        self.assertEqual(r.status_code, 201)
        body = json.loads(r.content)
        serial4 = body['serial']
        assertGreater(serial4, serial3)

        r = client.get(u('commissions/' + str(serial4)), **s1_headers)
        self.assertEqual(r.status_code, 404)

        # malformed
        commission_request = {
            "auto_accept": True,
            "name": "my commission",
            "provisions": [
                {
                    "holder": user.uuid,
                    "source": "system",
                    "resource": resource11['name'],
                }
            ]}

        post_data = json.dumps(commission_request)
        r = client.post(u('commissions'), post_data,
                        content_type='application/json', **s1_headers)
        self.assertEqual(r.status_code, 400)

        commission_request = {
            "auto_accept": True,
            "name": "my commission",
            "provisions": "dummy"}

        post_data = json.dumps(commission_request)
        r = client.post(u('commissions'), post_data,
                        content_type='application/json', **s1_headers)
        self.assertEqual(r.status_code, 400)

        r = client.post(u('commissions'), commission_request,
                        content_type='application/json', **s1_headers)
        self.assertEqual(r.status_code, 400)

        # no holding
        commission_request = {
            "auto_accept": True,
            "name": "my commission",
            "provisions": [
                {
                    "holder": user.uuid,
                    "source": "system",
                    "resource": "non existent",
                    "quantity": 1
                },
                {
                    "holder": user.uuid,
                    "source": "system",
                    "resource": resource12['name'],
                    "quantity": 100
                }]}

        post_data = json.dumps(commission_request)
        r = client.post(u('commissions'), post_data,
                        content_type='application/json', **s1_headers)
        self.assertEqual(r.status_code, 404)

        # release
        commission_request = {
            "provisions": [
                {
                    "holder": user.uuid,
                    "source": "system",
                    "resource": resource11['name'],
                    "quantity": -1
                }
            ]}

        post_data = json.dumps(commission_request)
        r = client.post(u('commissions'), post_data,
                        content_type='application/json', **s1_headers)
        self.assertEqual(r.status_code, 201)
        body = json.loads(r.content)
        serial = body['serial']

        accept_data = {'accept': ""}
        post_data = json.dumps(accept_data)
        r = client.post(u('commissions/' + str(serial) + '/action'), post_data,
                        content_type='application/json', **s1_headers)
        self.assertEqual(r.status_code, 200)

        reject_data = {'reject': ""}
        post_data = json.dumps(accept_data)
        r = client.post(u('commissions/' + str(serial) + '/action'), post_data,
                        content_type='application/json', **s1_headers)
        self.assertEqual(r.status_code, 404)

        # force
        commission_request = {
            "force": True,
            "provisions": [
                {
                    "holder": user.uuid,
                    "source": "system",
                    "resource": resource11['name'],
                    "quantity": 100
                }]}

        post_data = json.dumps(commission_request)
        r = client.post(u('commissions'), post_data,
                        content_type='application/json', **s1_headers)
        self.assertEqual(r.status_code, 201)

        commission_request = {
            "force": True,
            "provisions": [
                {
                    "holder": user.uuid,
                    "source": "system",
                    "resource": resource11['name'],
                    "quantity": -200
                }]}

        post_data = json.dumps(commission_request)
        r = client.post(u('commissions'), post_data,
                        content_type='application/json', **s1_headers)
        self.assertEqual(r.status_code, 413)

        r = client.get(u('quotas'), **headers)
        self.assertEqual(r.status_code, 200)
        body = json.loads(r.content)
        system_quota = body['system']
        r11 = system_quota[resource11['name']]
        self.assertEqual(r11['usage'], 102)
        self.assertEqual(r11['pending'], 101)

        # Bad Request
        r = client.head(u('commissions'))
        self.assertEqual(r.status_code, 405)
        self.assertTrue('Allow' in r)


class TokensApiTest(TestCase):
    def setUp(self):
        backend = activation_backends.get_backend()

        self.user1 = get_local_user(
            'test1@example.org', email_verified=True, moderated=True,
            is_rejected=False)
        backend.activate_user(self.user1)
        assert self.user1.is_active is True

        self.user2 = get_local_user(
            'test2@example.org', email_verified=True, moderated=True,
            is_rejected=False)
        backend.activate_user(self.user2)
        assert self.user2.is_active is True

        c1 = Component(name='component1', url='http://localhost/component1')
        c1.save()
        s1 = Service(component=c1, type='type1', name='service1')
        s1.save()
        e1 = Endpoint(service=s1)
        e1.save()
        e1.data.create(key='versionId', value='v1.0')
        e1.data.create(key='publicURL', value='http://localhost:8000/s1/v1.0')

        s2 = Service(component=c1, type='type2', name='service2')
        s2.save()
        e2 = Endpoint(service=s2)
        e2.save()
        e2.data.create(key='versionId', value='v1.0')
        e2.data.create(key='publicURL', value='http://localhost:8000/s2/v1.0')

        c2 = Component(name='component2', url='http://localhost/component2')
        c2.save()
        s3 = Service(component=c2, type='type3', name='service3')
        s3.save()
        e3 = Endpoint(service=s3)
        e3.save()
        e3.data.create(key='versionId', value='v2.0')
        e3.data.create(key='publicURL', value='http://localhost:8000/s3/v2.0')

    def test_authenticate(self):
        client = Client()
        url = reverse('astakos.api.tokens.authenticate')

        # Check not allowed method
        r = client.get(url, post_data={})
        self.assertEqual(r.status_code, 405)
        self.assertTrue('Allow' in r)
        self.assertEqual(r['Allow'], 'POST')

        # check public mode
        r = client.post(url, CONTENT_LENGTH=0)
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r['Content-Type'].startswith('application/json'))
        try:
            body = json.loads(r.content)
        except Exception, e:
            self.fail(e)
        self.assertTrue('token' not in body.get('access'))
        self.assertTrue('user' not in body.get('access'))
        self.assertTrue('serviceCatalog' in body.get('access'))

        # Check unsupported xml input
        post_data = """
            <?xml version="1.0" encoding="UTF-8"?>
                <auth xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
                 xmlns="http://docs.openstack.org/identity/api/v2.0"
                 tenantName="%s">
                  <passwordCredentials username="%s" password="%s"/>
                </auth>""" % (self.user1.uuid, self.user1.uuid,
                              self.user1.auth_token)
        r = client.post(url, post_data, content_type='application/xml')
        self.assertEqual(r.status_code, 400)
        body = json.loads(r.content)
        self.assertEqual(body['badRequest']['message'],
                         "Unsupported Content-type: 'application/xml'")

        # Check malformed request: missing password
        post_data = """{"auth":{"passwordCredentials":{"username":"%s"},
                                "tenantName":"%s"}}""" % (
            self.user1.uuid, self.user1.uuid)
        r = client.post(url, post_data, content_type='application/json')
        self.assertEqual(r.status_code, 400)
        body = json.loads(r.content)
        self.assertTrue(body['badRequest']['message'].
                        startswith('Malformed request'))

        # Check malformed request: missing username
        post_data = """{"auth":{"passwordCredentials":{"password":"%s"},
                                "tenantName":"%s"}}""" % (
            self.user1.auth_token, self.user1.uuid)
        r = client.post(url, post_data, content_type='application/json')
        self.assertEqual(r.status_code, 400)
        body = json.loads(r.content)
        self.assertTrue(body['badRequest']['message'].
                        startswith('Malformed request'))

        # Check invalid pass
        post_data = """{"auth":{"passwordCredentials":{"username":"%s",
                                                       "password":"%s"},
                                "tenantName":"%s"}}""" % (
            self.user1.uuid, '', self.user1.uuid)
        r = client.post(url, post_data, content_type='application/json')
        self.assertEqual(r.status_code, 401)
        body = json.loads(r.content)
        self.assertEqual(body['unauthorized']['message'],
                         'Invalid token')

        # Check inconsistent pass
        post_data = """{"auth":{"passwordCredentials":{"username":"%s",
                                                       "password":"%s"},
                                "tenantName":"%s"}}""" % (
            self.user1.uuid, self.user2.auth_token, self.user2.uuid)
        r = client.post(url, post_data, content_type='application/json')
        self.assertEqual(r.status_code, 401)
        body = json.loads(r.content)
        self.assertEqual(body['unauthorized']['message'],
                         'Invalid credentials')

        # Check invalid json data
        r = client.post(url, "not json", content_type='application/json')
        self.assertEqual(r.status_code, 400)
        body = json.loads(r.content)
        self.assertEqual(body['badRequest']['message'], 'Invalid JSON data')

        # Check auth with token
        post_data = """{"auth":{"token": {"id":"%s"},
                        "tenantName":"%s"}}""" % (
            self.user1.auth_token, self.user1.uuid)
        r = client.post(url, post_data, content_type='application/json')
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r['Content-Type'].startswith('application/json'))
        try:
            body = json.loads(r.content)
        except Exception, e:
            self.fail(e)

        # Check malformed request: missing token
        post_data = """{"auth":{"auth_token":{"id":"%s"},
                                "tenantName":"%s"}}""" % (
            self.user1.auth_token, self.user1.uuid)
        r = client.post(url, post_data, content_type='application/json')
        self.assertEqual(r.status_code, 400)
        body = json.loads(r.content)
        self.assertTrue(body['badRequest']['message'].
                        startswith('Malformed request'))

        # Check bad request: inconsistent tenant
        post_data = """{"auth":{"token":{"id":"%s"},
                                "tenantName":"%s"}}""" % (
            self.user1.auth_token, self.user2.uuid)
        r = client.post(url, post_data, content_type='application/json')
        self.assertEqual(r.status_code, 400)
        body = json.loads(r.content)
        self.assertEqual(body['badRequest']['message'],
                         'Not conforming tenantName')

        # Check bad request: inconsistent tenant
        post_data = """{"auth":{"token":{"id":"%s"},
                                "tenantName":""}}""" % (
            self.user1.auth_token)
        r = client.post(url, post_data, content_type='application/json')
        self.assertEqual(r.status_code, 200)

        # Check successful json response
        post_data = """{"auth":{"passwordCredentials":{"username":"%s",
                                                       "password":"%s"},
                                "tenantName":"%s"}}""" % (
            self.user1.uuid, self.user1.auth_token, self.user1.uuid)
        r = client.post(url, post_data, content_type='application/json')
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r['Content-Type'].startswith('application/json'))
        try:
            body = json.loads(r.content)
        except Exception, e:
            self.fail(e)

        try:
            token = body['access']['token']['id']
            user = body['access']['user']['id']
            service_catalog = body['access']['serviceCatalog']
        except KeyError:
            self.fail('Invalid response')

        self.assertEqual(token, self.user1.auth_token)
        self.assertEqual(user, self.user1.uuid)
        self.assertEqual(len(service_catalog), 3)

        # Check successful xml response
        headers = {'HTTP_ACCEPT': 'application/xml'}
        post_data = """{"auth":{"passwordCredentials":{"username":"%s",
                                                       "password":"%s"},
                                "tenantName":"%s"}}""" % (
            self.user1.uuid, self.user1.auth_token, self.user1.uuid)
        r = client.post(url, post_data, content_type='application/json',
                        **headers)
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r['Content-Type'].startswith('application/xml'))
#        try:
#            body = minidom.parseString(r.content)
#        except Exception, e:
#            self.fail(e)


class UserCatalogsTest(TestCase):
    def test_get_uuid_displayname_catalogs(self):
        self.user = get_local_user(
            'test1@example.org', email_verified=True, moderated=True,
            is_rejected=False, is_active=False)

        client = Client()
        url = reverse('astakos.api.user.get_uuid_displayname_catalogs')
        d = dict(uuids=[self.user.uuid], displaynames=[self.user.username])

        # assert Unauthorized: missing authentication token
        r = client.post(url,
                        data=json.dumps(d),
                        content_type='application/json')
        self.assertEqual(r.status_code, 401)

        # assert Unauthorized: invalid authentication token
        r = client.post(url,
                        data=json.dumps(d),
                        content_type='application/json',
                        HTTP_X_AUTH_TOKEN='1234')
        self.assertEqual(r.status_code, 401)

        # assert Unauthorized: inactive token holder
        r = client.post(url,
                        data=json.dumps(d),
                        content_type='application/json',
                        HTTP_X_AUTH_TOKEN=self.user.auth_token)
        self.assertEqual(r.status_code, 401)

        backend = activation_backends.get_backend()
        backend.activate_user(self.user)
        assert self.user.is_active is True

        r = client.post(url,
                        data=json.dumps(d),
                        content_type='application/json',
                        HTTP_X_AUTH_TOKEN=self.user.auth_token)
        self.assertEqual(r.status_code, 200)
        try:
            data = json.loads(r.content)
        except:
            self.fail('Response body should be json formatted')
        else:
            if not isinstance(data, dict):
                self.fail('Response body should be json formatted dictionary')

            self.assertTrue('uuid_catalog' in data)
            self.assertEqual(data['uuid_catalog'],
                             {self.user.uuid: self.user.username})

            self.assertTrue('displayname_catalog' in data)
            self.assertEqual(data['displayname_catalog'],
                             {self.user.username: self.user.uuid})

        # assert Unauthorized: expired token
        self.user.auth_token_expires = date.today() - timedelta(1)
        self.user.save()

        r = client.post(url,
                        data=json.dumps(d),
                        content_type='application/json',
                        HTTP_X_AUTH_TOKEN=self.user.auth_token)
        self.assertEqual(r.status_code, 401)

        # assert Unauthorized: expired token
        self.user.auth_token_expires = date.today() + timedelta(1)
        self.user.save()

        # assert badRequest
        r = client.post(url,
                        data=json.dumps(str(d)),
                        content_type='application/json',
                        HTTP_X_AUTH_TOKEN=self.user.auth_token)
        self.assertEqual(r.status_code, 400)


class WrongPathAPITest(TestCase):
    def test_catch_wrong_account_paths(self, *args):
        path = get_service_path(astakos_services, 'account', 'v1.0')
        path = join_urls(BASE_HOST, path, 'nonexistent')
        response = self.client.get(path)
        self.assertEqual(response.status_code, 400)
        try:
            error = json.loads(response.content)
        except ValueError:
            self.assertTrue(False)

    def test_catch_wrong_identity_paths(self, *args):
        path = get_service_path(astakos_services, 'identity', 'v2.0')
        path = join_urls(BASE_HOST, path, 'nonexistent')
        response = self.client.get(path)
        self.assertEqual(response.status_code, 400)
        try:
            json.loads(response.content)
        except ValueError:
            self.assertTrue(False)

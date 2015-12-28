#
# Copyright (c) 2013, Digium, Inc.
#

"""Swagger client library.
"""

import json
import os.path
import re
import urllib
import swaggerpy

from tornado.log import app_log as log
from tornado.ioloop import IOLoop
from tornado.gen import coroutine, Return
from tornado.httpclient import AsyncHTTPClient, HTTPClient, HTTPRequest
from tornado.websocket import websocket_connect
from swaggerpy.processors import WebsocketProcessor, SwaggerProcessor


class ClientProcessor(SwaggerProcessor):
    """Enriches swagger models for client processing.
    """

    def process_resource_listing_api(self, resources, listing_api, context):
        """Add name to listing_api.

        :param resources: Resource listing object
        :param listing_api: ResourceApi object.
        :type context: ParsingContext
        :param context: Current context in the API.
        """
        name, ext = os.path.splitext(os.path.basename(listing_api['path']))
        listing_api['name'] = name


class Operation(object):
    """Operation object.
    """

    def __init__(self, uri, operation, http_client):
        """

        :param uri:
        :param operation:
        :param http_client: HTTP client
        :type http_client: AsyncHTTPClient
        :return:
        """
        self.uri = uri
        self.json = operation
        self.http_client = http_client

    def __repr__(self):
        return '{0}({1})'.format(
                self.__class__.__name__, self.json['nickname'])

    @coroutine
    def __call__(self, **kwargs):
        """Invoke ARI operation.

        :param kwargs: ARI operation arguments.
        :return: Implementation specific response or WebSocket connection
        """
        log.info('{0}?{1!r:s}'.format(
                self.json['nickname'], urllib.urlencode(kwargs)))
        method = self.json['httpMethod']
        uri = self.uri
        params = {}
        data = None
        headers = None
        for param in self.json.get('parameters', []):
            pname = param['name']
            value = kwargs.get(pname)
            # Turn list params into comma separated values
            if isinstance(value, list):
                value = ','.join(value)

            if value is not None:
                if param['paramType'] == 'path':
                    uri = uri.replace('{%s}' % pname,
                                      urllib.quote_plus(str(value)))
                elif param['paramType'] == 'query':
                    params[pname] = value
                elif param['paramType'] == 'body':
                    if isinstance(value, dict):
                        if data:
                            data.update(value)
                        else:
                            data = value
                    else:
                        raise TypeError(
                                'Parameters of type "body" require dict input')
                else:
                    raise AssertionError(
                            u'Unsupported paramType {0}'
                            .format(param['paramType']))
                del kwargs[pname]
            else:
                if param['required']:
                    raise TypeError(
                            'Missing required parameter "{0}" for "{1}"'
                            .format(pname, self.json['nickname']))
        if kwargs:
            raise TypeError('"{0}" does not have parameters {1!r:s}'
                            .format(self.json['nickname'], kwargs.keys()))

        log.info('{0} {1}({2!r:s})'.format(method, uri, params))

        if data:
            data = json.dumps(data)
            headers = {'Content-type': 'application/json',
                       'Accept': 'application/json'}

        url = '?'.join([uri, urllib.urlencode(params)])
        if self.json['is_websocket']:
            # Fix up http: URLs
            uri = re.sub('^http', 'ws', uri)
            if data:
                raise NotImplementedError(
                        'Sending body data with websockets not implmented')
            request = HTTPRequest(url, **self.http_client.defaults)
            ws = yield websocket_connect(request)
            raise Return(ws)
        else:
            result = yield self.http_client.fetch(
                url, method=method, body=data, headers=headers)
            raise Return(result)


class Resource(object):
    """Swagger resource, described in an API declaration.

    :param resource: Resource model
    :param http_client: HTTP client API
    """

    def __init__(self, resource, http_client):
        log.debug(u'Building resource "{0}"'.format(resource['name']))
        self.json = resource
        decl = resource['api_declaration']
        self.http_client = http_client
        self.operations = {
            oper['nickname']: self._build_operation(decl, api, oper)
            for api in decl['apis']
            for oper in api['operations']}

    def __repr__(self):
        return '{0}({1})'.format(
                self.__class__.__name__, self.json['name'])

    def __getattr__(self, item):
        """Promote operations to be object fields.

        :param item: Name of the attribute to get.
        :rtype: Resource
        :return: Resource object.
        """
        op = self.get_operation(item)
        if not op:
            raise AttributeError('Resource "{0}" has no operation "{1}"'
                                 .format(self.get_name(), item))
        return op

    def get_operation(self, name):
        """Gets the operation with the given nickname.

        :param name: Nickname of the operation.
        :rtype:  Operation
        :return: Operation, or None if not found.
        """
        return self.operations.get(name)

    def get_name(self):
        """Returns the name of this resource.

        Name is derived from the filename of the API declaration.

        :return: Resource name.
        """
        return self.json.get('name')

    def _build_operation(self, decl, api, operation):
        """Build an operation object

        :param decl: API declaration.
        :param api: API entry.
        :param operation: Operation.
        """
        log.debug('Building operation {0}.{1}'.format(
                self.get_name(), operation['nickname']))
        uri = decl['basePath'] + api['path']
        return Operation(uri, operation, self.http_client)


class SwaggerClient(object):
    """Client object for accessing a Swagger-documented RESTful service.

    :param url_or_resource: Either the parsed resource listing+API decls,
                            or its URL.
    :type url_or_resource: dict or str
    :param http_client: HTTP client API
    :type  http_client: HttpClient
    """
    _api_docs = None
    _resources = None

    @property
    def api_docs(self):
        if self._api_docs is None:
            raise RuntimeError('Not loaded')
        return self._api_docs

    @api_docs.setter
    def api_docs(self, value):
        self._api_docs = value

    @property
    def resources(self):
        if self._resources is None:
            raise RuntimeError('Not loaded')
        return self._resources

    @resources.setter
    def resources(self, value):
        self._resources = value

    def __init__(self, url_or_resource, io_loop=None, http_client=None):
        if io_loop is None:
            io_loop = IOLoop.current()
        self.io_loop = io_loop
        if http_client is None:
            http_client = AsyncHTTPClient()
        self.http_client = http_client

        loader = swaggerpy.Loader(
                http_client=HTTPClient(defaults=self.http_client.defaults),
                processors=[WebsocketProcessor(), ClientProcessor()]
        )

        if isinstance(url_or_resource, str):
            log.debug('Loading from {0}'.format(url_or_resource))
            self.api_docs = loader.load_resource_listing(url_or_resource)
        else:
            log.debug('Loading from {0}'.format(
                    url_or_resource.get('basePath')))
            self.api_docs = url_or_resource
            loader.process_resource_listing(self.api_docs)

        self.resources = {
            resource['name']: Resource(resource, self.http_client)
            for resource in self.api_docs['apis']}

    def __repr__(self):
        return '{0}({1})'.format(
                self.__class__.__name__, self.api_docs['basePath'])

    def __getattr__(self, item):
        """Promote resource objects to be client fields.

        :param item: Name of the attribute to get.
        :return: Resource object.
        """
        resource = self.get_resource(item)
        if not resource:
            raise AttributeError('API has no resource "{0}"'.format(item))
        return resource

    def close(self):
        """Close the SwaggerClient, and underlying resources.
        """
        self.http_client.close()

    def get_resource(self, name):
        """Gets a Swagger resource by name.

        :param name: Name of the resource to get
        :rtype: Resource
        :return: Resource, or None if not found.
        """
        return self.resources.get(name)

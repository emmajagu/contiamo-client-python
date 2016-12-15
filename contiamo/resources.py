from .http_client import HTTPClient

from contiamo import errors

import logging
logger = logging.getLogger(__name__)


def CreateNestedResource(base_class, parent, **kwargs):
  class_name = type(parent).__name__ + base_class.__name__.rstrip('Resource')
  properties = {'parent': parent}
  properties.update(kwargs)
  return type(class_name, (base_class,), properties)


###
# Main client
###
class Client:

  def __init__(self, api_key, api_base='https://api.contiamo.com'):
    self.api_key = api_key
    self.api_base = api_base
    self.http_client = HTTPClient(api_key)
    self.Project = CreateNestedResource(ProjectResource, parent=self, path_segment=None)

  def client(self):
    return self.http_client

  def instance_url(self):
    return self.api_base


###
# Base resource class
###
class Resource(dict):
  id_attribute = 'id'
  path_segment = None
  parent = None

  def __init__(self, id):
    self.id = id
    self._init_nested_resources()

  def _init_nested_resources(self):
    pass

  @classmethod
  def client(cls):
    return cls.parent.client()

  @classmethod
  def class_url(cls):
    base_url = cls.parent.instance_url()
    if cls.path_segment:
      return '%s/%s' % (base_url, cls.path_segment)
    else:
      return base_url

  def instance_url(self):
    return '%s/%s' % (self.class_url(), self.id)

  @classmethod
  def instantiate_from_response(cls, response):
    try:
      resource_instance = cls(response[cls.id_attribute])
    except KeyError:
      self._handle_invalid_response(e, response)
    resource_instance.update(response)
    return resource_instance


###
# Mixin classes
###
class RetrievableResource(Resource):

  @classmethod
  def instantiate_list(cls, responses):
    return [cls.instantiate_from_response(response) for response in responses]

  @classmethod
  def list(cls, instantiate=False):
    resources = cls.request('get', cls.class_url())
    if type(resources) is dict:
      try:
        resources = resources['resources']
      except KeyError as e:
        self._handle_invalid_response(e, response)
    if instantiate:
      return cls.instantiate_list(resources)
    else:
      return resources

  @classmethod
  def retrieve(cls, id):
    instance = cls(id)
    resource = cls.request('get', instance.instance_url())
    instance.update(resource)
    return instance

  @classmethod
  def request(cls, method, url, payload=None):
    response = cls.client().request(method, url, payload=payload)
    try:
      result = response.json()
    except ValueError as e:  # JSONDecodeError inherits from ValueError
      cls._handle_invalid_response(e, response)
    return result

  @classmethod
  def _handle_invalid_response(self, e, response):
    logger.error('Invalid JSON response: %s' % response.text)
    raise errors.ResponseError(
      'The response from the server was invalid. Please report the bug to support@contiamo.com\n'
      'The following %s error was raised when interpreting the response:\n%s' % (type(e).__name__, e),
      http_body=response.content, http_status=response.status_code, headers=response.headers)


class UpdateableResource(Resource):

  @classmethod
  def create(cls, model):
    response = cls.request('post', cls.class_url(), payload=model)
    return cls.instantiate_from_response(response)

  def modify(self, model):
    # need to handle lock version
    response = self.request('put', self.instance_url(), payload=model)
    return self.instantiate_from_response(response)


###
# Resource classes
###
class ProjectResource(Resource):
  path_segment = 'projects'

  def _init_nested_resources(self):
    self.Dashboard = CreateNestedResource(DashboardResource, parent=self)
    self.App = CreateNestedResource(AppResource, parent=self)

class DashboardResource(RetrievableResource, UpdateableResource, Resource):
  path_segment = 'dashboards'

  def _init_nested_resources(self):
    self.Widget = CreateNestedResource(WidgetResource, parent=self)

class WidgetResource(RetrievableResource, UpdateableResource, Resource):
  path_segment = 'widgets'

class AppResource(RetrievableResource, Resource):
  path_segment = 'apps'

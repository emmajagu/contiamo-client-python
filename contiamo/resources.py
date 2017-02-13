from contiamo.http_client import HTTPClient
from contiamo.utils import raise_response_error, parse_query_result

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

  def query_contract(self, labs_id, max_rows=10000):
    """
    The labs_id of a contract is available in the manage section for that contract.
    It is an identifier that begins with 'contract:'.
    """
    if max_rows > 100000:
      raise errors.InvalidRequestError(
        'The number of rows is limited at 100k. Please contact us if you need to query more data.')
    try:
      # truncate id in case token was left in by the user
      _, project_id, app_id, contract_key = labs_id.split(':')[:4]
    except ValueError:
      raise errors.InvalidRequestError('"%s" is not a valid data contract identifier.' % labs_id)
    project = self.Project(project_id)
    # deal with negative max_rows silently to avoid misleading authentication failure
    return project.query_sql(app_id, "select * from contract_%s limit %d;" % (contract_key, max(max_rows, 0)))


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
    except KeyError as e:
      raise_response_error(e, response, logger)
    resource_instance.update(response)
    return resource_instance

  @classmethod
  def request(cls, method, url, payload=None):
    response = cls.client().request(method, url, payload=payload)
    try:
      result = response.json()
    except ValueError as e:  # JSONDecodeError inherits from ValueError
      raise_response_error(e, response, logger)
    return result

  def resolve_url(self, url, sub_path):
    resolved_url = url if url else self.instance_url()
    if sub_path is not None:
      resolved_url += '/' + sub_path.strip('/')
    return resolved_url

  # do not overwrite dict get method
  def _get(self, url=None, sub_path=None):
    return self.__class__.request('GET', self.resolve_url(url, sub_path))

  def _post(self, url=None, sub_path=None, payload=None):
    return self.__class__.request('POST', self.resolve_url(url, sub_path), payload=payload)

  def _put(self, url=None, sub_path=None, payload=None):
    return self.__class__.request('PUT', self.resolve_url(url, sub_path), payload=payload)


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
        raise_response_error(e, response, logger)
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

  def refresh(self):
    response = self._get()
    self.update(self.instantiate_from_response(response))


class UpdateableResource(Resource):

  @classmethod
  def create(cls, model):
    response = cls.request('post', cls.class_url(), payload=model)
    return cls.instantiate_from_response(response)

  def modify(self, model):
    # need to handle lock version
    response = self._put(payload=model)
    return self.instantiate_from_response(response)


###
# Resource classes
###
class ProjectResource(Resource):
  path_segment = 'projects'

  def _init_nested_resources(self):
    self.Dashboard = CreateNestedResource(DashboardResource, parent=self)
    self.App = CreateNestedResource(AppResource, parent=self)

  def query_sql(self, app_id, sql, parse_dates=True, use_column_names=True):
    payload = {
      'app_data_id': app_id,
      'columns': [],
      'query': sql
    }
    json_response = self._post(sub_path='/sql_query', payload=payload)
    return parse_query_result(json_response, parse_dates=parse_dates, use_column_names=use_column_names)

class DashboardResource(RetrievableResource, UpdateableResource, Resource):
  path_segment = 'dashboards'

  def _init_nested_resources(self):
    self.Widget = CreateNestedResource(WidgetResource, parent=self)

class WidgetResource(RetrievableResource, UpdateableResource, Resource):
  path_segment = 'widgets'

class AppResource(RetrievableResource, Resource):
  path_segment = 'apps'

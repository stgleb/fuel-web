import re
import json
import time
import urllib2
from functools import partial, wraps


logger = None


def set_logger(log):
    global logger
    logger = log


class Urllib2HTTP(object):
    """
    class for making HTTP requests
    """

    allowed_methods = ('get', 'put', 'post', 'delete', 'patch', 'head')

    def __init__(self, root_url, headers=None, echo=False):
        """
        """
        if root_url.endswith('/'):
            self.root_url = root_url[:-1]
        else:
            self.root_url = root_url

        self.headers = headers if headers is not None else {}
        self.echo = echo

    def do(self, method, path, params=None):
        if path.startswith('/'):
            url = self.root_url + path
        else:
            url = self.root_url + '/' + path

        if method == 'get':
            assert params == {} or params is None
            data_json = None
        else:
            data_json = json.dumps(params)

        if self.echo:
            print "HTTP: {} {}".format(method.upper(), url)

        request = urllib2.Request(url,
                                  data=data_json,
                                  headers=self.headers)
        if data_json is not None:
            request.add_header('Content-Type', 'application/json')

        request.get_method = lambda: method.upper()
        responce = urllib2.urlopen(request)

        if responce.code < 200 or responce.code > 209:
            raise IndexError(url)

        content = responce.read()

        if '' == content:
            return None

        return json.loads(content)

    def __getattr__(self, name):
        if name in self.allowed_methods:
            return partial(self.do, name)
        raise AttributeError(name)


def get_inline_param_list(url):
    format_param_rr = re.compile(r"\{([a-zA-Z_]+)\}")
    for match in format_param_rr.finditer(url):
        yield match.group(1)


class RestObj(object):
    name = None
    id = None

    def __init__(self, conn, **kwargs):
        self.__dict__.update(kwargs)
        self.__connection__ = conn

    def __str__(self):
        res = ["{}({}):".format(self.__class__.__name__, self.name)]
        for k, v in sorted(self.__dict__.items()):
            if k.startswith('__') or k.endswith('__'):
                continue
            if k != 'name':
                res.append("    {}={!r}".format(k, v))
        return "\n".join(res)


def make_call(method, url):
    def closure(obj, entire_obj=None, **data):
        if entire_obj is not None:
            if data != {}:
                raise ValueError("Both entire_obj and data provided")
            request_data = entire_obj
            result_url = url
        else:
            inline_params_vals = {}
            request_data = data.copy()
            for name in get_inline_param_list(url):
                if name in data:
                    inline_params_vals[name] = data[name]
                    del data[name]
                else:
                    inline_params_vals[name] = getattr(obj, name)
            result_url = url.format(**inline_params_vals)

        return obj.__connection__.do(method, result_url, params=request_data)
    return closure


PUT = partial(make_call, 'put')
GET = partial(make_call, 'get')
DELETE = partial(make_call, 'delete')


def with_timeout(tout, message):
    def closure(func):
        @wraps(func)
        def closure2(*dt, **mp):
            ctime = time.time()
            etime = ctime + tout

            while ctime < etime:
                if func(*dt, **mp):
                    return
                sleep_time = ctime + 1 - time.time()
                time.sleep(sleep_time)
                ctime = time.time()
            raise RuntimeError("Timeout during " + message)
        return closure2
    return closure


#-------------------------------  ORM -----------------------------------------


class Node(RestObj):
    def set_node_name(self, name):
        self.__connection__.put('nodes', [{'id': self.id, 'name': name}])


class Cluster(RestObj):

    add_node_call = PUT('nodes')
    start_deploy = PUT('clusters/{id}/changes')
    status = GET('clusters/{id}')
    delete = DELETE('clusters/{id}')

    def add_node(self, node, roles):
        data = {}
        data['pending_roles'] = roles
        data['cluster_id'] = self.id
        data['id'] = node.id
        data['pending_addition'] = True
        logger.debug("Adding node %s to cluster..." % node.id)
        self.add_node_call([data])

    def wait_operational(self, timeout):
        print self.status
        wo = lambda : self.status()['status'] == 'operational'
        with_timeout(timeout, "deploy cluster")(wo)()

    def deploy(self, timeout):
        logger.debug("Starting deploy...")
        self.start_deploy()

        self.wait_operational(timeout)

        # for _ in range(timeout):
        #     response = api_request('/api/tasks?tasks=' + str(self.id), 'GET')

        #     for task in response:
        #         if task['status'] == 'error':
        #             raise Exception('Task execution error')

        #     time.sleep(1)

        # raise Exception('Tasks timeout error')


def get_all_nodes(conn):
    for node_desc in conn.get('nodes'):
        yield Node(conn, **node_desc)


def get_all_clusters(conn):
    for cluster_desc in conn.get('clusters'):
        yield Cluster(conn, **cluster_desc)


def create_empty_cluster(conn, cluster_desc):
    logger.info("Creating new cluster %s" % cluster_desc['name'])
    data = {}
    data['nodes'] = []
    data['tasks'] = []
    data['name'] = cluster_desc['name']
    data['release'] = cluster_desc['release']
    data['mode'] = cluster_desc['deployment_mode']
    data['net_provider'] = cluster_desc['settings']['net_provider']

    return Cluster(conn, **conn.post('clusters', data))


def reflect_cluster(conn, cluster_id):
    pass

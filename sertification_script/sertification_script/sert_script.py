import functools
import time
import glob
import os.path
import pkgutil
import smtplib
import inspect
import contextlib
from email.mime.text import MIMEText

import yaml
from sertification_script.fuel_rest_api import api_request, get_all_nodes, set_node_name, get_clusters
from sertification_script.tests import base


import sys
sys.path.insert(0, '../lib/requests')

logger = None

GB = 1024 * 1024 * 1024


def set_logger(log):
    global logger
    logger = log


def add_node_to_cluster(cluster_id, node_id, roles):
    data = {}
    data['pending_roles'] = roles
    data['cluster_id'] = cluster_id
    data['id'] = node_id
    data['pending_addition'] = True
    logger.debug("Adding node %s to cluster..." % node_id)

    api_request('/api/nodes', 'PUT', [data])


def find_node_by_requirements(nodes, requirements):
    min_cpu = requirements.get('cpu_count_min') or 0
    max_cpu = requirements.get('cpu_count_max') or 1000
    min_hd = requirements.get('hd_size_min') or 0
    max_hd = requirements.get('hd_size_max') or 10000

    def cpu_valid(cpu):
        return max_cpu >= cpu >= min_cpu

    def hd_valid(hd):
        return max_hd >= hd >= min_hd

    for node in nodes:
        cpu = node['meta']['cpu']['total']
        hd = sum([disk['size'] for disk in node['meta']['disks']]) / GB
        if cpu_valid(cpu) and hd_valid(hd):
            return node


def add_nodes_to_cluster(cluster_id, nodes, timeout):
    num_nodes = len(nodes)
    logger.debug("Waiting for nodes %s to be discovered..." % nodes.keys())
    for _ in range(timeout):
        response = api_request('/api/nodes', 'GET')
        nodes_discovered = [x for x in response if x['cluster'] is None]
        if len(nodes_discovered) < num_nodes:
            time.sleep(1)
            continue
        else:
            node_mac_mapping = dict([(node['mac'].upper(), node) for
                                     node in nodes_discovered])
            for node in nodes.values():
                mac = node.get('mac')
                requirements = node.get('requirements')
                if mac:
                    node_found = node_mac_mapping.get(mac.upper())
                    if not node_found:
                        raise Exception("node with mac %s not found" % mac)
                    add_node_to_cluster(cluster_id, node_found['id'],
                                        node['roles'])
                    nodes_discovered.remove(node_found)
                    continue
                if requirements:
                    node_found = find_node_by_requirements(nodes_discovered,
                                                           requirements)
                    if not node_found:
                        raise Exception("node with requirements not found")
                    add_node_to_cluster(cluster_id, node_found['id'],
                                        node['roles'])
                    nodes_discovered.remove(node_found)
            return
    raise Exception('Timeout exception')


def deploy(cluster_id, timeout):
    logger.debug("Starting deploy...")
    api_request('/api/clusters/' + str(cluster_id) + '/changes',
                'PUT')

    for _ in range(timeout):
        cluster = api_request('/api/clusters/' + str(cluster_id))
        if cluster['status'] == 'operational':
            break
        time.sleep(1)
    else:
        raise Exception('Cluster deploy timeout error')

    for _ in range(timeout):
        response = api_request('/api/tasks?tasks=' + str(cluster_id), 'GET')

        for task in response:
            if task['status'] == 'error':
                raise Exception('Task execution error')
        else:
            break
        time.sleep(1)
    else:
        raise Exception('Tasks timeout error')


def find_test_classes():
    test_classes = []
    for loader, name, _ in pkgutil.iter_modules(['tests']):
        module = loader.find_module(name).load_module(name)
        test_classes.extend([member for name, member in
                             inspect.getmembers(module)
                             if inspect.isclass(member) and
                                issubclass(member, base.BaseTests)])
    return test_classes


def run_all_tests(cluster_id, timeout, tests_to_run, fuel_url):
    test_classes = find_test_classes()
    results = []
    for test_class in test_classes:
        test_class_inst = test_class(fuel_url, cluster_id, timeout)
        available_tests = test_class_inst.get_available_tests()
        results.extend(test_class_inst.run_tests(
            set(available_tests) & set(tests_to_run)))
    return results


def send_results(mail_config, tests):
    server = smtplib.SMTP(mail_config['smtp_server'], 587)
    server.starttls()
    server.login(mail_config['login'], mail_config['password'])

    # Form message body
    failed_tests = [test for test in tests if test['status'] == 'failure']
    msg = '\n'.join([test['name'] + '\n        ' + test['message']
                     for test in failed_tests])

    msg = MIMEText(msg)
    msg['Subject'] = 'Test Results'
    msg['To'] = mail_config['mail_to']
    msg['From'] = mail_config['mail_from']

    logger.debug("Sending results by email...")
    server.sendmail(mail_config['mail_from'],
                    [mail_config['mail_to']],
                    msg.as_string())
    server.quit()


def load_all_clusters(path):
    res = {}
    for fname in glob.glob(os.path.join(path, "*.yaml")):
        try:
            cluster = yaml.load(open(fname).read())
            res[cluster['name']] = cluster
        except Exception as exc:
            msg = "Failed to load cluster from file {}: {}".format(
                fname, exc)
            logger.error(msg)
    return res


def create_empty_cluster(cluster):
    print "Creating new cluster %s" % cluster['name']
    data = {}
    data['nodes'] = []
    data['tasks'] = []
    data['name'] = cluster['name']
    data['release'] = cluster['release']
    data['mode'] = cluster['deployment_mode']
    data['net_provider'] = cluster['settings']['net_provider']
    response = api_request('/api/clusters', 'POST', data)
    return response['id']


def delete_cluster(cluster_id):
    api_request('/api/clusters/' + str(cluster_id), 'DELETE')


def deploy_cluster(cluster):
    cluster_id = create_empty_cluster(cluster)

    num_nodes = len(cluster['nodes'])
    logger.debug("Waiting for %d nodes to be discovered..." % num_nodes)
    nodes_discover_timeout = cluster.get('nodes_discovery_timeout', 3600)
    deploy_timeout = cluster.get('DEPLOY_TIMEOUT', 3600)

    nodes_info = cluster['nodes']
    add_nodes_to_cluster(cluster_id, nodes_info,
                         nodes_discover_timeout)

    deploy(cluster_id, deploy_timeout)
    return cluster_id


@contextlib.contextmanager
def make_cluster(cluster, auto_delete):
    if auto_delete:
        for cluster_obj in get_clusters():
            if cluster_obj.name == cluster['name']:
                delete_cluster(cluster_obj.id)

    cid = deploy_cluster(cluster)
    try:
        yield cid
    finally:
        delete_cluster(cid)


def with_cluster(config_path):
    cluster = yaml.load(open(config_path).read())

    def decorator(f):
        @functools.wraps(f)
        def wrapper(*args, **kwargs):
            with make_cluster(cluster) as cluster_id:
                arg_spec = inspect.getargspec(f)
                if 'cluster_id' in arg_spec.args[len(arg_spec.defaults) - 1:]:
                    kwargs['cluster_id'] = cluster_id
                return f(*args, **kwargs)
        return wrapper
    return decorator

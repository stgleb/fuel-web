import time
import glob
import os.path
import pkgutil
import smtplib
import inspect
import contextlib

import yaml
from email.mime.text import MIMEText
from fuel_rest_api import api_request


logger = None


def set_logger(log):
    global loggerii
    logger = log


def map_node_role_id(nodes, timeout):
    logger.debug("Waiting for nodes %s to be discovered..." % nodes)
    for _ in range(timeout):
        response = api_request('/api/nodes', 'GET')

        nodes_discovered = len([x for x in response if x['cluster'] is None])
        if set(nodes).issubset([node['name'] for node in nodes_discovered]):
            return [(node['id'], nodes[node['name']]) for node in
                    nodes_discovered if node['name'] in nodes]
        time.sleep(1)

    raise Exception('Timeout exception')


def add_node_to_cluster(cluster_id, node_id, roles):
    data = {}
    data['pending_roles'] = roles
    data['cluster_id'] = cluster_id
    data['id'] = node_id
    data['pending_addition'] = True
    logger.debug("Adding node %s to cluster..." % node_id)

    api_request('/api/nodes', 'PUT', [data])


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
                             if inspect.isclass(member)])
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


def create_empty_cluster(name, cluster):
    print "Creating new cluster %s" % name
    data = {}
    data['nodes'] = []
    data['tasks'] = []
    data['name'] = name
    data['release'] = cluster['release']
    data['mode'] = cluster['deployment_mode']
    data['net_provider'] = cluster['settings']['net_provider']
    response = api_request('/api/clusters', 'POST', data)
    return response['id']


def delete_cluster(cluster_id):
    api_request('/api/clusters/' + str(cluster_id), 'DELETE')


def deploy_cluster(name, cluster):
    cluster_id = create_empty_cluster(name, cluster)

    num_nodes = len(cluster['nodes'])
    logger.debug("Waiting for %d nodes to be discovered..." % num_nodes)
    nodes_discover_timeout = cluster.get('nodes_discovery_timeout', 3600)
    deploy_timeout = cluster.get('DEPLOY_TIMEOUT', 3600)

    nodes_info = cluster['nodes'].keys()
    nodes_roles_mapping = map_node_role_id(nodes_info,
                                           nodes_discover_timeout)

    for node_id, roles in nodes_roles_mapping:
        add_node_to_cluster(cluster_id, node_id, roles=roles)

    deploy(cluster_id, deploy_timeout)
    return cluster_id


@contextlib.contextmanager
def make_cluster(name, cluster):
    cid = deploy_cluster(name, cluster)
    try:
        yield cid
    finally:
        delete_cluster(cid)

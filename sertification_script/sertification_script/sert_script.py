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
from fuel_rest_api import get_all_nodes, set_node_name, get_clusters, create_empty_cluster
from tests import base

import sys

sys.path.insert(0, '../lib/requests')

logger = None


def set_logger(log):
    global logger
    logger = log


def set_node_names(cluster):
    names = [i.strip() for i in cluster['node_names'].split(',')]
    nodes = list(get_all_nodes())

    for node, name in zip(nodes, names):
        node.set_node_name(name)


def map_node_role_id(nodes, timeout):
    logger.debug("Waiting for nodes %s to be discovered..." % nodes.keys())
    for _ in range(timeout):
        nodes_discovered = get_all_nodes()

        if set(nodes).issubset([node['name'] for node in nodes_discovered]):
            return [(node['id'], nodes[node.name]) for node in
                    nodes_discovered if node.name in nodes]
        time.sleep(1)

    raise Exception('Timeout exception')


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


def deploy_cluster(cluster_desc):
    cluster = create_empty_cluster(cluster_desc)

    num_nodes = len(cluster['nodes'])
    logger.debug("Waiting for %d nodes to be discovered..." % num_nodes)
    nodes_discover_timeout = cluster_desc.get('nodes_discovery_timeout', 3600)
    deploy_timeout = cluster_desc.get('DEPLOY_TIMEOUT', 3600)

    nodes_info = cluster_desc['nodes']
    nodes_roles_mapping = map_node_role_id(nodes_info,
                                           nodes_discover_timeout)

    for node_id, roles in nodes_roles_mapping:
        cluster.add_node(node_id, roles=roles)

    cluster.deploy(deploy_timeout)
    return cluster


@contextlib.contextmanager
def make_cluster(cluster, auto_delete):
    if auto_delete:
        for cluster_obj in get_clusters():
            if cluster_obj.name == cluster['name']:
                cluster_obj.delete_cluster()

    c = deploy_cluster(cluster)
    try:
        yield c
    finally:
        c.delete_cluster()


def with_cluster(config_path):
    cluster_desc = yaml.load(open(config_path).read())

    def decorator(f):
        @functools.wraps(f)
        def wrapper(*args, **kwargs):
            with make_cluster(cluster_desc) as cluster:
                arg_spec = inspect.getargspec(f)
                if 'cluster_id' in arg_spec.args[len(arg_spec.defaults) - 1:]:
                    kwargs['cluster_id'] = cluster.id
                return f(*args, **kwargs)
        return wrapper
    return decorator


if __name__ == '__main__':
    with_cluster('config.yaml')
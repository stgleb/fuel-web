import time

from sertification_script.fuel_rest_api import api_request
from sertification_script.tests import base


class OSTFTests(base.BaseTests):

    def run_tests(self, tests):
        test_data = []
        for test in tests:
            test_data.append(
                {'testset': test,
                 'tests': [],
                 'metadata': {'cluster_id': self.cluster_id}})
        headers = {'Content-type': 'application/json'}
        testruns = api_request('/ostf/testruns', 'POST', data=test_data,
                               headers=headers)
        started_at = time.time()
        finished_testruns = []
        while testruns:
            if time.time() - started_at < self.timeout:
                for testrun in testruns:
                    testrun_resp = api_request('/ostf/testruns/%s' % testrun['id'])
                    if testrun_resp['status'] != 'finished':
                        time.sleep(5)
                        continue
                    else:
                        finished_testruns.append(testrun_resp)
                        testruns.remove(testrun)
            else:
                raise Exception('Timeout error')
        return finished_testruns

    def get_available_tests(self):
        testsets = api_request('/ostf/testsets/%s' % str(self.cluster_id))
        return [testset['id'] for testset in testsets]
import time


import base
from certification_script.certification_script.fuel_rest_api import Urllib2HTTP


class OSTFTests(base.BaseTests):

    def run_tests(self, tests):
        test_data = []
        for test in tests:
            test_data.append(
                {'testset': test,
                 'tests': [],
                 'metadata': {'cluster_id': self.cluster_id}})
        headers = {'Content-type': 'application/json'}

        req = Urllib2HTTP()
        testruns = req.do('POST', '/ostf/testruns', params=test_data)

        started_at = time.time()
        finished_testruns = []
        while testruns:
            if time.time() - started_at < self.timeout:
                for testrun in testruns:
                    testrun_resp = req.do(path='/ostf/testruns/%s' % testrun['id'])
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
        req = Urllib2HTTP()
        testsets = req.do(path='/ostf/testsets/%s' % str(self.cluster_id))
        return [testset['id'] for testset in testsets]
import unittest
import json
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ansible_link.ansible_link import app, load_config

class TestAnsibleLink(unittest.TestCase):
    def setUp(self):
        self.app = app.test_client()
        self.app.testing = True

    def test_health_check(self):
        response = self.app.get('/health')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertEqual(data['status'], 'healthy')

    def test_load_config(self):
        test_config = load_config()
        self.assertIsInstance(test_config, dict)
        self.assertIn('playbook_dir', test_config)
        self.assertIn('inventory_file', test_config)

    def test_playbook_endpoint(self):
        payload = {
            'playbook': 'test_playbook.yml',
            'inventory': 'test_inventory.ini',
            'vars': {'test_var': 'test_value'}
        }
        response = self.app.post('/ansible/playbook', json=payload)
        self.assertEqual(response.status_code, 202)
        data = json.loads(response.data)
        self.assertIn('job_id', data)
        self.assertEqual(data['status'], 'running')

    def test_jobs_endpoint(self):
        response = self.app.get('/ansible/jobs')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertIsInstance(data, dict)

    def test_job_endpoint(self):
        payload = {'playbook': 'test_playbook.yml'}
        response = self.app.post('/ansible/playbook', json=payload)
        job_id = json.loads(response.data)['job_id']

        response = self.app.get(f'/ansible/job/{job_id}')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertIn('status', data)

    def test_job_output_endpoint(self):
        payload = {'playbook': 'test_playbook.yml'}
        response = self.app.post('/ansible/playbook', json=payload)
        job_id = json.loads(response.data)['job_id']

        response = self.app.get(f'/ansible/job/{job_id}/output')

if __name__ == '__main__':
    unittest.main()
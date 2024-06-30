import unittest
import json
import time
from pathlib import Path

from ansible_link import init_app, load_config, VERSION
API_PATH=f'/api/v{VERSION.split(".")[0]}'

class TestAnsibleLink(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = init_app()
        cls.client = cls.app.test_client()
        cls.app.testing = True
        
    def test_health_check(self):
        response = self.client.get('/health')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertEqual(data['status'], 'healthy')

    def test_load_config(self):
        config = load_config()
        self.assertIsInstance(config, dict)
        
        required_keys = [
            'host', 'port', 'debug', 'suppress_ansible_output', 
            'omit_event_data', 'only_failed_event_data', 'metrics_port', 
            'playbook_dir', 'inventory_file', 'job_storage_dir', 
            'log_level', 'playbook_whitelist'
        ]
        for key in required_keys:
            self.assertIn(key, config, f"Required key '{key}' not found in config")
        
        self.assertIsInstance(config['port'], int, "Expected 'port' to be an integer")
        self.assertIsInstance(config['debug'], bool, "Expected 'debug' to be a boolean")
        self.assertIsInstance(config['playbook_whitelist'], list, "Expected 'playbook_whitelist' to be a list")

    def test_playbook_endpoint(self):
        payload = {
            'playbook': 'test_playbook.yml',
            'inventory': 'test_inventory.ini',
            'vars': {'test_var': 'test_value'}
        }
        response = self.client.post(f'{API_PATH}/ansible/playbook', json=payload)
        self.assertEqual(response.status_code, 202)
        data = json.loads(response.data)
        self.assertIn('job_id', data)
        self.assertEqual(data['status'], 'running')

    def test_job_creation_and_retrieval(self):
        config = load_config()
        payload = {
            'playbook': 'test_playbook.yml',
            'inventory': 'test_inventory.ini',
            'vars': {'test_var': 'test_value'}
        }
        response = self.client.post(f'{API_PATH}/ansible/playbook', json=payload)
        self.assertEqual(response.status_code, 202)
        job_data = json.loads(response.data)
        job_id = job_data['job_id']
        
        time.sleep(2)
        
        job_file_path = Path(config['job_storage_dir']) / f"{job_id}.json"
        self.assertTrue(job_file_path.exists(), f"Job file {job_file_path} does not exist")
        
        job_folder_path = Path(config['job_storage_dir']) / job_id
        self.assertTrue(job_folder_path.exists(), f"Job folder {job_folder_path} does not exist")
        
        response = self.client.get(f'{API_PATH}/ansible/job/{job_id}')
        self.assertEqual(response.status_code, 200, f"Failed to retrieve job {job_id}, status code: {response.status_code}")
        job_data = json.loads(response.data)
        
        response = self.client.get(f'{API_PATH}/ansible/jobs')
        self.assertEqual(response.status_code, 200, f"Failed to retrieve jobs list, status code: {response.status_code}")
        jobs_data = json.loads(response.data)
        
        self.assertIn(job_id, jobs_data, f"Job {job_id} not found in jobs list")
        
        max_wait_time = 10
        wait_interval = 1
        elapsed_time = 0

        while elapsed_time < max_wait_time:
            response = self.client.get(f'{API_PATH}/ansible/job/{job_id}')
            self.assertEqual(response.status_code, 200, f"Failed to retrieve job {job_id}, status code: {response.status_code}")
            job_data = json.loads(response.data)
            if job_data['status'] not in ['running', 'pending']:
                break
            time.sleep(wait_interval)
            elapsed_time += wait_interval
        time.sleep(8)
        self.assertNotEqual(job_data['status'], 'running', f"Job {job_id} is still running after {max_wait_time} seconds")

        # check keys using endpoint
        expected_keys = ['status', 'playbook', 'inventory', 'vars', 'start_time', 'ansible_cli_command']
        for key in expected_keys:
            self.assertIn(key, job_data, f"Expected key '{key}' not found in job data")
        
        # check keys using file on disk
        with open(job_file_path, 'r') as f:
            file_data = json.load(f)
        for key in expected_keys:
            self.assertIn(key, file_data, f"Expected key '{key}' not found in job file")

if __name__ == '__main__':
    unittest.main()
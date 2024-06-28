import unittest
import json
import sys
import os

from ansible_link import app, load_config, VERSION
API_PATH=f'/api/v{VERSION.split(".")[0]}'

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
        response = self.app.post(f'{API_PATH}/ansible/playbook', json=payload)
        self.assertEqual(response.status_code, 202)
        data = json.loads(response.data)
        self.assertIn('job_id', data)
        self.assertEqual(data['status'], 'running')

if __name__ == '__main__':
    unittest.main()
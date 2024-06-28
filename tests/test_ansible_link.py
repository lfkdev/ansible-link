import unittest
import json
import sys
import os
from unittest.mock import patch, MagicMock
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ansible_link.ansible_link import app, load_config, validate_playbook

class TestAnsibleLink(unittest.TestCase):
    def setUp(self):
        self.app = app.test_client()
        self.app.testing = True
        self.config = {
            'playbook_dir': '/tmp/playbooks',
            'inventory_file': '/tmp/inventory.ini',
            'playbook_whitelist': [r'test_.*\.yml', r'production_.*\.yaml']
        }

    def test_health_check(self):
        response = self.app.get('/health')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertEqual(data['status'], 'healthy')

    @patch('ansible_link.ansible_link.load_config')
    def test_load_config(self, mock_load_config):
        mock_load_config.return_value = self.config
        test_config = load_config()
        self.assertIsInstance(test_config, dict)
        self.assertIn('playbook_dir', test_config)
        self.assertIn('inventory_file', test_config)
        self.assertIn('playbook_whitelist', test_config)

    @patch('ansible_link.ansible_link.validate_playbook')
    @patch('ansible_link.ansible_link.Path')
    def test_playbook_endpoint(self, mock_path, mock_validate_playbook):
        mock_path.return_value.is_file.return_value = True
        mock_validate_playbook.return_value = '/tmp/playbooks/test_playbook.yml'
        
        payload = {
            'playbook': 'test_playbook.yml',
            'inventory': 'test_inventory.ini',
            'vars': {'test_var': 'test_value'}
        }
        response = self.app.post('/api/v1/ansible/playbook', json=payload)
        self.assertEqual(response.status_code, 202)
        data = json.loads(response.data)
        self.assertIn('job_id', data)
        self.assertEqual(data['status'], 'running')

    def test_jobs_endpoint(self):
        response = self.app.get('/api/v1/ansible/jobs')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertIsInstance(data, dict)

    @patch('ansible_link.ansible_link.validate_playbook')
    @patch('ansible_link.ansible_link.Path')
    def test_job_endpoint(self, mock_path, mock_validate_playbook):
        mock_path.return_value.is_file.return_value = True
        mock_validate_playbook.return_value = '/tmp/playbooks/test_playbook.yml'
        
        payload = {'playbook': 'test_playbook.yml'}
        response = self.app.post('/api/v1/ansible/playbook', json=payload)
        job_id = json.loads(response.data)['job_id']

        response = self.app.get(f'/api/v1/ansible/job/{job_id}')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertIn('status', data)

    @patch('ansible_link.ansible_link.validate_playbook')
    @patch('ansible_link.ansible_link.Path')
    def test_job_output_endpoint(self, mock_path, mock_validate_playbook):
        mock_path.return_value.is_file.return_value = True
        mock_validate_playbook.return_value = '/tmp/playbooks/test_playbook.yml'
        
        payload = {'playbook': 'test_playbook.yml'}
        response = self.app.post('/api/v1/ansible/playbook', json=payload)
        job_id = json.loads(response.data)['job_id']

        response = self.app.get(f'/api/v1/ansible/job/{job_id}/output')
        self.assertEqual(response.status_code, 202)  # Assuming job is still running

    @patch('ansible_link.ansible_link.Path')
    def test_playbook_whitelist(self, mock_path):
        mock_path.return_value.is_file.return_value = True
        mock_path.return_value.suffix = '.yml'

        # valid playbooks
        self.assertEqual(validate_playbook('test_playbook.yml'), '/tmp/playbooks/test_playbook.yml')
        self.assertEqual(validate_playbook('production_playbook.yaml'), '/tmp/playbooks/production_playbook.yaml')

        # invalid playbooks
        with self.assertRaises(ValueError):
            validate_playbook('invalid_playbook.yml')
        with self.assertRaises(ValueError):
            validate_playbook('test_playbook.yaml')  # yaml should error

    def test_invalid_playbook_request(self):
        payload = {
            'playbook': 'invalid_playbook.yml',
            'inventory': 'non_existent_inventory.ini',
            'vars': 'invalid_vars'  # should be dict
        }
        response = self.app.post('/api/v1/ansible/playbook', json=payload)
        self.assertEqual(response.status_code, 400)
        data = json.loads(response.data)
        self.assertIn('errors', data)
        self.assertTrue(any('whitelist' in error for error in data['errors']))
        self.assertTrue(any('vars' in error for error in data['errors']))

    @patch('ansible_link.ansible_link.validate_playbook')
    @patch('ansible_link.ansible_link.Path')
    def test_playbook_with_tags(self, mock_path, mock_validate_playbook):
        mock_path.return_value.is_file.return_value = True
        mock_validate_playbook.return_value = '/tmp/playbooks/test_playbook.yml'
        
        payload = {
            'playbook': 'test_playbook.yml',
            'tags': 'tag1,tag2',
            'skip_tags': 'tag3,tag4'
        }
        response = self.app.post('/api/v1/ansible/playbook', json=payload)
        self.assertEqual(response.status_code, 202)
        data = json.loads(response.data)
        self.assertIn('job_id', data)

    def test_version_endpoint(self):
        response = self.app.get('/version')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertIn('version', data)

if __name__ == '__main__':
    unittest.main()
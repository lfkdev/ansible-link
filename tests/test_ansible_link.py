import unittest
from unittest.mock import patch, MagicMock
from flask import Flask
from flask.testing import FlaskClient
import json
import yaml
from pathlib import Path

# Import the main application
from ansible_link.ansible_link import app, load_config, validate_playbook, run_playbook

class TestAnsibleLink(unittest.TestCase):
    def setUp(self):
        self.app = app.test_client()
        self.app.testing = True

    @patch('ansible_link.load_config')
    def test_load_config(self, mock_load_config):
        mock_config = {
            'playbook_dir': '/tmp/playbooks',
            'inventory_dir': '/tmp/inventory',
            'job_storage_dir': '/tmp/job-storage',
            'playbook_whitelist': ['test_playbook.yml']
        }
        mock_load_config.return_value = mock_config
        config = load_config()
        self.assertEqual(config, mock_config)

    @patch('ansible_link.config')
    @patch('pathlib.Path.is_file')
    def test_validate_playbook_valid(self, mock_is_file, mock_config):
        mock_config.__getitem__.return_value = '/tmp/playbooks'
        mock_is_file.return_value = True
        result = validate_playbook('test_playbook.yml')
        self.assertEqual(result, '/tmp/playbooks/test_playbook.yml')

    @patch('ansible_link.config')
    @patch('pathlib.Path.is_file')
    def test_validate_playbook_invalid(self, mock_is_file, mock_config):
        mock_config.__getitem__.return_value = '/tmp/playbooks'
        mock_is_file.return_value = False
        with self.assertRaises(ValueError):
            validate_playbook('invalid_playbook.yml')

    @patch('ansible_runner.run')
    @patch('ansible_link.validate_playbook')
    def test_run_playbook(self, mock_validate_playbook, mock_ansible_runner):
        mock_validate_playbook.return_value = '/tmp/playbooks/test_playbook.yml'
        mock_runner = MagicMock()
        mock_runner.status = 'successful'
        mock_runner.stdout.read.return_value = 'Playbook output'
        mock_runner.stderr.read.return_value = ''
        mock_runner.stats = {'ok': 1, 'failed': 0}
        mock_ansible_runner.return_value = mock_runner

        job_id = 'test_job_id'
        playbook = 'test_playbook.yml'
        inventory = 'test_inventory'
        vars = {'test_var': 'value'}

        run_playbook(job_id, playbook, inventory, vars)

        self.assertEqual(mock_ansible_runner.call_count, 1)
        self.assertEqual(mock_validate_playbook.call_count, 1)

    def test_playbook_endpoint(self):
        data = {
            'playbook': 'test_playbook.yml',
            'inventory': 'test_inventory',
            'vars': {'test_var': 'value'}
        }
        response = self.app.post('/ansible/playbook', json=data)
        self.assertEqual(response.status_code, 202)
        result = json.loads(response.data)
        self.assertIn('job_id', result)
        self.assertEqual(result['status'], 'running')

    def test_jobs_endpoint(self):
        response = self.app.get('/ansible/jobs')
        self.assertEqual(response.status_code, 200)
        result = json.loads(response.data)
        self.assertIsInstance(result, dict)

    def test_health_check(self):
        response = self.app.get('/health')
        self.assertEqual(response.status_code, 200)
        result = json.loads(response.data)
        self.assertEqual(result['status'], 'healthy')

if __name__ == '__main__':
    unittest.main()
# ANSIBLE-LINK
# info: github.com/lfkdev/ansible-link
# author: l.klostermann@pm.me
# license: MPL2

from werkzeug.middleware.proxy_fix import ProxyFix
from flask_restx import Api, Resource, fields
from flask import Flask, request, jsonify
from datetime import datetime
from pathlib import Path
import ansible_runner
import threading
import logging
import json
import uuid
import yaml
import os
import re

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app)
api = Api(app, version='0.9', title='ANSIBLE-LINK',
          description='API for executing Ansible playbooks')

ns = api.namespace('ansible', description='Ansible operations')

def load_config():
    config_path = os.environ.get('ANSIBLE_API_CONFIG', 'config.yml')
    try:
        with open(config_path, 'r') as f:
            return yaml.safe_load(f)
    except Exception as e:
        logger.error(f"Failed to load configuration: {e} - is ANSIBLE_API_CONFIG set correctly?")
        raise

config = load_config()

job_storage_dir = Path(config.get('job_storage_dir', '/var/lib/ansible-link/job-storage'))
job_storage_dir.mkdir(parents=True, exist_ok=True)

playbook_whitelist = config.get('playbook_whitelist', [])

# regex whitelist support
compiled_whitelist = [re.compile(pattern) for pattern in playbook_whitelist]

def validate_playbook(playbook):
    playbook_path = Path(config['playbook_dir']) / playbook
    if not playbook_path.is_file():
        raise ValueError(f"Playbook {playbook_path} not found")
    if playbook_path.suffix not in ['.yml', '.yaml']:
        raise ValueError(f"Invalid playbook file type: {playbook}")

    if compiled_whitelist and not any(pattern.match(playbook) for pattern in compiled_whitelist):
        raise ValueError(f"Playbook {playbook} is not in the whitelist")

    return str(playbook_path)


playbook_model = api.model('PlaybookRequest', {
    'playbook': fields.String(required=True, description='Playbook name'),
    'inventory': fields.String(description='Inventory file'),
    'vars': fields.Raw(description='Variables for the playbook'),
})

job_model = api.model('JobResponse', {
    'job_id': fields.String(description='Unique job ID'),
    'status': fields.String(description='Current job status'),
})

jobs = {}

def save_job_to_disk(job_id, job_data):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{job_data['playbook']}_{timestamp}_{job_id}.json"
    file_path = job_storage_dir / filename
    with open(file_path, 'w') as f:
        json.dump(job_data, f, indent=2)
    logger.info(f"Job {job_id} saved to {file_path}")

def run_playbook(job_id, playbook, inventory, vars):
    try:
        playbook_path = validate_playbook(playbook)
        inventory_path = Path(config['inventory_dir']) / inventory if inventory else None

        tags = vars.pop('ansible_tags', None)

        runner_config = {
            'playbook': playbook_path,
            'inventory': str(inventory_path) if inventory_path else None,
            'extravars': vars
        }

        # handle tags, implement proper way later
        if tags:
            runner_config['tags'] = tags

        runner = ansible_runner.run(**runner_config)

        jobs[job_id]['status'] = 'completed' if runner.status == 'successful' else 'failed'
        jobs[job_id]['stdout'] = runner.stdout.read()
        jobs[job_id]['stderr'] = runner.stderr.read()
        jobs[job_id]['stats'] = runner.stats

        logger.info(f"Job {job_id} completed with status: {jobs[job_id]['status']}")
        
        save_job_to_disk(job_id, jobs[job_id])
    except Exception as e:
        logger.error(f"Error in job {job_id}: {str(e)}")
        jobs[job_id]['status'] = 'error'
        jobs[job_id]['error'] = str(e)
        save_job_to_disk(job_id, jobs[job_id])

@ns.route('/playbook')
class AnsiblePlaybook(Resource):
    @ns.expect(playbook_model)
    @ns.marshal_with(job_model)
    def post(self):
        try:
            data = api.payload
            job_id = str(uuid.uuid4())
            jobs[job_id] = {
                'status': 'running',
                'playbook': data['playbook'],
                'inventory': data.get('inventory'),
                'vars': data.get('vars', {}),
                'start_time': datetime.now().isoformat(),
            }
            
            thread = threading.Thread(target=run_playbook, args=(job_id, data['playbook'], data.get('inventory'), data.get('vars', {})))
            thread.start()
            
            logger.info(f"Started job {job_id} for playbook {data['playbook']}")
            return {'job_id': job_id, 'status': 'running'}, 202
        except Exception as e:
            logger.error(f"Error starting playbook: {str(e)}")
            return {'error': str(e)}, 400

@ns.route('/jobs')
class JobList(Resource):
    def get(self):
        return {job_id: {'status': job['status']} for job_id, job in jobs.items()}

@ns.route('/job/<string:job_id>')
@ns.param('job_id', 'The job identifier')
class Job(Resource):
    def get(self, job_id):
        if job_id not in jobs:
            logger.warning(f"Job {job_id} not found")
            api.abort(404, f"Job {job_id} not found")
        return jobs[job_id]

@ns.route('/job/<string:job_id>/output')
@ns.param('job_id', 'The job identifier')
class JobOutput(Resource):
    def get(self, job_id):
        if job_id not in jobs:
            logger.warning(f"Job {job_id} not found")
            api.abort(404, f"Job {job_id} not found")
        if jobs[job_id]['status'] == 'running':
            return {'message': 'Job is still running'}, 202
        return {
            'stdout': jobs[job_id].get('stdout', ''),
            'stderr': jobs[job_id].get('stderr', ''),
            'stats': jobs[job_id].get('stats', {})
        }

# simple healthcheck placeholder
@app.route('/health')
def health_check():
    return jsonify({"status": "healthy"}), 200

if __name__ == '__main__':
    app.run(debug=config.get('debug', False), host=config.get('host', '0.0.0.0'), port=config.get('port', 5000))
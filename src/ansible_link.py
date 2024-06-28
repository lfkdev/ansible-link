#!/usr/bin/env python3
# ANSIBLE-LINK
# info: github.com/lfkdev/ansible-link
# author: l.klostermann@pm.me
# license: MPL2

from werkzeug.middleware.proxy_fix import ProxyFix
from flask_restx import Api, Resource, fields
from flask import Flask, jsonify

from version import VERSION
from webhook import WebhookSender

from ansible_runner.config.runner import RunnerConfig
import ansible_runner

from prometheus_client import Counter, Histogram, Gauge, start_http_server

from datetime import datetime
from pathlib import Path
import threading
import logging
import base64
import json
import uuid
import yaml
import os
import re

app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app)
prefix=f'/api/v{VERSION.split(".")[0]}'
api = Api(app, 
          version='0.9',
          title='ANSIBLE-LINK',
          description='API for executing Ansible playbooks',
          external_doc={'description': 'GitHub', 'url': 'https://github.com/lfkdev/ansible-link'},
          prefix=prefix
)

ns = api.namespace('ansible', description='Ansible operations')

def load_config():
    current_dir = Path(__file__).parent.absolute()
    default_config_path = current_dir / 'config.yml'
    config_path = os.environ.get('ANSIBLE_LINK_CONFIG_PATH', default_config_path)
    print(f"{datetime.now().isoformat()} - INFO - Loading configuration from {config_path}")
    try:
        with open(config_path, 'r') as f:
            return yaml.safe_load(f)
    except Exception as e:
        print(f"{datetime.now().isoformat()} - ERROR - Failed to load configuration: {e} - is ANSIBLE_LINK_CONFIG_PATH set correctly?")
        raise   

def validate_playbook(playbook):
    playbook_path = Path(config['playbook_dir']) / playbook
    if not playbook_path.is_file():
        raise ValueError(f"Playbook {playbook_path} not found")
    if playbook_path.suffix not in ['.yml', '.yaml']:
        raise ValueError(f"Invalid playbook file type: {playbook}")

    if compiled_whitelist and not any(pattern.match(playbook) for pattern in compiled_whitelist):
        raise ValueError(f"Playbook {playbook} is not in the whitelist")

    return str(playbook_path)

def validate_playbook_request(data, config):
    errors = []

    try:
        playbook_path = validate_playbook(data['playbook'])
    except ValueError as e:
        errors.append(str(e))
    else:
        data['playbook_path'] = playbook_path

    if 'inventory' in data:
        inventory_path = Path(data['inventory'])
        if not inventory_path.is_file():
            errors.append(f"Inventory file not found: {inventory_path}")
    else:
        inventory_path = Path(config['inventory_file'])
        if not inventory_path.is_file():
            errors.append(f"Default inventory file not found: {inventory_path}")
    data['inventory_path'] = str(inventory_path)

    if 'vars' in data and not isinstance(data['vars'], dict):
        errors.append("'vars' must be a dictionary")

    if 'forks' in data:
        try:
            forks = int(data['forks'])
            if forks < 1:
                errors.append("'forks' must be a positive integer")
        except ValueError:
            errors.append("'forks' must be an integer")

    if 'verbosity' in data:
        try:
            verbosity = int(data['verbosity'])
            if verbosity not in range(5):  # 0 to 4
                errors.append("'verbosity' must be an integer between 0 and 4")
        except ValueError:
            errors.append("'verbosity' must be an integer")

    if 'limit' in data and not isinstance(data['limit'], str):
        errors.append("'limit' must be a string")

    for tag_field in ['tags', 'skip_tags']:
        if tag_field in data:
            if not isinstance(data[tag_field], str):
                errors.append(f"'{tag_field}' must be a comma-separated string")
            else:
                tags = data[tag_field].split(',')
                for tag in tags:
                    if not re.match(r'^[a-zA-Z0-9_]+$', tag.strip()):
                        errors.append(f"Invalid tag in '{tag_field}': {tag}")

    if 'cmdline' in data and not isinstance(data['cmdline'], str):
        errors.append("'cmdline' must be a string")

    return errors

playbook_model = api.model('PlaybookRequest', {
    'playbook': fields.String(required=True, description='Playbook name (e.g., "site.yml")'),
    'inventory': fields.String(description='Inventory file name. If not provided, the default inventory will be used.'),
    'vars': fields.Raw(description='Variables for the playbook as a dictionary'),
    'forks': fields.Integer(description='Number of parallel processes to use. Default is 5.', default=5),
    'verbosity': fields.Integer(description='Ansible verbosity level (0-4). Default is 0.', default=0, min=0, max=4),
    'limit': fields.String(description='Limit the playbook run to specific hosts or groups (e.g., "webservers,dbservers")'),
    'tags': fields.String(description='Comma-separated string of tags to run in the playbook (e.g., "tag1,tag2")'),
    'skip_tags': fields.String(description='Comma-separated string of tags to skip in the playbook (e.g., "tag3,tag4")'),
    'cmdline': fields.String(description='Custom command-line arguments for Ansible')
})

job_model = api.model('JobResponse', {
    'job_id': fields.String(description='Unique job ID (UUID)'),
    'status': fields.String(description='Current job status (e.g., "running", "completed", "failed", "error")'),
    'errors': fields.List(fields.String, description='List of error messages, if any', allow_none=True)
})

jobs = {} # memory job storage

def save_job_to_disk(job_id, job_data):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base_playbook_name = os.path.basename(job_data['playbook']).replace('.yml', '_yml').replace('.yaml', '_yaml')  
    filename = f"{base_playbook_name}_{timestamp}_{job_id}.json"
    file_path = job_storage_dir / filename
    with open(file_path, 'w') as f:
        json.dump(job_data, f, indent=2)
    logger.info(f"Job {job_id} saved to {file_path}")

def run_playbook(job_id, playbook_path, inventory_path, vars, forks=5, verbosity=0, limit=None, tags=None, skip_tags=None, cmdline=None):
    ACTIVE_JOBS.inc()
    start_time = datetime.now()

    webhook_sender.send("job_started", {
        "job_id": job_id,
        "playbook": playbook_path,
        "status": "started"
    })

    try:
        job_private_data_dir = job_storage_dir / job_id
        job_private_data_dir.mkdir(parents=True, exist_ok=True)

        runner_config = RunnerConfig(
            private_data_dir=str(job_private_data_dir),
            playbook=playbook_path,
            inventory=inventory_path,
            extravars=vars,
            limit=limit,
            verbosity=verbosity,
            forks=forks,
            tags=tags,
            skip_tags=skip_tags,
            cmdline=cmdline,
            suppress_ansible_output=config.get('suppress_ansible_output', False),
            omit_event_data=config.get('omit_event_data', False),
            only_failed_event_data=config.get('only_failed_event_data', False)
        )
        logger.debug(f"RunnerConfig: {runner_config.__dict__}")

        runner_config.prepare()

        runner = ansible_runner.Runner(config=runner_config)
        ansible_command = ' '.join(runner.config.command)
        logger.info(f"Runner: {ansible_command}")
        result = runner.run()

        logger.debug(f"Runner result: {result}")

        status = 'completed' if runner.status == 'successful' else 'failed'
        jobs[job_id]['status'] = status
        jobs[job_id]['stdout'] = runner.stdout.read()
        jobs[job_id]['stderr'] = runner.stderr.read()
        jobs[job_id]['stats'] = runner.stats
        jobs[job_id]['ansible_command'] = ansible_command

        logger.info(f"Job {job_id} completed with status: {status}")
        
        save_job_to_disk(job_id, jobs[job_id])

        PLAYBOOK_RUNS.labels(playbook=playbook_path, status=status).inc()

        webhook_sender.send("job_completed", {
            "job_id": job_id,
            "playbook": playbook_path,
            "status": status
        })

    except Exception as e:
        logger.error(f"Error in job {job_id}: {str(e)}")
        jobs[job_id]['status'] = 'error'
        jobs[job_id]['error'] = str(e)
        save_job_to_disk(job_id, jobs[job_id])

        PLAYBOOK_RUNS.labels(playbook=playbook_path, status='error').inc()

        webhook_sender.send("job_error", {
            "job_id": job_id,
            "playbook": playbook_path,
            "status": "error",
            "error": str(e)
        })
    finally:
        ACTIVE_JOBS.dec()
        duration = (datetime.now() - start_time).total_seconds()
        PLAYBOOK_DURATION.labels(playbook=playbook_path).observe(duration)

@ns.route('/playbook')
class AnsiblePlaybook(Resource):
    @ns.expect(playbook_model)
    @ns.marshal_with(job_model)
    def post(self):
        try:
            data = api.payload

            validation_errors = validate_playbook_request(data, config)
            if validation_errors:
                logger.error(f"Validation errors: {validation_errors}")
                return {'job_id': None, 'status': 'error', 'errors': validation_errors}, 400

            job_id = str(uuid.uuid4())
            jobs[job_id] = {
                'status': 'running',
                'playbook': data['playbook_path'],
                'inventory': data['inventory_path'],
                'vars': data.get('vars', {}),
                'forks': data.get('forks', 5),
                'verbosity': data.get('verbosity', 0),
                'limit': data.get('limit'),
                'tags': data.get('tags'),
                'skip_tags': data.get('skip_tags'),
                'cmdline': data.get('cmdline'),
                'start_time': datetime.now().isoformat(),
            }

            thread = threading.Thread(target=run_playbook, args=(
                job_id, 
                data['playbook_path'],
                data['inventory_path'],
                data.get('vars', {}),
                data.get('forks', 5),
                data.get('verbosity', 0),
                data.get('limit'),
                data.get('tags'),
                data.get('skip_tags'),
                data.get('cmdline')
            ))
            thread.start()

            logger.info(f"Started job {job_id} for playbook {data['playbook']}")
            return {'job_id': job_id, 'status': 'running', 'errors': None}, 202
        except Exception as e:
            logger.error(f"Error starting playbook: {str(e)}")
            return {'job_id': None, 'status': 'error', 'errors': [str(e)]}, 400

@ns.route('/jobs')
class JobList(Resource):
    def get(self):
        return {job_id: {'status': job['status'], 'playbook': job['playbook']} for job_id, job in jobs.items()}

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

@app.route('/version')
def version_check():
    return jsonify({"version": VERSION}), 200

def init_app():
    global config, logger, job_storage_dir, compiled_whitelist, webhook_sender, PLAYBOOK_RUNS, PLAYBOOK_DURATION, ACTIVE_JOBS
    
    config = load_config()

    log_level = getattr(logging, config.get('log_level', 'INFO').upper())
    logging.basicConfig(level=log_level, format='%(asctime)s - %(levelname)s - %(message)s')
    logger = logging.getLogger(__name__)
    logger.info(f"Logging level set to {logging.getLevelName(log_level)}")
    logger.info(f"Initializing Ansible-Link, version {VERSION} - {prefix}")

    job_storage_dir = Path(config.get('job_storage_dir', Path(__file__).parent.absolute() / 'job-storage'))
    job_storage_dir.mkdir(parents=True, exist_ok=True)

    playbook_whitelist = config.get('playbook_whitelist', [])
    compiled_whitelist = [re.compile(pattern) for pattern in playbook_whitelist]

    webhook_sender = WebhookSender(config.get('webhook', {}))

    PLAYBOOK_RUNS = Counter('ansible_link_playbook_runs_total', 'Total number of playbook runs', ['playbook', 'status'])
    PLAYBOOK_DURATION = Histogram('ansible_link_playbook_duration_seconds', 'Duration of playbook runs in seconds', ['playbook'])
    ACTIVE_JOBS = Gauge('ansible_link_active_jobs', 'Number of currently active jobs')

    return app

def main():
    app = init_app()
    
    ANSIBLE_LINK_LOGO_BASE64 = "ICAgX19fICAgICAgICAgICAgXyBfXyAgIF9fICAgICAgICBfXyAgIF8gICAgICBfXyAgCiAgLyBfIHwgX19fICBfX18gKF8pIC8gIC8gL19fIF9fX18vIC8gIChfKV9fICAvIC9fXwogLyBfXyB8LyBfIFwoXy08LyAvIF8gXC8gLyAtXylfX18vIC9fXy8gLyBfIFwvICAnXy8KL18vIHxfL18vL18vX19fL18vXy5fXy9fL1xfXy8gICAvX19fXy9fL18vL18vXy9cX1wgCiAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICA="
    ANSIBLE_LINK_LOGO = base64.b64decode(ANSIBLE_LINK_LOGO_BASE64).decode('utf-8')
    print(ANSIBLE_LINK_LOGO)

    metrics_port = config.get('metrics_port', 8000)
    start_http_server(metrics_port)

    logger.info(f"Metrics server started, port {metrics_port}")

    app.run(debug=config.get('debug', False), host=config.get('host', '127.0.0.1'), port=config.get('port', 5000))


if __name__ == '__main__':
    main()
    
    
    


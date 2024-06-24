<div align="center" style="display: flex; align-items: center;">
  <img src="logo.png" alt="Ansible Link Logo" width="100" height="100" style="margin-right: 20px;">
  <div>
    <h1>ANSIBLE LINK</h1>
    <p>
      RESTful API for executing Ansible playbooks remotely. It allows users to trigger playbook executions, pass custom variables, and track the status of each execution.
    </p>
  </div>
</div>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.7%2B-blue" alt="Python">
  <img src="https://img.shields.io/badge/Platform-Linux-lightgrey" alt="Linux">
  <img src="https://img.shields.io/badge/Flask--RESTx-Swagger-green" alt="Flask-RESTx">
  <img src="https://img.shields.io/badge/Ansible--Runner-1.4-red" alt="Ansible Runner">
</p>

## Features
- **Playbook Execution** Asynchronous playbook executions with real-time status updates.
- **Playbook History** Keep track of playbook executions and their status.
- **API Documentation** Swagger UI documentation for easy exploration of the API endpoints.

<b>NOTE</b> Project is usable but still in early development

## Motivation
Searched for a way to run our playbooks over CI/CD without the need of AWX or other big projects while still being more stable and less error-prone than custom bash scripts. So I created Ansible-Link. This projects aims to be a KISS way to run ansible jobs remotely.

## Prerequisites
Python 3.7+
Your Ansible node

## Installation
* Clone the repository (on your ansible-node):
```shell
git clone git@github.com:Daemonfork/ansible-link.git
cd ansible-link
```

* Install the dependencies:
```shell
# use virtual env
pip install -r requirements.txt
```

## API Documentation
The API documentation is available via Swagger UI.

<img src="docs.png" alt="Ansible Link Docs"  style="margin-right: 20px;">

## Configuration
The API configuration is stored in the config.yaml file. You can customize the following settings:

```yaml
host: '127.0.0.1'
port: 5001
debug: false

playbook_dir: '/etc/ansible/'
inventory_dir: '/etc/ansible/hosts'
ansible_playbook_cmd: 'ansible-playbook'

job_storage_dir: '/var/lib/ansible-link/job_storage'

log_level: 'INFO'
log_file: '/var/log/ansible-link/api.log'

playbook_whitelist:
  - some_allowed_playbook.yml
  - some_other_allowed_playbook.yml

```

The whitelist supports <b>full regex</b>, you could go wild:
```yaml
playbook_whitelist:
  # Allow all playbooks in the 'test' directory
  - ^test/.*\.ya?ml$

  # Allow playbooks starting with 'prod_' or 'dev_'
  - ^(prod|dev)_.*\.ya?ml$

  # Allow specific playbooks
  - ^(backup|restore|maintenance)\.ya?ml$
```
Leave empty to allow all playbooks.

## Start the API server:
```shell
python3 ansible-link.py
```
The API will be accessible at localhost:port (default 5001) or wherever you bind it to.
**Use WSGI for prod ENV (gunicorn) + systemd service**

### unitd example file
```
[Unit]
Description=Ansible Link
After=network.target

[Service]
User=ansible
Group=ansible
WorkingDirectory=/opt/ansible-link
ExecStart=/usr/local/bin/gunicorn -w 1 -k gthread -b localhost:5000 wsgi:app
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

### Example setup:
```
/
├── etc/
│   └── ansible/
│       ├── playbooks/
│       │   └── some_playbooks.yml
│       └── inventory/
│           ├── production
│           └── staging
│
├── opt/
│   └── ansible-link/
│       ├── ansible-link.py
│       ├── config.yml
│       ├── requirements.txt
│       └── README.md
│
└── var/
    ├── lib/
    │   └── ansible-link/
    │       └── job-storage/
    │           └── playbook_name_20230624_130000_job_id.json
    └── log/
        └── ansible-link/
            └── api.log
```

### API Endpoints

* <code>POST /ansible/playbook: Execute a playbook</code>
* <code>GET /ansible/jobs: List all jobs</code>
* <code>GET /ansible/job/<job_id>: Get job status</code>
* <code>GET /ansible/job/<job_id>/output: Get job output</code>
* <code>GET /health: Health check endpoint</code>

## Usage

#### Example requests:
CLI
```shell
$ ansible-playbook monitoring_stack.yml
```

API
```json
{
  "playbook": "monitoring_stack.yml",
}
```
---
CLI
```shell
$ ansible-playbook monitoring_stack.yml -e customer="mycustomer" --tags="monitoring"
```

API
```json
{
  "playbook": "monitoring_stack.yml",
  "vars": {
    "customer": "mycustomer",
    "ansible_tags": "monitoring"
  }
}
```

### Output
Ansible-Link will save each job as .json with the following info (from ansible-runner):
```json
{
  "status": "successfull",
  "playbook": "<playbook_name>",
  "inventory": null,
  "vars": {
    "customer": "emind"
  },
 "start_time": "2024-06-24T15:32:35.380662",
  "stdout": "<ANSIBLE PLAYBOOK OUTPUT>",
  "stderr": "",
  "stats": {
    "skipped": {
      "<playbook_name>": 8
    },
    "ok": {
      "<playbook_name>": 28
    },
    "dark": {},
    "failures": {
      "<playbook_name>": 1
    },
    "ignored": {},
    "rescued": {},
    "processed": {
      "<playbook_name>": 1
    },
    "changed": {}
  }
}
```
essentially showing everything ansible-playbook would display.

## Security Considerations
* Use TLS in production
* Add basic auth
* Remove ProxyFix call if not needed in your setup

## Contributing
Contributions are always welcome - if you find any issues or have suggestions for improvements, please open an issue or submit a pull request.

## License
This project is licensed under the MPL2 License. See the LICENSE file for more information.




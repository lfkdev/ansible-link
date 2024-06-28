# ANSIBLE-LINK (webhook module)
# info: github.com/lfkdev/ansible-link
# author: l.klostermann@pm.me
# license: MPL2

import requests
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

class WebhookSender:
    def __init__(self, config):
        self.webhook_url = config.get('url')
        self.webhook_type = config.get('type', 'generic').lower()
        self.webhook_timeout = config.get('timeout', 5)

    def format_payload(self, event_type, job_data):
        base_payload = {
            "event_type": event_type,
            "job_id": job_data['job_id'],
            "playbook": job_data['playbook'],
            "status": job_data['status'],
            "timestamp": datetime.now().isoformat()
        }
        
        if 'error' in job_data:
            base_payload['error'] = job_data['error']

        if self.webhook_type == 'slack':
            color = "#36a64f" if job_data['status'] in ['completed', 'started'] else "#ff0000"
            fields = [
                {"title": "Status", "value": job_data['status'], "short": True},
            ]
            if 'error' in job_data:
                fields.append({"title": "Error", "value": job_data['error'], "short": False})
            
            return {
                "attachments": [{
                    "color": color,
                    "title": job_data['playbook'],
                    "text": f"Event: {event_type.replace('_', ' ').title()}",
                    "fields": fields,
                    "footer": f"Ansible-Link | {job_data['job_id']}",
                    "ts": int(datetime.now().timestamp())
                }]
            }
        elif self.webhook_type == 'discord':
            color = 0x36a64f if job_data['status'] in ['completed', 'started'] else 0xff0000
            fields = [
                {"name": "Status", "value": job_data['status'], "inline": True},
                {"name": "Job ID", "value": job_data['job_id'], "inline": True},
                {"name": "Event", "value": event_type.replace('_', ' ').title(), "inline": False}
            ]
            if 'error' in job_data:
                fields.append({"name": "Error", "value": job_data['error'], "inline": False})
            
            return {
                "embeds": [{
                    "title": job_data['playbook'],
                    "color": color,
                    "fields": fields,
                    "footer": {"text": "Ansible-Link"},
                    "timestamp": datetime.now().isoformat()
                }]
            }
        else:  # generic webhook
            return base_payload

    def send(self, event_type, job_data):
        if not self.webhook_url:
            logger.info("Webhook URL not configured, skipping webhook")
            return

        payload = self.format_payload(event_type, job_data)

        try:
            response = requests.post(self.webhook_url, json=payload, timeout=self.webhook_timeout)
            response.raise_for_status()
            logger.info(f"Webhook sent successfully for job {job_data['job_id']}")
        except requests.RequestException as e:
            logger.error(f"Failed to send webhook for job {job_data['job_id']}: {str(e)}")
import requests

class WorkflowManager:
    def __init__(self, hostname, token, job_id):
        self.hostname = hostname
        self.token = token
        self.job_id = job_id

    def trigger_workflow(self, catalog, config, src, table):
        api_url = f"https://{self.hostname}/api/2.1/jobs/run-now"
        headers = {"Authorization": f"Bearer {self.token}"}
        payload = {
            "job_id": self.job_id,
            "job_parameters": {
                "catalog_name": catalog,
                "config_schema_name": config,
                "source_schema_name": src,
                "table_name": table
            }
        }
        return requests.post(api_url, headers=headers, json=payload)
import requests

class WorkflowManager:
    def __init__(self, hostname, token, job_id):
        self.api_url = f"https://{hostname}/api/2.1/jobs/run-now"
        self.headers = {"Authorization": f"Bearer {token}"}
        self.job_id = job_id

    def trigger_dqx_job(self, catalog, config_schema, source_schema, table):
        payload = {
            "job_id": self.job_id,
            "job_parameters": {
                "catalog_name": catalog,
                "config_schema_name": config_schema,
                "source_schema_name": source_schema,
                "table_name": table
            }
        }
        response = requests.post(self.api_url, headers=self.headers, json=payload)
        return response
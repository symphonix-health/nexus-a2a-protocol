"""Mock FHIR Server for openhie-mediator.
Listens on port 8080.
"""
from http.server import HTTPServer, BaseHTTPRequestHandler
import json
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("mock-fhir")

class MockFHIRHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        logger.info(f"GET {self.path}")
        
        # Default empty bundle
        response = {
            "resourceType": "Bundle",
            "type": "searchset",
            "total": 0,
            "entry": []
        }

        if "/Patient" in self.path:
            # Return a mock patient
            response["total"] = 1
            response["entry"] = [{
                "resource": {
                    "resourceType": "Patient",
                    "id": "123",
                    "name": [{"family": "Doe", "given": ["John"]}],
                    "identifier": [{"system": "nid", "value": "123456789"}]
                }
            }]
        
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(response).encode("utf-8"))

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        logger.info(f"POST {self.path} - {len(body)} bytes")
        
        # Always return success for transactions
        response = {
            "resourceType": "Bundle",
            "type": "transaction-response",
            "entry": [
                {"response": {"status": "201 Created", "location": "Patient/123"}},
                {"response": {"status": "201 Created", "location": "Encounter/456"}}
            ]
        }

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(response).encode("utf-8"))

def run(port=8080):
    server = HTTPServer(("0.0.0.0", port), MockFHIRHandler)
    print(f"Mock FHIR server running on port {port}")
    server.serve_forever()

if __name__ == "__main__":
    run()

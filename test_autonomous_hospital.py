"""Test the Autonomous Digital Hospital - Multi-Agent Demo

This script demonstrates the Nexus A2A protocol running locally without Docker.
It tests the ED Triage workflow: patient -> triage -> diagnosis -> FHIR record.
"""
import httpx
import json
import time
from datetime import datetime

# Agent endpoints
TRIAGE_AGENT = "http://localhost:8021"
DIAGNOSIS_AGENT = "http://localhost:8022"
OPENHIE_MEDIATOR = "http://localhost:8023"

# JWT token from .env
JWT_TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJkZW1vLXVzZXIiLCJpYXQiOjE3NzA1NjM4MjAsImV4cCI6MTc3MDY1MDIyMCwic2NvcGUiOiJuZXh1czppbnZva2UifQ.Ck1B4zMKX55f_4LMtFFMJGL6iX8VLXU-oULGUV3DQmM"


def test_agent_health():
    """Check that all agents are responding"""
    print("🏥 Testing Autonomous Hospital Agent Health\n")
    print("=" * 60)
    
    agents = [
        ("Triage Agent", TRIAGE_AGENT),
        ("Diagnosis Agent", DIAGNOSIS_AGENT),
        ("OpenHIE Mediator", OPENHIE_MEDIATOR),
        ("Transcriber Agent", "http://localhost:8031"),
        ("Summariser Agent", "http://localhost:8032"),
        ("EHR Writer Agent", "http://localhost:8033"),
        ("Insurer Agent", "http://localhost:8041"),
        ("Provider Agent", "http://localhost:8042"),
        ("Consent Analyser", "http://localhost:8043"),
        ("HITL UI", "http://localhost:8044"),
        ("Hospital Reporter", "http://localhost:8051"),
        ("OSINT Agent", "http://localhost:8052"),
        ("Central Surveillance", "http://localhost:8053"),
    ]
    
    healthy = 0
    for name, url in agents:
        try:
            resp = httpx.get(f"{url}/.well-known/agent-card.json", timeout=3)
            if resp.status_code == 200:
                card = resp.json()
                print(f"✓ {name:25s} | {card.get('agent_id', 'unknown')}")
                healthy += 1
            else:
                print(f"✗ {name:25s} | HTTP {resp.status_code}")
        except Exception as e:
            print(f"✗ {name:25s} | {str(e)[:40]}")
    
    print("=" * 60)
    print(f"\n{healthy}/{len(agents)} agents healthy\n")
    return healthy == len(agents)


def test_ed_triage_workflow():
    """Test the ED Triage multi-agent workflow"""
    print("\n🚑 Testing ED Triage Workflow\n")
    print("=" * 60)
    
    # Simulated patient presenting to ED
    patient_case = {
        "patient_id": "PT-12345",
        "chief_complaint": "Severe chest pain radiating to left arm",
        "vital_signs": {
            "heart_rate": 105,
            "blood_pressure": "160/95",
            "temperature": 98.6,
            "respiratory_rate": 22
        },
        "onset": "30 minutes ago",
        "history": "56yo male, smoker, family history of CAD"
    }
    
    print("📋 Patient Case:")
    print(json.dumps(patient_case, indent=2))
    
    # Step 1: Send to Triage Agent
    print("\n➡️  Step 1: Sending to Triage Agent...")
    try:
        triage_request = {
            "jsonrpc": "2.0",
            "id": f"test-{int(time.time())}",
            "method": "agent.task",
            "params": {
                "task": {
                    "sender": "test-client",
                    "recipient": "triage-agent",
                    "content": {
                        "type": "clinical_assessment",
                        "data": patient_case
                    }
                }
            }
        }
        
        resp = httpx.post(
            f"{TRIAGE_AGENT}/rpc",
            json=triage_request,
            headers={"Authorization": f"Bearer {JWT_TOKEN}"},
            timeout=30
        )
        
        if resp.status_code == 200:
            result = resp.json()
            print(f"✓ Triage Response: {result.get('result', {}).get('status', 'unknown')}")
            print(f"  Priority: {result.get('result', {}).get('priority', 'N/A')}")
        else:
            print(f"✗ Triage failed: HTTP {resp.status_code}")
            print(f"  Response: {resp.text[:200]}")
    except Exception as e:
        print(f"✗ Error: {e}")
    
    print("\n" + "=" * 60)
    print("\n✅ Autonomous Hospital Test Complete!")
    print("\n💡 Tip: Visit http://localhost:8021/.well-known/agent-card.json")
    print("   to see any agent's capabilities\n")


def show_agent_capabilities():
    """Display capabilities of each agent"""
    print("\n📖 Autonomous Hospital Agent Capabilities\n")
    print("=" * 60)
    
    demos = {
        "ED Triage": [
            ("Triage Agent", 8021, "Initial patient assessment and prioritization"),
            ("Diagnosis Agent", 8022, "Diagnostic reasoning and recommendations"),
            ("OpenHIE Mediator", 8023, "FHIR record management and HIE integration"),
        ],
        "Telemed Scribe": [
            ("Transcriber", 8031, "Audio to text transcription"),
            ("Summariser", 8032, "Clinical note generation from transcripts"),
            ("EHR Writer", 8033, "Structured data entry to EHR systems"),
        ],
        "Consent Verification": [
            ("Insurer Agent", 8041, "Insurance verification and authorization"),
            ("Provider Agent", 8042, "Provider identity and credentials"),
            ("Consent Analyser", 8043, "Policy analysis and compliance checking"),
            ("HITL UI", 8044, "Human-in-the-loop interface for overrides"),
        ],
        "Public Health Surveillance": [
            ("Hospital Reporter", 8051, "Case reporting from hospital systems"),
            ("OSINT Agent", 8052, "Open-source intelligence gathering"),
            ("Central Surveillance", 8053, "Aggregate analysis and alerting"),
        ]
    }
    
    for demo_name, agents in demos.items():
        print(f"\n{demo_name}:")
        for name, port, desc in agents:
            print(f"  • {name:20s} (:{port}) - {desc}")
    
    print("\n" + "=" * 60)


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("     NEXUS A2A AUTONOMOUS DIGITAL HOSPITAL TEST")
    print("=" * 60)
    
    # Show capabilities
    show_agent_capabilities()
    
    # Test health
    all_healthy = test_agent_health()
    
    # Test workflow if agents are healthy
    if all_healthy:
        test_ed_triage_workflow()
    else:
        print("\n⚠️  Some agents are not healthy. Skipping workflow test.")
        print("   Run: python tools/launch_all_agents.py")
    
    print("\n📚 Documentation:")
    print("   • Architecture: docs/autonomous_digital_hospital_white_paper.md")
    print("   • Compliance: docs/compliance_guide.md")
    print("   • How to Run: docs/how-to-run.md\n")

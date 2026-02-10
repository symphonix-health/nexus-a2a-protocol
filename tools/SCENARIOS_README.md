# HelixCare Patient Journey Scenarios

This directory contains a comprehensive library of realistic patient journey scenarios for testing and demonstrating the HelixCare AI Hospital system.

## Files

- `helixcare_all_scenarios.json` - Complete scenario definitions in JSON format
- `scenario_summaries.md` - Human-readable scenario documentation
- `helixcare_scenarios.py` - Python scenario runner for base scenarios
- `additional_scenarios.py` - Additional specialized scenarios
- `scenario_manager.py` - Tools for managing and validating scenarios
- `run_helixcare_scenarios.py` - Simple scenario runner script
- `simulate_patient_visit.py` - Original patient visit simulation
- `simulate_patient_visit_fixed.py` - Fixed version without import issues

## Available Scenarios

### Base Scenarios (5 total)
1. **chest_pain_cardiac** - Adult male with chest pain, suspected cardiac event
2. **pediatric_fever_sepsis** - Child with high fever, suspected sepsis
3. **orthopedic_fracture** - Adult with extremity fracture
4. **geriatric_confusion** - Elderly patient with acute confusion/delirium
5. **obstetric_emergency** - Pregnant patient with vaginal bleeding

### Additional Specialized Scenarios
- **mental_health_crisis** - Adult with acute mental health crisis
- **chronic_diabetes_complication** - Diabetic patient with foot ulcer
- **trauma_motor_vehicle_accident** - Multiple trauma from MVC
- **infectious_disease_outbreak** - Patient with suspected infectious disease
- **pediatric_asthma_exacerbation** - Child with severe asthma exacerbation

## Usage

### Running Individual Scenarios
```bash
# Run a specific scenario
python tools/helixcare_scenarios.py --run chest_pain_cardiac

# List all available scenarios
python tools/helixcare_scenarios.py --list

# Save scenarios to JSON file
python tools/helixcare_scenarios.py --save
```

### Running Multiple Scenarios
```bash
# Run all scenarios sequentially
python tools/run_helixcare_scenarios.py

# Run with Command Centre monitoring
python tools/monitor_command_centre.py &
python tools/run_helixcare_scenarios.py
```

### Validating Scenarios and Agents
```bash
# Validate scenario structure and check agent availability
python tools/validate_scenarios.py
```

## Scenario Structure

Each scenario contains:
- **Patient Profile**: Age, gender, chief complaint, urgency level
- **Journey Steps**: Sequential agent interactions with realistic parameters
- **Expected Duration**: Approximate time for complete scenario execution
- **Agent Coverage**: All 8 HelixCare agents (triage, diagnosis, imaging, pharmacy, bed_manager, coordinator, discharge, followup)

## Agent Endpoints

Scenarios interact with agents running on these ports:
- Triage: 8021
- Diagnosis: 8022
- Imaging: 8024
- Pharmacy: 8025
- Bed Manager: 8026
- Discharge: 8027
- Follow-up: 8028
- Care Coordinator: 8029
- Command Centre: 8099

## Prerequisites

1. All HelixCare agents must be running
2. Command Centre should be operational for monitoring
3. Python environment with required dependencies

## Starting All Agents

```bash
# Start all agents
python tools/launch_all_agents.py

# Or use Docker Compose
docker-compose -f docker-compose-helixcare.yml up
```

## Monitoring

Run the Command Centre monitor to observe scenario execution:

```bash
python tools/monitor_command_centre.py
```

This provides real-time visibility into agent activity and scenario progress.

## Customization

Scenarios can be modified by editing the JSON files or Python definitions. Each scenario is self-contained and can be run independently or as part of larger test suites.

## Testing

These scenarios are designed to:
- Exercise all agent capabilities
- Test realistic patient workflows
- Validate inter-agent communication
- Demonstrate system integration
- Support performance testing and load simulation

## Support

For questions about scenario usage or modification, refer to the individual scenario files or the HelixCare documentation.
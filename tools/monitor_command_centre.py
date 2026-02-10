#!/usr/bin/env python3
"""
Command Centre Monitor - Real-time dashboard for observing HelixCare activity
"""

import asyncio
import httpx
import json
import time
from datetime import datetime

async def monitor_command_centre():
    """Monitor Command Centre and display real-time agent activity."""

    print("🎯 Command Centre Monitor Started")
    print("📊 Monitoring 19 HelixCare agents in real-time")
    print("=" * 60)

    async with httpx.AsyncClient(timeout=10.0) as client:
        while True:
            try:
                # Get agent status
                response = await client.get("http://localhost:8099/api/agents")
                agents = response.json()

                # Get health status
                health_response = await client.get("http://localhost:8099/health")
                health = health_response.json()

                # Clear screen and show status
                print(f"\033[2J\033[H")  # Clear screen
                print(f"🎯 HelixCare Command Centre - {datetime.now().strftime('%H:%M:%S')}")
                print(f"📊 Status: {health.get('status', 'unknown').upper()}")
                print(f"🤖 Agents Monitored: {health.get('monitored_agents', 0)}")
                print("=" * 60)

                # Show agent status summary
                healthy = sum(1 for agent in agents if agent.get('status') == 'healthy')
                unhealthy = sum(1 for agent in agents if agent.get('status') != 'healthy')

                print(f"✅ Healthy Agents: {healthy}")
                print(f"⚠️  Other Status: {unhealthy}")
                print()

                # Show individual agent status
                print("Agent Status Overview:")
                for agent in sorted(agents, key=lambda x: x.get('name', '')):
                    name = agent.get('name', 'Unknown')
                    status = agent.get('status', 'unknown')
                    health_score = agent.get('health_score', 0)
                    last_seen = agent.get('last_seen', 'Never')

                    # Color coding
                    if status == 'healthy':
                        status_icon = "🟢"
                    elif status == 'unhealthy':
                        status_icon = "🔴"
                    else:
                        status_icon = "🟡"

                    print(f"  {status_icon} {name:<25} | {status:<10} | Score: {health_score:.2f} | Last: {last_seen[-8:]}")

                print("\n" + "=" * 60)
                print("💡 Tip: Watch for changing health scores and status updates")
                print("🔄 Refreshing every 3 seconds... (Ctrl+C to stop)")

            except Exception as e:
                print(f"❌ Error connecting to Command Centre: {e}")
                print("🔄 Retrying in 5 seconds...")

            await asyncio.sleep(3)

if __name__ == "__main__":
    try:
        asyncio.run(monitor_command_centre())
    except KeyboardInterrupt:
        print("\n🛑 Command Centre Monitor stopped")
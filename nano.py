#!/usr/bin/env python3
"""
Simple Microphone Monitor - Logs apps accessing microphone on macOS
Uses log monitoring to detect microphone access events
"""

import subprocess
import time
import re
import signal
import sys
from datetime import datetime
import threading

# Color codes for terminal output
class Colors:
    RED = '\033[91m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    RESET = '\033[0m'
    BOLD = '\033[1m'

# Global state
running = True
active_apps = {}  # app_name: timestamp

def signal_handler(signum, frame):
    """Handle Ctrl+C gracefully"""
    global running
    running = False
    print(f"\n{Colors.YELLOW}Stopping monitor...{Colors.RESET}")
    sys.exit(0)

def monitor_microphone_logs():
    """Monitor system logs for microphone access events"""
    print(f"\n{Colors.BOLD}🎙️  Microphone Monitor Started{Colors.RESET}")
    print(f"{Colors.BLUE}Monitoring microphone access...{Colors.RESET}\n")
    
    # Monitor TCC (Transparency, Consent, and Control) logs
    log_cmd = [
        'log', 'stream',
        '--predicate', 
        '(subsystem == "com.apple.TCC" OR eventMessage CONTAINS "microphone" OR eventMessage CONTAINS "audio input") AND (category == "access" OR eventMessage CONTAINS "granted" OR eventMessage CONTAINS "allowed")',
        '--style', 'compact'
    ]
    
    # Also monitor for Safari specifically
    safari_cmd = [
        'log', 'stream',
        '--predicate',
        'process == "Safari" AND (eventMessage CONTAINS "microphone" OR eventMessage CONTAINS "getUserMedia")',
        '--style', 'compact'
    ]
    
    # Start both log monitors
    process = subprocess.Popen(log_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, 
                              text=True, bufsize=1)
    
    # Patterns to extract app names
    patterns = {
        'tcc_pattern': re.compile(r'(?:client|process):\s*"?([^"]+)"?\s*(?:request|access|granted).*microphone', re.IGNORECASE),
        'bundle_pattern': re.compile(r'(?:bundle|identifier):\s*"?([^"]+)"?.*microphone', re.IGNORECASE),
        'app_pattern': re.compile(r'(\w+(?:\s+\w+)*)\s+(?:is|has|requested|using).*microphone', re.IGNORECASE),
        'safari_pattern': re.compile(r'Safari.*microphone|microphone.*Safari', re.IGNORECASE),
    }
    
    # App name mapping
    app_names = {
        'com.apple.Safari': 'Safari',
        'com.google.Chrome': 'Google Chrome',
        'org.mozilla.firefox': 'Firefox',
        'us.zoom.xos': 'Zoom',
        'com.tinyspeck.slackmacgap': 'Slack',
        'com.microsoft.teams': 'Microsoft Teams',
        'com.skype.skype': 'Skype',
    }
    
    for line in process.stdout:
        if not running:
            break
        
        # Skip system noise
        if 'com.apple.WebKit' in line and 'GPU' in line:
            continue
            
        # Check for microphone access
        if 'microphone' in line.lower() or 'audio input' in line.lower():
            app_name = None
            
            # Try different patterns to extract app name
            for pattern_name, pattern in patterns.items():
                match = pattern.search(line)
                if match:
                    extracted = match.group(1)
                    # Map bundle ID to friendly name
                    app_name = app_names.get(extracted, extracted)
                    break
            
            # Special handling for Safari
            if not app_name and 'Safari' in line:
                app_name = 'Safari'
            
            if app_name and app_name not in ['tccd', 'kernel', 'system']:
                timestamp = datetime.now().strftime('%H:%M:%S')
                
                # Check if this is a new access
                if app_name not in active_apps:
                    print(f"{Colors.GREEN}[{timestamp}] ▶ {Colors.BOLD}{app_name}{Colors.RESET} "
                          f"{Colors.GREEN}started using microphone{Colors.RESET}")
                    active_apps[app_name] = time.time()

def check_inactive_apps():
    """Periodically check for apps that stopped using microphone"""
    global active_apps
    while running:
        time.sleep(5)  # Check every 5 seconds
        current_time = time.time()
        apps_to_remove = []
        
        for app, last_seen in list(active_apps.items()):
            # If we haven't seen activity for 10 seconds, assume stopped
            if current_time - last_seen > 10:
                timestamp = datetime.now().strftime('%H:%M:%S')
                print(f"{Colors.RED}[{timestamp}] ■ {Colors.BOLD}{app}{Colors.RESET} "
                      f"{Colors.RED}stopped using microphone{Colors.RESET}")
                apps_to_remove.append(app)
        
        for app in apps_to_remove:
            del active_apps[app]

def main():
    # Check if running on macOS
    if sys.platform != 'darwin':
        print(f"{Colors.RED}This script only works on macOS!{Colors.RESET}")
        sys.exit(1)
    
    # Setup signal handler
    signal.signal(signal.SIGINT, signal_handler)
    
    # Start inactive checker thread
    checker_thread = threading.Thread(target=check_inactive_apps, daemon=True)
    checker_thread.start()
    
    # Monitor logs
    try:
        monitor_microphone_logs()
    except KeyboardInterrupt:
        signal_handler(None, None)
    except Exception as e:
        print(f"{Colors.RED}Error: {e}{Colors.RESET}")
        print(f"{Colors.YELLOW}Try running with: sudo python3 mic_monitor.py{Colors.RESET}")

if __name__ == "__main__":
    main()
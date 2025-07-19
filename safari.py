#!/usr/bin/env python3
"""
Simple Microphone Monitor - Logs apps accessing microphone on macOS
Follows OverSight's approach: monitors audio device state + system logs
"""

import subprocess
import time
import re
import os
import signal
import sys
from datetime import datetime
from threading import Thread
import queue

# Color codes for terminal output
class Colors:
    RED = '\033[91m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    RESET = '\033[0m'
    BOLD = '\033[1m'

# Global queue for log messages
log_queue = queue.Queue()
running = True

def get_process_info(pid):
    """Get process name and path from PID"""
    try:
        # Get process name
        name_result = subprocess.run(['ps', '-p', str(pid), '-o', 'comm='], 
                                   capture_output=True, text=True)
        name = name_result.stdout.strip()
        
        # Get full path
        path_result = subprocess.run(['ps', '-p', str(pid), '-o', 'command='], 
                                   capture_output=True, text=True)
        full_path = path_result.stdout.strip()
        
        return name, full_path
    except:
        return f"Unknown (PID: {pid})", ""

def get_user_friendly_name(name, path):
    """Get user-friendly app name"""
    name_lower = name.lower()
    path_lower = path.lower()
    
    # WebKit processes are Safari
    if 'webkit' in name_lower:
        return 'Safari'
    
    # Chrome and Chrome Helper
    if 'google chrome' in name_lower or 'chrome' in path_lower:
        return 'Google Chrome'
    
    # Other common apps
    app_map = {
        'firefox': 'Firefox',
        'zoom.us': 'Zoom',
        'slack': 'Slack',
        'discord': 'Discord',
        'skype': 'Skype',
        'teams': 'Microsoft Teams',
        'facetime': 'FaceTime',
        'whatsapp': 'WhatsApp',
        'telegram': 'Telegram',
        'obs': 'OBS Studio',
        'screenflow': 'ScreenFlow'
    }
    
    for key, friendly_name in app_map.items():
        if key in name_lower or key in path_lower:
            return friendly_name
    
    # Filter out system daemons
    if name.endswith('d') and '/usr' in path:
        return None
    
    return name

def monitor_system_logs():
    """Monitor system logs for microphone access"""
    # Monitor CoreMedia logs
    log_cmd = ['log', 'stream', '--predicate', 
               'subsystem == "com.apple.coremedia" OR subsystem == "com.apple.cmio"']
    
    process = subprocess.Popen(log_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, 
                              text=True, bufsize=1)
    
    pid_pattern = re.compile(r'PID\s*=\s*(\d+)')
    seen_pids = set()
    
    for line in process.stdout:
        if not running:
            break
            
        # Look for PID patterns in logs
        match = pid_pattern.search(line)
        if match and ('microphone' in line.lower() or 'audio' in line.lower()):
            pid = int(match.group(1))
            
            # Avoid duplicate logs
            if pid in seen_pids:
                continue
            seen_pids.add(pid)
            
            name, path = get_process_info(pid)
            app_name = get_user_friendly_name(name, path)
            
            if app_name:  # Only show if we have a valid app name
                timestamp = datetime.now().strftime('%H:%M:%S')
                log_queue.put({
                    'timestamp': timestamp,
                    'pid': pid,
                    'app': app_name,
                    'type': 'access'
                })

def monitor_audio_devices():
    """Monitor audio device state changes"""
    last_active_pids = set()
    
    while running:
        try:
            # Get list of processes using audio
            result = subprocess.run(['lsof', '-n', '/dev/audio*'], 
                                  capture_output=True, text=True)
            
            current_pids = set()
            for line in result.stdout.splitlines()[1:]:  # Skip header
                parts = line.split()
                if len(parts) > 1:
                    pid = int(parts[1])
                    name, path = get_process_info(pid)
                    app_name = get_user_friendly_name(name, path)
                    
                    if app_name:  # Only track if we have a valid app name
                        current_pids.add(pid)
            
            # Check for new processes
            new_pids = current_pids - last_active_pids
            for pid in new_pids:
                name, path = get_process_info(pid)
                app_name = get_user_friendly_name(name, path)
                if app_name:
                    timestamp = datetime.now().strftime('%H:%M:%S')
                    log_queue.put({
                        'timestamp': timestamp,
                        'pid': pid,
                        'app': app_name,
                        'type': 'started'
                    })
            
            # Check for stopped processes
            stopped_pids = last_active_pids - current_pids
            for pid in stopped_pids:
                name, path = get_process_info(pid)
                app_name = get_user_friendly_name(name, path)
                if app_name:
                    timestamp = datetime.now().strftime('%H:%M:%S')
                    log_queue.put({
                        'timestamp': timestamp,
                        'pid': pid,
                        'app': app_name,
                        'type': 'stopped'
                    })
            
            last_active_pids = current_pids
            
        except Exception as e:
            pass
        
        time.sleep(1)  # Poll every second

def display_logs():
    """Display colored log messages"""
    print(f"\n{Colors.BOLD}🎙️  Microphone Monitor Started{Colors.RESET}")
    print(f"{Colors.BLUE}Monitoring microphone access...{Colors.RESET}\n")
    
    seen_events = set()  # Prevent duplicate messages
    
    while running:
        try:
            log = log_queue.get(timeout=0.5)
            
            # Create unique key for event
            event_key = f"{log['app']}-{log['type']}"
            
            # Skip if we just showed this event (within 2 seconds)
            current_time = time.time()
            if event_key in seen_events:
                continue
            
            seen_events.add(event_key)
            # Clear old events after 2 seconds
            Thread(target=lambda: (time.sleep(2), seen_events.discard(event_key)), daemon=True).start()
            
            if log['type'] == 'started' or log['type'] == 'access':
                print(f"{Colors.GREEN}[{log['timestamp']}] ▶ {Colors.BOLD}{log['app']}{Colors.RESET} "
                      f"{Colors.GREEN}started using microphone (PID: {log['pid']}){Colors.RESET}")
            elif log['type'] == 'stopped':
                print(f"{Colors.RED}[{log['timestamp']}] ■ {Colors.BOLD}{log['app']}{Colors.RESET} "
                      f"{Colors.RED}stopped using microphone (PID: {log['pid']}){Colors.RESET}")
                      
        except queue.Empty:
            continue

def signal_handler(signum, frame):
    """Handle Ctrl+C gracefully"""
    global running
    running = False
    print(f"\n{Colors.YELLOW}Stopping monitor...{Colors.RESET}")
    sys.exit(0)

def main():
    # Check if running on macOS
    if sys.platform != 'darwin':
        print(f"{Colors.RED}This script only works on macOS!{Colors.RESET}")
        sys.exit(1)
    
    # Setup signal handler
    signal.signal(signal.SIGINT, signal_handler)
    
    # Start monitoring threads
    log_thread = Thread(target=monitor_system_logs, daemon=True)
    device_thread = Thread(target=monitor_audio_devices, daemon=True)
    
    log_thread.start()
    device_thread.start()
    
    # Display logs in main thread
    try:
        display_logs()
    except KeyboardInterrupt:
        signal_handler(None, None)

if __name__ == "__main__":
    main()
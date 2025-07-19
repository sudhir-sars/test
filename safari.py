#!/usr/bin/env python3
"""
Simple Microphone Monitor - Logs apps accessing microphone on macOS
Monitors microphone access and identifies parent applications
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
active_apps = {}  # Track active apps

def get_parent_app(pid):
    """Find the parent application for a process"""
    try:
        # Get parent process ID
        ppid_result = subprocess.run(['ps', '-p', str(pid), '-o', 'ppid='], 
                                   capture_output=True, text=True)
        ppid = ppid_result.stdout.strip()
        
        if ppid:
            # Get parent process info
            parent_result = subprocess.run(['ps', '-p', ppid, '-o', 'comm='], 
                                         capture_output=True, text=True)
            parent_name = parent_result.stdout.strip()
            
            # Check if parent is a known browser
            if 'Safari' in parent_name:
                return 'Safari', ppid
            elif 'Google Chrome' in parent_name:
                return 'Google Chrome', ppid
            elif 'firefox' in parent_name.lower():
                return 'Firefox', ppid
    except:
        pass
    
    return None, None

def get_app_name_for_process(pid, process_name):
    """Determine the actual app name for a process"""
    # Direct app detection
    app_mapping = {
        'zoom.us': 'Zoom',
        'Slack': 'Slack',
        'Discord': 'Discord',
        'Skype': 'Skype',
        'teams': 'Microsoft Teams',
        'facetime': 'FaceTime',
        'whatsapp': 'WhatsApp',
        'telegram': 'Telegram',
        'signal': 'Signal'
    }
    
    process_lower = process_name.lower()
    
    # Check direct mappings
    for key, app in app_mapping.items():
        if key in process_lower:
            return app
    
    # Check if it's a WebKit process
    if 'webkit' in process_lower:
        parent_app, parent_pid = get_parent_app(pid)
        if parent_app:
            return parent_app
        # If no parent found, it's likely Safari (WebKit is Safari's engine)
        return 'Safari'
    
    # Check if it's Chrome
    if 'chrome' in process_lower:
        return 'Google Chrome'
    
    # Default to process name
    return process_name

def monitor_microphone_access():
    """Main monitoring function using log stream"""
    print(f"\n{Colors.BOLD}🎙️  Microphone Monitor Started{Colors.RESET}")
    print(f"{Colors.BLUE}Monitoring microphone access...{Colors.RESET}\n")
    
    # Monitor TCCd (Transparency, Consent, and Control daemon) logs for mic access
    log_cmd = ['log', 'stream', '--predicate', 
               '(subsystem == "com.apple.TCC" OR subsystem == "com.apple.coremedia") AND ' +
               '(eventMessage CONTAINS "microphone" OR eventMessage CONTAINS "audio input")']
    
    try:
        process = subprocess.Popen(log_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, 
                                  text=True, bufsize=1)
        
        # Also monitor audio device usage
        Thread(target=monitor_audio_activity, daemon=True).start()
        
        for line in process.stdout:
            if not running:
                break
                
            # Process log entries for microphone access
            if 'granted' in line.lower() or 'accessing' in line.lower():
                # Extract PID if available
                pid_match = re.search(r'pid[:\s]+(\d+)', line, re.IGNORECASE)
                if pid_match:
                    pid = int(pid_match.group(1))
                    
                    # Get process info
                    result = subprocess.run(['ps', '-p', str(pid), '-o', 'comm='], 
                                          capture_output=True, text=True)
                    process_name = result.stdout.strip()
                    
                    if process_name:
                        app_name = get_app_name_for_process(pid, process_name)
                        timestamp = datetime.now().strftime('%H:%M:%S')
                        
                        print(f"{Colors.GREEN}[{timestamp}] ▶ {Colors.BOLD}{app_name}{Colors.RESET} "
                              f"{Colors.GREEN}accessing microphone (PID: {pid}){Colors.RESET}")
                        
                        active_apps[pid] = app_name
                        
    except KeyboardInterrupt:
        pass
    except Exception as e:
        print(f"{Colors.RED}Error in log monitoring: {e}{Colors.RESET}")

def monitor_audio_activity():
    """Monitor audio input activity"""
    last_check = set()
    
    while running:
        try:
            # Check for audio input activity
            result = subprocess.run(['pmset', '-g', 'assertions'], 
                                  capture_output=True, text=True)
            
            # Also check CoreAudio for active input
            audio_result = subprocess.run(['system_profiler', 'SPAudioDataType'], 
                                        capture_output=True, text=True)
            
            # Look for processes using audio
            lsof_result = subprocess.run(['lsof', '+D', '/dev'], 
                                       capture_output=True, text=True)
            
            current_pids = set()
            
            for line in lsof_result.stdout.splitlines():
                if 'audio' in line.lower():
                    parts = line.split()
                    if len(parts) > 1:
                        try:
                            pid = int(parts[1])
                            current_pids.add(pid)
                        except:
                            pass
            
            # Check for new processes
            new_pids = current_pids - last_check
            for pid in new_pids:
                if pid not in active_apps:
                    try:
                        result = subprocess.run(['ps', '-p', str(pid), '-o', 'comm='], 
                                              capture_output=True, text=True)
                        process_name = result.stdout.strip()
                        
                        if process_name:
                            app_name = get_app_name_for_process(pid, process_name)
                            timestamp = datetime.now().strftime('%H:%M:%S')
                            
                            print(f"{Colors.GREEN}[{timestamp}] ▶ {Colors.BOLD}{app_name}{Colors.RESET} "
                                  f"{Colors.GREEN}started using microphone (PID: {pid}){Colors.RESET}")
                            
                            active_apps[pid] = app_name
                    except:
                        pass
            
            # Check for stopped processes
            stopped_pids = last_check - current_pids
            for pid in stopped_pids:
                if pid in active_apps:
                    app_name = active_apps[pid]
                    timestamp = datetime.now().strftime('%H:%M:%S')
                    
                    print(f"{Colors.RED}[{timestamp}] ■ {Colors.BOLD}{app_name}{Colors.RESET} "
                          f"{Colors.RED}stopped using microphone (PID: {pid}){Colors.RESET}")
                    
                    del active_apps[pid]
            
            last_check = current_pids
            
        except Exception:
            pass
        
        time.sleep(2)

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
    
    try:
        monitor_microphone_access()
    except KeyboardInterrupt:
        signal_handler(None, None)

if __name__ == "__main__":
    main()
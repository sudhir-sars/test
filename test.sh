#!/bin/bash

# Simple window monitor script using Swift

# Create inline Swift script
cat << 'EOF' > /tmp/window_monitor.swift
import Cocoa

let options = CGWindowListOption(arrayLiteral: .excludeDesktopElements, .optionOnScreenOnly)
let windowList = CGWindowListCopyWindowInfo(options, kCGNullWindowID)!
let windows = windowList as NSArray as! [[String: Any]]

print("\n--- \(Date()) ---")
for window in windows {
    let app = window[kCGWindowOwnerName as String] as? String ?? "?"
    let title = window[kCGWindowName as String] as? String ?? "<no title>"
    let pid = window[kCGWindowOwnerPID as String] as? Int32 ?? 0
    
    print("\(app): \(title) [PID:\(pid)]")
}
EOF

# Run continuously
while true; do
    swift /tmp/window_monitor.swift
    sleep 2
done
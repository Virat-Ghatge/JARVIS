#!/usr/bin/env python3
"""
System Information Module
Handles battery, CPU, RAM, temperature, IP, disk, and internet speed queries.
"""

import socket
import psutil
import threading
import speedtest

class SystemInfoHandler:
    """Handles system hardware and network operations"""

    def __init__(self, jarvis):
        self.jarvis = jarvis

    def get_quick_stats(self):
        """Returns quick hardware stats for background monitoring"""
        stats = {
            'cpu': psutil.cpu_percent(interval=0.1),
            'ram': psutil.virtual_memory().percent,
            'battery': None,
            'plugged_in': None,
            'temp': None
        }

        # Battery
        if hasattr(psutil, 'sensors_battery'):
            battery = psutil.sensors_battery()
            if battery:
                stats['battery'] = battery.percent
                stats['plugged_in'] = battery.power_plugged

        # Temperature (often unsupported on Windows natively)
        if hasattr(psutil, 'sensors_temperatures'):
            try:
                temps = psutil.sensors_temperatures()
                if temps and 'coretemp' in temps:
                    # Average the core temperatures
                    core_temps = [entry.current for entry in temps['coretemp']]
                    if core_temps:
                        stats['temp'] = sum(core_temps) / len(core_temps)
            except Exception:
                pass

        return stats

    def get_full_report(self):
        """Gathers all system info and speaks it"""
        self.jarvis.speak("Running full system diagnostics, sir. This will take a moment to test the network.")
        
        # Gather hardware stats
        stats = self.get_quick_stats()
        
        # Disk space
        disk = psutil.disk_usage('/')
        disk_free_gb = disk.free / (1024 ** 3)
        disk_total_gb = disk.total / (1024 ** 3)
        disk_percent = disk.percent
        
        # IP Address
        try:
            ip_address = socket.gethostbyname(socket.gethostname())
        except Exception:
            ip_address = "Unknown"

        # Speedtest
        download_mbps = 0
        upload_mbps = 0
        try:
            st = speedtest.Speedtest()
            st.get_best_server()
            download_mbps = st.download() / 1_000_000
            upload_mbps = st.upload() / 1_000_000
        except Exception as e:
            print(f"[Speedtest Error] {e}")

        # Construct report
        report = []
        report.append(f"CPU usage is at {stats['cpu']} percent.")
        report.append(f"Memory usage is at {stats['ram']} percent.")
        
        if stats['temp']:
            report.append(f"CPU temperature is {stats['temp']:.1f} degrees Celsius.")
        
        if stats['battery'] is not None:
            plug_status = "plugged in" if stats['plugged_in'] else "on battery power"
            report.append(f"Battery is at {stats['battery']} percent and {plug_status}.")
        
        report.append(f"Main disk is {disk_percent} percent full, with {disk_free_gb:.1f} gigabytes free.")
        report.append(f"Local IP address is {ip_address}.")
        
        if download_mbps > 0:
            report.append(f"Internet connection is active. Download speed: {download_mbps:.1f} megabits per second. Upload speed: {upload_mbps:.1f} megabits per second.")
        else:
            report.append("I was unable to perform a network speed test at this time.")

        full_text = " ".join(report)
        self.jarvis.speak(full_text)

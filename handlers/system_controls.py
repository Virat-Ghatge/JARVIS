#!/usr/bin/env python3
"""
System Controls Module
Handles volume, brightness, timer, and stopwatch
"""

import os
import platform
import threading
import time
from datetime import datetime, timedelta

# Windows-specific imports
if platform.system() == "Windows":
    try:
        import ctypes
        from ctypes import wintypes
        WINDOWS_AVAILABLE = True
    except ImportError:
        WINDOWS_AVAILABLE = False

    try:
        from comtypes import CLSCTX_ALL
        from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
        PYCAW_AVAILABLE = True
    except ImportError:
        PYCAW_AVAILABLE = False

    try:
        import wmi
        WMI_AVAILABLE = True
    except ImportError:
        WMI_AVAILABLE = False
else:
    WINDOWS_AVAILABLE = False
    PYCAW_AVAILABLE = False
    WMI_AVAILABLE = False


class SystemControls:
    """System control handlers"""

    def __init__(self, jarvis):
        self.jarvis = jarvis
        self.timers = []  # Active timers
        self.stopwatch_start = None
        self.stopwatch_running = False
        self._muted = False  # Track mute state for deterministic mute/unmute

    # ==================== VOLUME CONTROL ====================

    def set_volume(self, level):
        """
        Set system volume (0-100)
        level: int or string with number
        """
        try:
            # Extract number from string if needed
            if isinstance(level, str):
                import re
                numbers = re.findall(r'\d+', level)
                if numbers:
                    level = int(numbers[0])
                else:
                    self.jarvis.speak("Please specify a volume level, sir.")
                    return

            # Clamp to 0-100
            level = max(0, min(100, level))

            if platform.system() == "Windows":
                self._set_volume_windows(level)
            else:
                self._set_volume_generic(level)

            self.jarvis.speak(f"Volume set to {level} percent, sir.")

        except Exception as e:
            print(f"Volume control error: {e}")
            self.jarvis.speak("I'm unable to adjust the volume, sir.")

    def _set_volume_windows(self, level):
        """Set volume on Windows using pycaw"""
        if not PYCAW_AVAILABLE:
            # Fallback: use key presses
            self._adjust_volume_by_keys(level)
            return

        try:
            devices = AudioUtilities.GetSpeakers()
            interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
            volume = interface.QueryInterface(IAudioEndpointVolume)
            volume.SetMasterVolumeLevelScalar(level / 100, None)
        except Exception as e:
            self._adjust_volume_by_keys(level)

    def _adjust_volume_by_keys(self, target_level):
        """Fallback: Adjust volume using media keys toward target_level (0-100)."""
        if not WINDOWS_AVAILABLE:
            return

        VK_VOLUME_UP = 0xAF
        VK_VOLUME_DOWN = 0xAE

        user32 = ctypes.windll.user32

        # Each key press moves volume by ~2 units on most Windows systems.
        # Start by pressing Volume Down 50 times to get close to 0,
        # then press Volume Up (target_level // 2) times to reach the target.
        # This is an approximation but far better than the old stub.
        STEP = 2  # approximate volume change per key press

        # Drive to 0 first
        for _ in range(50):
            user32.keybd_event(VK_VOLUME_DOWN, 0, 0, 0)
            user32.keybd_event(VK_VOLUME_DOWN, 0, 2, 0)

        # Drive up to target
        steps_up = target_level // STEP
        for _ in range(steps_up):
            user32.keybd_event(VK_VOLUME_UP, 0, 0, 0)
            user32.keybd_event(VK_VOLUME_UP, 0, 2, 0)

    def mute(self):
        """Mute audio (idempotent — only acts if not already muted)"""
        try:
            if platform.system() == "Windows" and WINDOWS_AVAILABLE:
                if not self._muted:
                    VK_VOLUME_MUTE = 0xAD
                    user32 = ctypes.windll.user32
                    user32.keybd_event(VK_VOLUME_MUTE, 0, 0, 0)
                    user32.keybd_event(VK_VOLUME_MUTE, 0, 2, 0)
                    self._muted = True
                self.jarvis.speak("Audio muted, sir.")
            else:
                self.jarvis.speak("Mute control not available, sir.")
        except Exception:
            self.jarvis.speak("Unable to mute audio, sir.")

    def unmute(self):
        """Unmute audio (idempotent — only acts if currently muted)"""
        try:
            if platform.system() == "Windows" and WINDOWS_AVAILABLE:
                if self._muted:
                    VK_VOLUME_MUTE = 0xAD
                    user32 = ctypes.windll.user32
                    user32.keybd_event(VK_VOLUME_MUTE, 0, 0, 0)
                    user32.keybd_event(VK_VOLUME_MUTE, 0, 2, 0)
                    self._muted = False
                self.jarvis.speak("Audio unmuted, sir.")
            else:
                self.jarvis.speak("Unmute control not available, sir.")
        except Exception:
            self.jarvis.speak("Unable to unmute audio, sir.")

    # ==================== BRIGHTNESS CONTROL ====================

    def set_brightness(self, level):
        """
        Set screen brightness (0-100)
        """
        try:
            # Extract number from string if needed
            if isinstance(level, str):
                import re
                numbers = re.findall(r'\d+', level)
                if numbers:
                    level = int(numbers[0])
                else:
                    self.jarvis.speak("Please specify a brightness level, sir.")
                    return

            # Clamp to 0-100
            level = max(0, min(100, level))

            if platform.system() == "Windows":
                self._set_brightness_windows(level)
            else:
                self._set_brightness_generic(level)

            self.jarvis.speak(f"Brightness set to {level} percent, sir.")

        except Exception as e:
            print(f"Brightness control error: {e}")
            self.jarvis.speak("I'm unable to adjust the brightness, sir.")

    def _set_brightness_windows(self, level):
        """Set brightness on Windows"""
        if WMI_AVAILABLE:
            try:
                c = wmi.WMI(namespace='wmi')
                methods = c.WmiMonitorBrightnessMethods()[0]
                methods.WmiSetBrightness(level, 0)
            except Exception as e:
                # Fallback: try screen-brightness-control library
                try:
                    import screen_brightness_control as sbc
                    sbc.set_brightness(level)
                except:
                    pass
        else:
            try:
                import screen_brightness_control as sbc
                sbc.set_brightness(level)
            except:
                pass

    def _set_brightness_generic(self, level):
        """Generic brightness setting for other platforms"""
        try:
            if platform.system() == "Linux":
                # Linux: use xrandr or brightnessctl
                os.system(f"brightnessctl set {level}%")
            elif platform.system() == "Darwin":  # macOS
                # macOS: use brightness command
                os.system(f"brightness -v {level / 100}")
        except:
            pass

    def increase_brightness(self, amount=10):
        """Increase brightness by amount"""
        try:
            if platform.system() == "Windows" and WMI_AVAILABLE:
                c = wmi.WMI(namespace='wmi')
                brightness = c.WmiMonitorBrightness()[0].CurrentBrightness
                new_brightness = min(100, brightness + amount)
                self.set_brightness(new_brightness)
            else:
                self.jarvis.speak("Brightness adjustment not available, sir.")
        except:
            self.jarvis.speak("Unable to adjust brightness, sir.")

    def decrease_brightness(self, amount=10):
        """Decrease brightness by amount"""
        try:
            if platform.system() == "Windows" and WMI_AVAILABLE:
                c = wmi.WMI(namespace='wmi')
                brightness = c.WmiMonitorBrightness()[0].CurrentBrightness
                new_brightness = max(0, brightness - amount)
                self.set_brightness(new_brightness)
            else:
                self.jarvis.speak("Brightness adjustment not available, sir.")
        except:
            self.jarvis.speak("Unable to adjust brightness, sir.")

    # ==================== TIMER ====================

    def set_timer(self, duration_str):
        """
        Set a timer for specified duration
        Examples: "5 minutes", "30 seconds", "1 hour"
        """
        try:
            import re

            # Parse duration
            total_seconds = 0

            # Look for hours, minutes, seconds
            hours = re.search(r'(\d+)\s*hour', duration_str)
            minutes = re.search(r'(\d+)\s*minute|(\d+)\s*min', duration_str)
            seconds = re.search(r'(\d+)\s*second|(\d+)\s*sec', duration_str)

            if hours:
                total_seconds += int(hours.group(1)) * 3600
            if minutes:
                total_seconds += int(minutes.group(1) or minutes.group(2)) * 60
            if seconds:
                total_seconds += int(seconds.group(1) or seconds.group(2))

            # Direct number (assume minutes)
            if total_seconds == 0:
                numbers = re.findall(r'\d+', duration_str)
                if numbers:
                    total_seconds = int(numbers[0]) * 60

            if total_seconds <= 0:
                self.jarvis.speak("Please specify a valid duration, sir.")
                return

            # Format duration for speech
            duration_text = self._format_duration(total_seconds)

            # Create timer
            timer_id = len(self.timers)
            timer_thread = threading.Thread(
                target=self._timer_worker,
                args=(timer_id, total_seconds),
                daemon=True
            )

            self.timers.append({
                'id': timer_id,
                'duration': total_seconds,
                'remaining': total_seconds,
                'thread': timer_thread,
                'start_time': time.time()
            })

            timer_thread.start()

            self.jarvis.speak(f"Timer set for {duration_text}, sir.")

        except Exception as e:
            print(f"Timer error: {e}")
            self.jarvis.speak("I couldn't set the timer, sir.")

    def _timer_worker(self, timer_id, duration):
        """Background thread for timer"""
        elapsed = 0
        while elapsed < duration:
            # Check if timer was cancelled (removed from list)
            if not any(t['id'] == timer_id for t in self.timers):
                return
            time.sleep(1)
            elapsed += 1

        # Timer finished - beep and announce
        self._beep_timer()

        if self.jarvis:
            self.jarvis.speak("Sir, your timer is up!")

        # Remove from active timers
        self.timers = [t for t in self.timers if t['id'] != timer_id]

    def _beep_timer(self):
        """Beep for timer alarm"""
        if platform.system() == "Windows":
            try:
                import winsound
                # Beep pattern: 3 beeps
                for _ in range(3):
                    winsound.Beep(1000, 500)  # 1000Hz for 500ms
                    time.sleep(0.2)
            except:
                pass

    def _format_duration(self, seconds):
        """Format seconds into readable duration"""
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        secs = seconds % 60

        parts = []
        if hours > 0:
            parts.append(f"{hours} hour{'s' if hours > 1 else ''}")
        if minutes > 0:
            parts.append(f"{minutes} minute{'s' if minutes > 1 else ''}")
        if secs > 0 and hours == 0:  # Only show seconds if no hours
            parts.append(f"{secs} second{'s' if secs > 1 else ''}")

        return " ".join(parts) if parts else "0 seconds"

    def cancel_timer(self):
        """Cancel all active timers with confirmation"""
        if not self.timers:
            self.jarvis.speak("No active timers to cancel, sir.")
            return

        # List active timers
        if len(self.timers) == 1:
            duration = self._format_duration(self.timers[0]['duration'])
            self.jarvis.speak(f"You have one active timer for {duration}. Are you sure you want to cancel it?")
        else:
            self.jarvis.speak(f"You have {len(self.timers)} active timers. Are you sure you want to cancel all of them?")

        # Ask for confirmation
        response = self.jarvis.listen()
        
        if response and any(word in response.lower() for word in ['yes', 'yeah', 'yep', 'sure', 'cancel']):
            self.timers.clear()
            self.jarvis.speak("All timers have been cancelled, sir.")
        else:
            self.jarvis.speak("Timers will remain active, sir.")

    # ==================== STOPWATCH ====================

    def start_stopwatch(self):
        """Start the stopwatch"""
        if not self.stopwatch_running:
            self.stopwatch_start = time.time()
            self.stopwatch_running = True
            self.jarvis.speak("Stopwatch started, sir.")
        else:
            self.jarvis.speak("Stopwatch is already running, sir.")

    def stop_stopwatch(self):
        """Stop the stopwatch and report elapsed time"""
        if self.stopwatch_running:
            elapsed = time.time() - self.stopwatch_start
            self.stopwatch_running = False

            time_str = self._format_duration(int(elapsed))
            self.jarvis.speak(f"Stopwatch stopped at {time_str}, sir.")
        else:
            self.jarvis.speak("Stopwatch is not running, sir.")

    def lap_stopwatch(self):
        """Record a lap time"""
        if self.stopwatch_running:
            elapsed = time.time() - self.stopwatch_start
            time_str = self._format_duration(int(elapsed))
            self.jarvis.speak(f"Lap time: {time_str}, sir.")
        else:
            self.jarvis.speak("Stopwatch is not running, sir.")

    def reset_stopwatch(self):
        """Reset the stopwatch"""
        self.stopwatch_running = False
        self.stopwatch_start = None
        self.jarvis.speak("Stopwatch reset, sir.")


if __name__ == "__main__":
    # Test module
    class MockJARVIS:
        def speak(self, text):
            print(f"JARVIS: {text}")

    jarvis = MockJARVIS()
    controls = SystemControls(jarvis)

    print("Testing system controls...")
    print("Available commands: volume, brightness, timer, stopwatch")

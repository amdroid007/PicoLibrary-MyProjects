"""
# FeedbackController.py
# State-machine controller for the store customer feedback station.
# Integrates buttons, ultrasonic sensor, buzzer, LCD display, light strip,
# and FeedbackStats to track satisfaction and alert management if needed.
# Author: Jit Sengupta
"""

import sys
import time

# Safely handle non-MicroPython / test environments
try:
    import machine
except ImportError:
    import types
    m = types.ModuleType('machine')
    m.Pin = type('Pin', (), {
        'IN': 0, 'OUT': 1, 'PULL_UP': 1, 'PULL_DOWN': 2,
        'IRQ_FALLING': 1, 'IRQ_RISING': 2,
        '__init__': lambda self, *a, **k: None,
        'value': lambda self, *a: 0,
        'irq': lambda self, *a, **k: None
    })
    m.ADC = type('ADC', (), {'__init__': lambda self, *a, **k: None, 'read_u16': lambda self: 0})
    m.PWM = type('PWM', (), {'__init__': lambda self, *a, **k: None, 'freq': lambda self, *a: None, 'duty_u16': lambda self, *a: None})
    m.Timer = type('Timer', (), {})
    m.RTC = type('RTC', (), {})
    m.I2C = type('I2C', (), {
        '__init__': lambda self, *a, **k: None,
        'scan': lambda self: [0x27],
        'writeto': lambda self, *a, **k: None,
        'readfrom': lambda self, *a, **k: b'\x00'
    })
    m.SPI = type('SPI', (), {'__init__': lambda self, *a, **k: None})
    sys.modules['machine'] = m

try:
    import utime
except ImportError:
    u = time
    u.ticks_ms = lambda: int(time.time() * 1000)
    u.ticks_us = lambda: int(time.time() * 1000000)
    u.ticks_diff = lambda a, b: a - b
    u.sleep_us = lambda us: time.sleep(us / 1000000)
    u.sleep_ms = lambda ms: time.sleep(ms / 1000)
    sys.modules['utime'] = u

if not hasattr(time, 'ticks_ms'):
    time.ticks_ms = lambda: int(time.time() * 1000)
if not hasattr(time, 'ticks_diff'):
    time.ticks_diff = lambda a, b: a - b

try:
    import neopixel
except ImportError:
    import types
    n = types.ModuleType('neopixel')
    n.NeoPixel = type('NeoPixel', (), {
        '__init__': lambda self, p, count: None,
        '__setitem__': lambda self, i, v: None,
        'write': lambda self: None
    })
    sys.modules['neopixel'] = n

try:
    import micropython
except ImportError:
    sys.modules['micropython'] = types.ModuleType('micropython')

try:
    import dht
except ImportError:
    sys.modules['dht'] = types.ModuleType('dht')

from Log import *
from StateModel import StateModel
from Counters import SoftwareTimer
from Button import Button
from Lights import GREEN, RED, WHITE, YELLOW, BLACK
from LightStrip import LightStrip
from Buzzer import PassiveBuzzer
from Displays import LCDDisplay
from Sensors_advanced import UltrasonicSensor
from FeedbackStats import FeedbackStats


class FeedbackController:
    """
    **FeedbackController** coordinates the customer feedback station.
    It manages the state transitions according to the state diagram:
    - **State 0 (Welcome)**: Displays 'Welcome to Ikea', awaits customer presence via UltrasonicSensor.
    - **State 1 (Selection)**: Displays 'How was your visit?' and starts a 5-second timer.
      Accepts feedback via green button (happy) or red button (unhappy).
    - **State 2 (happy)**: Increments happy count, displays 'Thank you', plays happy music,
      updates light strip satisfaction level, and starts 5-second timer to return to Welcome.
    - **State 3 (unhappy)**: Increments unhappy count, displays 'Sorry to hear that', plays sad tone,
      updates light strip satisfaction level, and starts 5-second timer. If satisfaction falls below
      the threshold percentage, it transitions to State 4 (Alarm).
    - **State 4 (Alarm)**: Displays 'Calling manager', plays a 2-tone alarm repeatedly, and waits for
      manager acknowledgement via green button press. On exit, resets feedback statistics.

    Parameters:
    ----------
    stats : FeedbackStats, optional
        Pre-configured FeedbackStats instance. If None, a new instance is created.
    display : LCDDisplay, optional
        Pre-configured LCDDisplay instance. If None, creates an I2C LCD on (sda, scl).
    buzzer : PassiveBuzzer, optional
        Pre-configured PassiveBuzzer instance. If None, creates buzzer on buzzer_pin.
    lightstrip : LightStrip, optional
        Pre-configured LightStrip instance. If None, creates LightStrip on lightstrip_pin.
    uss : UltrasonicSensor, optional
        Pre-configured UltrasonicSensor instance. If None, creates one on (trigger, echo).
    button_green : Button, optional
        Green button instance. If None, creates one on green_pin with name 'green'.
    button_red : Button, optional
        Red button instance. If None, creates one on red_pin with name 'red'.
    timer : SoftwareTimer, optional
        Timer instance. If None, creates a SoftwareTimer named 'timer'.
    threshold : float, optional
        Minimum acceptable satisfaction percentage before alarming (default: 50.0).
    min_feedback_for_alarm : int, optional
        Minimum number of feedback entries required before evaluating threshold (default: 1).
    debug : bool, optional
        Whether to enable debug logging in StateModel (default: True).

    Examples:
    ---------
    1. Instantiating with default hardware settings on Pico:
       ```python
       controller = FeedbackController()
       controller.run()
       ```
    2. Instantiating with customized threshold:
       ```python
       controller = FeedbackController(threshold=60.0)
       controller.run()
       ```
    """

    def __init__(self,
                 stats=None,
                 display=None,
                 buzzer=None,
                 lightstrip=None,
                 uss=None,
                 button_green=None,
                 button_red=None,
                 timer=None,
                 green_pin=18,
                 red_pin=19,
                 buzzer_pin=16,
                 lightstrip_pin=2,
                 num_leds=16,
                 sda=0, scl=1,
                 trigger=14, echo=15,
                 threshold=50.0,
                 min_feedback_for_alarm=1,
                 debug=True):

        self._threshold = threshold
        self._min_feedback_for_alarm = min_feedback_for_alarm
        self._num_leds = num_leds
        self._alarm_tone_state = 0

        # Model statistics
        self._stats = stats if stats is not None else FeedbackStats(max_levels=num_leds)

        # Hardware components
        self._lightstrip = lightstrip if lightstrip is not None else self._create_lightstrip(lightstrip_pin, num_leds)
        self._buzzer = buzzer if buzzer is not None else self._create_buzzer(buzzer_pin)
        self._display = display if display is not None else self._create_display(sda, scl)

        self._button1 = button_green if button_green is not None else Button(green_pin, "green", handler=None)
        self._button2 = button_red if button_red is not None else Button(red_pin, "red", handler=None)

        self._uss = uss if uss is not None else UltrasonicSensor(trigger=trigger, echo=echo, name="uss")
        self._timer = timer if timer is not None else SoftwareTimer(name="timer", handler=None)

        # State Model with 5 states (0 through 4)
        self._model = StateModel(5, self, debug=debug)

        # Register inputs
        self._model.addButton(self._button1)
        self._model.addButton(self._button2)
        self._model.addSensor(self._uss)
        self._model.addTimer(self._timer)

        # Register custom threshold event
        self._model.addCustomEvent("feedback_below_threshold")

        # Configure transitions per the state diagram
        # State 0 (Welcome): uss_trip -> State 1 (Selection)
        self._model.addTransition(0, ["uss_trip"], 1)

        # State 1 (Selection):
        # timer_timeout -> State 0
        # green_press   -> State 2 (happy)
        # red_press     -> State 3 (unhappy)
        self._model.addTransition(1, ["timer_timeout"], 0)
        self._model.addTransition(1, ["green_press"], 2)
        self._model.addTransition(1, ["red_press"], 3)

        # State 2 (happy):
        # timer_timeout -> State 0
        self._model.addTransition(2, ["timer_timeout"], 0)

        # State 3 (unhappy):
        # timer_timeout            -> State 0
        # feedback_below_threshold -> State 4 (Alarm)
        self._model.addTransition(3, ["timer_timeout"], 0)
        self._model.addTransition(3, ["feedback_below_threshold"], 4)

        # State 4 (Alarm):
        # green_press -> State 0
        self._model.addTransition(4, ["green_press"], 0)

        Log.i("FeedbackController initialized successfully")

    def _create_lightstrip(self, pin, numleds):
        try:
            return LightStrip(pin=pin, numleds=numleds)
        except Exception as e:
            Log.w(f"LightStrip init warning: {e}")
            return None

    def _create_buzzer(self, pin):
        try:
            return PassiveBuzzer(pin=pin, name="buzzer")
        except Exception as e:
            Log.w(f"PassiveBuzzer init warning: {e}")
            return None

    def _create_display(self, sda, scl):
        try:
            return LCDDisplay(sda=sda, scl=scl)
        except Exception as e:
            Log.w(f"LCDDisplay init warning: {e}")
            return None

    @property
    def stats(self):
        """ Returns the FeedbackStats instance. """
        return self._stats

    @property
    def model(self):
        """ Returns the underlying StateModel instance. """
        return self._model

    @property
    def display(self):
        """ Returns the LCDDisplay instance. """
        return self._display

    @property
    def buzzer(self):
        """ Returns the PassiveBuzzer instance. """
        return self._buzzer

    @property
    def lightstrip(self):
        """ Returns the LightStrip instance. """
        return self._lightstrip

    @property
    def green_button(self):
        """ Returns the green Button instance. """
        return self._button1

    @property
    def red_button(self):
        """ Returns the red Button instance. """
        return self._button2

    @property
    def uss(self):
        """ Returns the UltrasonicSensor instance. """
        return self._uss

    @property
    def timer(self):
        """ Returns the SoftwareTimer instance. """
        return self._timer

    def stateEntered(self, state, event):
        """
        Handler for performing entry actions when entering a new state.

        Parameters:
        ----------
        state : int
            The state number just entered (0 to 4).
        event : str
            The event that caused the transition.
        """
        Log.d(f"FeedbackController: State {state} entered on event {event}")

        if state == 0:
            # 0 - Welcome: entry / display 'Welcome to Ikea'
            if self._display:
                self._display.clear()
                self._display.showText("Welcome to Ikea", 0, 0)
            if self._buzzer:
                self._buzzer.stop()
            self._update_light_strip()

        elif state == 1:
            # 1 - Selection: entry / display 'How was your visit?'; start a 5 sec timer
            if self._display:
                self._display.clear()
                self._display.showText("How was your", 0, 0)
                self._display.showText("visit?", 1, 0)
            if self._timer:
                self._timer.start(5)

        elif state == 2:
            # 2 - happy: entry / display 'Thank you'; play happy music; start 5 sec timer
            self._stats.add_happy()
            if self._display:
                self._display.clear()
                self._display.showText("Thank you", 0, 0)
            self._play_happy_music()
            self._update_light_strip()
            if self._timer:
                self._timer.start(5)

        elif state == 3:
            # 3 - unhappy: entry / display 'Sorry to hear that'; play sad tone; start 5 sec timer
            self._stats.add_unhappy()
            if self._display:
                self._display.clear()
                self._display.showText("Sorry to hear", 0, 0)
                self._display.showText("that", 1, 0)
            self._play_sad_tone()
            self._update_light_strip()
            if self._timer:
                self._timer.start(5)

            # Check threshold for alarm transition
            total = self._stats.get_total_count()
            pct = self._stats.calculate_percentage()
            if total >= self._min_feedback_for_alarm and pct < self._threshold:
                Log.w(f"Satisfaction {pct}% is below threshold {self._threshold}%. Triggering feedback_below_threshold.")
                self._model.processEvent("feedback_below_threshold")

        elif state == 4:
            # 4 - Alarm: entry / display 'Calling manager'
            if self._timer:
                self._timer.cancel()
            if self._display:
                self._display.clear()
                self._display.showText("Calling manager", 0, 0)
            if self._lightstrip:
                self._lightstrip.setColor(RED)
            self._alarm_tone_state = 0

    def stateLeft(self, state, event):
        """
        Handler for performing exit actions when leaving a state.

        Parameters:
        ----------
        state : int
            The state number being exited.
        event : str
            The event causing the exit.
        """
        Log.d(f"FeedbackController: State {state} exited on event {event}")

        if state in (1, 2, 3):
            if self._timer:
                self._timer.cancel()

        if state == 4:
            # 4 - Alarm: exit / reset stats
            Log.i("Exiting Alarm state - resetting feedback statistics")
            self._stats.reset()
            if self._buzzer:
                self._buzzer.stop()
            if self._lightstrip:
                self._lightstrip.off()

    def stateEvent(self, state, event) -> bool:
        """
        Handler for internal in-state events that do not trigger transitions.
        """
        return False

    def stateDo(self, state):
        """
        Handler for continuous activities while residing in a state.

        Parameters:
        ----------
        state : int
            The active state number.
        """
        if state == 4:
            # 4 - Alarm: do / play a 2 tone alarm
            if self._buzzer:
                if self._alarm_tone_state == 0:
                    self._buzzer.play(880)
                    self._alarm_tone_state = 1
                else:
                    self._buzzer.play(587)
                    self._alarm_tone_state = 0

    def _update_light_strip(self):
        """ Updates the LightStrip display based on current feedback statistics. """
        if not self._lightstrip:
            return
        level = self._stats.get_light_level(self._num_leds)
        if level <= 0:
            self._lightstrip.off()
        else:
            self._lightstrip.setColor(GREEN, level)

    def _play_happy_music(self):
        """ Plays a cheerful rising tone sequence for happy feedback. """
        if not self._buzzer:
            return
        melody = [523, 659, 784, 1047]  # C5, E5, G5, C6
        for tone in melody:
            self._buzzer.play(tone)
            time.sleep(0.08)
        self._buzzer.stop()

    def _play_sad_tone(self):
        """ Plays a descending tone sequence for unhappy feedback. """
        if not self._buzzer:
            return
        melody = [392, 330, 262]  # G4, E4, C4
        for tone in melody:
            self._buzzer.play(tone)
            time.sleep(0.12)
        self._buzzer.stop()

    def run(self, delay=0.1):
        """
        Start and run the feedback controller state model.

        Parameters:
        ----------
        delay : float, optional
            Delay between event loop iterations (default: 0.1).
        """
        Log.i("Starting FeedbackController state model...")
        self._model.run(delay)

    def stop(self):
        """ Stops the controller and cleans up hardware. """
        Log.i("Stopping FeedbackController...")
        if self._timer:
            self._timer.cancel()
        if self._buzzer:
            self._buzzer.stop()
        if self._lightstrip:
            self._lightstrip.off()
        if self._display:
            self._display.clear()
        self._model.stop()


if __name__ == "__main__":
    Log.i("Starting FeedbackController self-test...")

    # Create dummy hardware / mock components for non-hardware verification
    class DummyDisplay:
        def __init__(self):
            self.lines = {}
        def clear(self, line=-1):
            self.lines = {}
        def showText(self, text, row=0, col=0):
            self.lines[row] = text
            Log.d(f"[Display Row {row}]: {text}")

    class DummyBuzzer:
        def __init__(self):
            self.current_tone = 0
            self.is_playing = False
        def play(self, tone=500):
            self.current_tone = tone
            self.is_playing = True
            Log.d(f"[Buzzer]: Playing {tone}Hz")
        def stop(self):
            self.is_playing = False
            Log.d("[Buzzer]: Stopped")

    class DummyLightStrip:
        def __init__(self, numleds=16):
            self.numleds = numleds
            self.color = (0, 0, 0)
            self.num_pixels = 0
        def setColor(self, color, numPixels=None):
            self.color = color
            self.num_pixels = numPixels if numPixels is not None else self.numleds
            Log.d(f"[LightStrip]: Set {self.num_pixels} pixels to {color}")
        def off(self):
            self.color = (0, 0, 0)
            self.num_pixels = 0
            Log.d("[LightStrip]: Off")

    disp = DummyDisplay()
    buz = DummyBuzzer()
    strip = DummyLightStrip()
    stats = FeedbackStats(max_levels=16)

    controller = FeedbackController(
        stats=stats,
        display=disp,
        buzzer=buz,
        lightstrip=strip,
        threshold=50.0,
        min_feedback_for_alarm=2,
        debug=True
    )

    # 1. Start the model - should enter State 0 (Welcome)
    controller.model.start()
    assert controller.model._curState == 0, f"Expected State 0, got {controller.model._curState}"
    assert disp.lines.get(0) == "Welcome to Ikea", f"Expected 'Welcome to Ikea', got {disp.lines.get(0)}"
    Log.i("State 0 (Welcome) verified.")

    # 2. Customer approaches: trigger uss_trip -> State 1 (Selection)
    controller.model.processEvent("uss_trip")
    assert controller.model._curState == 1, f"Expected State 1, got {controller.model._curState}"
    assert disp.lines.get(0) == "How was your", f"Expected 'How was your', got {disp.lines.get(0)}"
    assert disp.lines.get(1) == "visit?", f"Expected 'visit?', got {disp.lines.get(1)}"
    Log.i("State 1 (Selection) on uss_trip verified.")

    # 3. Customer ignores selection: timer_timeout -> State 0
    controller.model.processEvent("timer_timeout")
    assert controller.model._curState == 0, f"Expected State 0, got {controller.model._curState}"
    assert disp.lines.get(0) == "Welcome to Ikea"
    Log.i("Timeout transition back to State 0 verified.")

    # 4. Next customer approaches: uss_trip -> State 1, then green_press -> State 2 (happy)
    controller.model.processEvent("uss_trip")
    assert controller.model._curState == 1
    controller.model.processEvent("green_press")
    assert controller.model._curState == 2, f"Expected State 2, got {controller.model._curState}"
    assert disp.lines.get(0) == "Thank you"
    assert stats.happy_count == 1
    assert stats.unhappy_count == 0
    assert strip.num_pixels == 16  # 100% happy = 16 pixels
    Log.i("State 2 (happy) on green_press verified.")

    # 5. Timer timeout in State 2 -> State 0
    controller.model.processEvent("timer_timeout")
    assert controller.model._curState == 0
    Log.i("Timeout transition from State 2 to State 0 verified.")

    # 6. Third customer: uss_trip -> State 1, then red_press -> State 3 (unhappy)
    # Total = 2 (1 happy, 1 unhappy = 50.0%). Threshold is 50.0% so pct is NOT below threshold yet.
    controller.model.processEvent("uss_trip")
    assert controller.model._curState == 1
    controller.model.processEvent("red_press")
    assert controller.model._curState == 3, f"Expected State 3, got {controller.model._curState}"
    assert disp.lines.get(0) == "Sorry to hear"
    assert disp.lines.get(1) == "that"
    assert stats.happy_count == 1
    assert stats.unhappy_count == 1
    assert strip.num_pixels == 8  # 50% satisfaction = 8 pixels
    Log.i("State 3 (unhappy) on red_press verified (no alarm when pct >= threshold).")

    # 7. Timer timeout in State 3 -> State 0
    controller.model.processEvent("timer_timeout")
    assert controller.model._curState == 0

    # 8. Fourth customer: uss_trip -> State 1, then red_press -> State 3 (unhappy)
    # Total = 3 (1 happy, 2 unhappy = 33.33% < 50.0%). Should automatically transition to State 4 (Alarm)!
    controller.model.processEvent("uss_trip")
    assert controller.model._curState == 1
    controller.model.processEvent("red_press")
    assert controller.model._curState == 4, f"Expected State 4 (Alarm), got {controller.model._curState}"
    assert disp.lines.get(0) == "Calling manager"
    assert strip.color == RED
    Log.i("State 4 (Alarm) triggered via feedback_below_threshold verified.")

    # 9. Test stateDo in State 4 (2-tone alarm)
    controller.stateDo(4)
    assert buz.current_tone == 880
    controller.stateDo(4)
    assert buz.current_tone == 587
    Log.i("2-tone alarm activity verified.")

    # 10. Manager arrives and presses green button: green_press -> State 0
    # On exit, stats must be reset
    controller.model.processEvent("green_press")
    assert controller.model._curState == 0, f"Expected State 0, got {controller.model._curState}"
    assert stats.get_total_count() == 0, f"Expected stats to reset to 0, got {stats.get_total_count()}"
    assert not buz.is_playing, "Buzzer should stop on exiting alarm"
    assert disp.lines.get(0) == "Welcome to Ikea"
    Log.i("Manager acknowledge on green_press and stats reset verified.")

    controller.stop()
    Log.i("Testing complete - all checks passed")

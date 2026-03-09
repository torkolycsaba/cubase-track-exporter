import pyautogui, time, json
with open("config.json", "r") as f:
    config = json.load(f)
EXPORT_HOTKEY = config["export_hotkey"]
time.sleep(3)  # gives you time to click into Cubase
# pyautogui.click(366, 266)
# pyautogui.keyDown('ctrl')
# pyautogui.keyDown('shift')
# pyautogui.keyDown('o')
# pyautogui.keyUp('o')
# pyautogui.keyUp('shift')
# pyautogui.keyUp('ctrl')
# pyautogui.hotkey('ctrl', 'shift', 'o')
# pyautogui.hotkey(*EXPORT_HOTKEY.split("+"))
# print(pyautogui.position())  # prints wherever your mouse is
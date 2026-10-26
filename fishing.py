"""로블록스 자동 낚시 매크로 (macOS 전용, 외부 패키지 불필요).

1. 좌클릭을 꾹 눌러 캐스팅 게이지를 채우다가, 초록 게이지가 위쪽 황금색 구간에 닿으면 손을 뗀다.
2. 화면 아래에 물고기 UI("Click Fast!"/"빠르게 클릭하세요!" + STOP/정지 버튼)가 뜨면 사라질 때까지 연타한다.
3. 보상 화면이 지나가면 다시 1번부터 반복한다.

- 누르고 있어도 게이지가 안 뜨면(보상 화면이 아직 떠 있는 등) 바로 떼고 잠깐 뒤 다시 시도한다.
- 로블록스가 맨 앞에 있을 때만 동작한다. 다른 앱을 보고 있으면 로블록스로 돌아올 때까지 기다린다.
- 실행 중에는 화면이 꺼지거나 잠기지 않게 막는다. (노트북 덮개를 닫으면 잠자기에 들어가므로 열어둘 것)

실행:  낚시매크로.command 더블클릭 (또는 python3 fishing.py)
일시정지/재개:  Control + Option 을 같이 누르기 (소리로 알려줌)
종료:  터미널 창 닫기 또는 Ctrl + C
"""

import ctypes
import ctypes.util
import os
import subprocess
import threading
import time
from datetime import datetime

ROBLOX_PROCESS = "RobloxPlayer"

cg = ctypes.cdll.LoadLibrary(ctypes.util.find_library("CoreGraphics"))
cf = ctypes.cdll.LoadLibrary(ctypes.util.find_library("CoreFoundation"))


class CGPoint(ctypes.Structure):
    _fields_ = [("x", ctypes.c_double), ("y", ctypes.c_double)]


class CGSize(ctypes.Structure):
    _fields_ = [("width", ctypes.c_double), ("height", ctypes.c_double)]


class CGRect(ctypes.Structure):
    _fields_ = [("origin", CGPoint), ("size", CGSize)]


cg.CGEventCreateMouseEvent.restype = ctypes.c_void_p
cg.CGEventCreateMouseEvent.argtypes = [ctypes.c_void_p, ctypes.c_uint32, CGPoint, ctypes.c_uint32]
cg.CGEventPost.argtypes = [ctypes.c_uint32, ctypes.c_void_p]
cg.CGWindowListCopyWindowInfo.restype = ctypes.c_void_p
cg.CGWindowListCopyWindowInfo.argtypes = [ctypes.c_uint32, ctypes.c_uint32]
cg.CGRectMakeWithDictionaryRepresentation.restype = ctypes.c_bool
cg.CGRectMakeWithDictionaryRepresentation.argtypes = [ctypes.c_void_p, ctypes.POINTER(CGRect)]
cg.CGWindowListCreateImage.restype = ctypes.c_void_p
cg.CGWindowListCreateImage.argtypes = [CGRect, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_uint32]
cg.CGImageGetWidth.restype = ctypes.c_size_t
cg.CGImageGetWidth.argtypes = [ctypes.c_void_p]
cg.CGImageGetHeight.restype = ctypes.c_size_t
cg.CGImageGetHeight.argtypes = [ctypes.c_void_p]
cg.CGImageGetBytesPerRow.restype = ctypes.c_size_t
cg.CGImageGetBytesPerRow.argtypes = [ctypes.c_void_p]
cg.CGImageGetDataProvider.restype = ctypes.c_void_p
cg.CGImageGetDataProvider.argtypes = [ctypes.c_void_p]
cg.CGDataProviderCopyData.restype = ctypes.c_void_p
cg.CGDataProviderCopyData.argtypes = [ctypes.c_void_p]
cg.CGEventSourceFlagsState.restype = ctypes.c_uint64
cg.CGEventSourceFlagsState.argtypes = [ctypes.c_int32]
cf.CFRelease.argtypes = [ctypes.c_void_p]
cf.CFArrayGetCount.restype = ctypes.c_long
cf.CFArrayGetCount.argtypes = [ctypes.c_void_p]
cf.CFArrayGetValueAtIndex.restype = ctypes.c_void_p
cf.CFArrayGetValueAtIndex.argtypes = [ctypes.c_void_p, ctypes.c_long]
cf.CFDictionaryGetValue.restype = ctypes.c_void_p
cf.CFDictionaryGetValue.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
cf.CFNumberGetValue.restype = ctypes.c_bool
cf.CFNumberGetValue.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p]
cf.CFStringCreateWithCString.restype = ctypes.c_void_p
cf.CFStringCreateWithCString.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_uint32]
cf.CFDataGetLength.restype = ctypes.c_long
cf.CFDataGetLength.argtypes = [ctypes.c_void_p]
cf.CFDataGetBytePtr.restype = ctypes.c_void_p
cf.CFDataGetBytePtr.argtypes = [ctypes.c_void_p]

HID_EVENT_TAP = 0
EVENT_SOURCE_HID = 1
HOTKEY_FLAGS = 0x40000 | 0x80000  # Control + Option
MOUSE_LEFT_DOWN = 1
MOUSE_LEFT_UP = 2
MOUSE_BUTTON_LEFT = 0
WINDOW_LIST_ALL = 0
WINDOW_LIST_ON_SCREEN = 1
CF_NUMBER_SINT32 = 3
CF_STRING_UTF8 = 0x08000100

# 좌클릭을 누른 뒤 이 시간 안에 게이지가 안 뜨면 아직 캐스팅할 수 없는 상태로 보고 뗐다가 다시 시도
METER_APPEAR_TIMEOUT = 2.0
RETRY_WAIT = 0.7
MAX_NORMAL_HOLD = 10  # 게이지가 황금색 구간까지 차는 데 걸리는 최대 시간(초). 슬로우 모드에서는 4초 넘게 걸린다
# 물고기 UI 의 STOP 버튼을 찾을 범위 (창 크기 대비 비율: 왼쪽, 위, 오른쪽, 아래)
STOP_SEARCH = (0.722, 0.85, 0.772, 1.0)
# 캐스팅 게이지를 찾을 범위 (창 크기 대비 비율)
METER_SEARCH = (0.2, 0.1, 0.8, 0.8)
CLICKS_PER_SECOND = 15
BITE_TIMEOUT = 12  # 캐스팅 후 물고기 UI 를 기다리는 최대 시간(초). 보통 4~7초 안에 뜬다
REWARD_WAIT = 1.0  # 잡은 뒤 잠깐 쉬는 시간(초). 아직 캐스팅할 수 없으면 cast 가 알아서 다시 시도한다


running = threading.Event()  # 꺼져 있으면 일시정지 상태


def cfstr(text):
    return cf.CFStringCreateWithCString(None, text.encode(), CF_STRING_UTF8)


KEY_OWNER_PID = cfstr("kCGWindowOwnerPID")
KEY_LAYER = cfstr("kCGWindowLayer")
KEY_BOUNDS = cfstr("kCGWindowBounds")


def cf_int(number_ref):
    value = ctypes.c_int32()
    cf.CFNumberGetValue(number_ref, CF_NUMBER_SINT32, ctypes.byref(value))
    return value.value


def roblox_pid():
    result = subprocess.run(["pgrep", "-x", ROBLOX_PROCESS], capture_output=True, text=True)
    pids = result.stdout.split()
    return int(pids[0]) if pids else None


def front_pid():
    asn = subprocess.run(["lsappinfo", "front"], capture_output=True, text=True).stdout.strip()
    info = subprocess.run(["lsappinfo", "info", "-only", "pid", asn], capture_output=True, text=True).stdout
    digits = "".join(ch for ch in info.split("=")[-1] if ch.isdigit())
    return int(digits) if digits else None


def window_rect(pid):
    """해당 프로세스의 일반 창(layer 0) 중 가장 큰 창의 위치/크기."""
    windows = cg.CGWindowListCopyWindowInfo(WINDOW_LIST_ALL, 0)
    best = None
    try:
        for i in range(cf.CFArrayGetCount(windows)):
            info = cf.CFArrayGetValueAtIndex(windows, i)
            if cf_int(cf.CFDictionaryGetValue(info, KEY_OWNER_PID)) != pid:
                continue
            if cf_int(cf.CFDictionaryGetValue(info, KEY_LAYER)) != 0:
                continue
            rect = CGRect()
            if not cg.CGRectMakeWithDictionaryRepresentation(cf.CFDictionaryGetValue(info, KEY_BOUNDS), ctypes.byref(rect)):
                continue
            area = rect.size.width * rect.size.height
            if best is None or area > best.size.width * best.size.height:
                best = rect
    finally:
        cf.CFRelease(windows)
    return best


# ---------- 화면 읽기 ----------


class Frame:
    """화면 일부를 캡처한 이미지. 좌표는 캡처한 영역 기준 픽셀(레티나면 pt 의 2배)."""

    def __init__(self, data, width, height, bytes_per_row, origin, scale):
        self.data, self.width, self.height, self.bpr = data, width, height, bytes_per_row
        self.origin, self.scale = origin, scale

    def rgb(self, x, y):
        i = y * self.bpr + x * 4  # BGRA
        d = self.data
        return d[i + 2], d[i + 1], d[i]


def capture(x, y, w, h):
    """화면 좌표(pt) 영역을 캡처한다."""
    rect = CGRect(CGPoint(x, y), CGSize(w, h))
    image = cg.CGWindowListCreateImage(rect, WINDOW_LIST_ON_SCREEN, 0, 0)
    if not image:
        return None
    data = cg.CGDataProviderCopyData(cg.CGImageGetDataProvider(image))
    buf = ctypes.string_at(cf.CFDataGetBytePtr(data), cf.CFDataGetLength(data))
    width, height, bpr = cg.CGImageGetWidth(image), cg.CGImageGetHeight(image), cg.CGImageGetBytesPerRow(image)
    cf.CFRelease(data)
    cf.CFRelease(image)
    return Frame(buf, width, height, bpr, (x, y), width / w)


def capture_ratio(win, box):
    left, top, right, bottom = box
    return capture(
        win.origin.x + win.size.width * left,
        win.origin.y + win.size.height * top,
        win.size.width * (right - left),
        win.size.height * (bottom - top),
    )


def is_navy(r, g, b):
    """캐스팅 게이지의 비어 있는 부분 색. 게이지가 게임 속 공간에 떠 있어서 맵 조명에 따라
    밝을 땐 (29, 41, 65), 어두운 맵에선 (21, 25, 34) 처럼 달라지므로 '어둡고 푸른 기가 도는 색' 으로 본다.
    청록색 물(파랑 ≈ 초록) 과 헷갈리지 않게 파랑이 초록보다 확실히 높아야 한다."""
    return r < 70 and g < 80 and b < 110 and b - r >= 10 and b - g >= 5


def is_stop_red(r, g, b):
    """STOP 버튼의 빨간색 (약 210, 70, 62)."""
    return r > 170 and 35 < g < 120 and 30 < b < 110 and r - g > 90


def is_light(r, g, b):
    """버튼 글자의 흰색. 창이 작으면 글자가 작아 테두리와 섞이므로 약간 어두운 흰색까지 본다."""
    return r > 170 and g > 170 and b > 170


def navy_run(frame, x, y):
    """(x, y) 에서 위아래로 이어진 남색 구간의 (위, 아래) y."""
    top = bottom = y
    while top > 0 and is_navy(*frame.rgb(x, top - 1)):
        top -= 1
    while bottom < frame.height - 1 and is_navy(*frame.rgb(x, bottom + 1)):
        bottom += 1
    return top, bottom


def navy_span(frame, x, y):
    """(x, y) 에서 좌우로 이어진 남색 구간의 (왼쪽, 오른쪽) x."""
    left = right = x
    while left > 0 and is_navy(*frame.rgb(left - 1, y)):
        left -= 1
    while right < frame.width - 1 and is_navy(*frame.rgb(right + 1, y)):
        right += 1
    return left, right


def find_meter(frame, win_width):
    """캐스팅 게이지의 비어 있는 남색 기둥을 찾는다. 찾으면 (가운데 x, 위 y, 아래 y) 를, 못 찾으면 None.

    게이지 크기는 창 크기에 비례한다 (폭이 창 너비의 약 0.8%: 1470pt 창에서 12pt, 800pt 창에서 6.5pt)."""
    unit = win_width * frame.scale / 1000  # 창 너비의 0.1% (픽셀)
    min_width, max_width = 4 * unit, 14 * unit
    min_height = int(20 * unit)
    for y in range(0, frame.height, max(1, min_height // 3)):
        for x in range(0, frame.width, max(1, int(min_width))):
            if not is_navy(*frame.rgb(x, y)):
                continue
            # 좁은 세로 기둥인지 확인: 폭이 게이지만 하고, 아래쪽도 같은 폭이고, 위아래로 충분히 길어야 한다
            left, right = navy_span(frame, x, y)
            if not min_width <= right - left + 1 <= max_width:
                continue
            cx = (left + right) // 2
            top, bottom = navy_run(frame, cx, y)
            if bottom - top < min_height:
                continue
            left2, right2 = navy_span(frame, cx, (top + bottom) // 2)
            if abs((right2 - left2) - (right - left)) > 2 * frame.scale:
                continue
            if has_cream_line_above(frame, cx, top):
                return cx, top, bottom
    return None


def has_cream_line_above(frame, x, top):
    """게이지의 빈 부분 바로 위에는 황금색 구간과 경계를 이루는 밝은 크림색 선이 있다."""
    for y in range(max(0, top - int(5 * frame.scale)), top):
        r, g, b = frame.rgb(x, y)
        if r > 230 and g > 225 and b > 185:
            return True
    return False


def stop_button_visible(win):
    """화면 아래 띠에서 빨간 STOP/정지 버튼을 찾는다.
    창 모드에서는 제목 표시줄(28pt) 만큼 버튼이 아래로 밀리므로 고정 위치 대신 세로로 훑는다."""
    frame = capture_ratio(win, STOP_SEARCH)
    if frame is None:
        return False
    step = max(1, int(frame.scale))
    xs = range(0, frame.width, step)
    # 버튼 가운데에는 글자와 검은 테두리가 있어서 그 줄은 빨간색이 절반쯤만 된다
    red_rows = [sum(is_stop_red(*frame.rgb(x, y)) for x in xs) > len(xs) * 0.25 for y in range(0, frame.height, step)]
    best_start = best_len = 0
    start = None
    for i, red in enumerate(red_rows + [False]):
        if red and start is None:
            start = i
        elif not red and start is not None:
            if i - start > best_len:
                best_start, best_len = start, i - start
            start = None
    # 버튼 높이도 창 크기에 비례한다 (1470pt 창에서 32pt, 800pt 창에서 21pt)
    height = best_len * step / frame.scale
    if not 0.015 * win.size.width <= height <= 0.035 * win.size.width:
        return False
    # 배경의 빨간 벽돌도 빨간색으로 잡히므로, 버튼 글자의 밝은 픽셀이 같이 있어야 물고기 UI 로 본다
    light = total = 0
    for i in range(best_start, best_start + best_len):
        for x in xs:
            total += 1
            light += is_light(*frame.rgb(x, i * step))
    return light / total > 0.02


# ---------- 마우스 ----------


def post(event):
    cg.CGEventPost(HID_EVENT_TAP, event)
    cf.CFRelease(event)


def mouse(kind, point):
    post(cg.CGEventCreateMouseEvent(None, kind, point, MOUSE_BUTTON_LEFT))


def click(point):
    mouse(MOUSE_LEFT_DOWN, point)
    time.sleep(0.5 / CLICKS_PER_SECOND)
    mouse(MOUSE_LEFT_UP, point)
    time.sleep(0.5 / CLICKS_PER_SECOND)


# ---------- 낚시 단계 ----------


def log(message):
    print(f"[{datetime.now():%H:%M:%S}] {message}", flush=True)


def cast(win, point):
    """좌클릭을 누른 채 게이지가 황금색 구간에 닿으면 뗀다. 캐스팅이 시작됐으면 True."""
    mouse(MOUSE_LEFT_DOWN, point)
    start = time.time()
    meter = None
    try:
        # 1) 게이지가 나타날 때까지 찾는다. 안 나타나면 보상 화면 등으로 아직 캐스팅할 수 없는 상태다.
        while time.time() - start < METER_APPEAR_TIMEOUT:
            frame = capture_ratio(win, METER_SEARCH)
            found = frame and find_meter(frame, win.size.width)
            if found:
                x, top, bottom = found
                meter = (frame.origin[0] + x / frame.scale, frame.origin[1] + top / frame.scale,
                         (bottom - top) / frame.scale, frame.scale)
                break
        if meter is None:
            log(f"{METER_APPEAR_TIMEOUT}초 동안 게이지가 안 떠서 뗌 - 다시 시도")
            return False

        # 2) 게이지 기둥 한 줄만 빠르게 읽으면서 남색(빈 부분)이 사라지는 순간을 기다린다.
        #    처음 찾은 빈 부분 길이만큼만 읽어야 게이지 아래 배경의 어두운 색을 빈 부분으로 착각하지 않는다
        mx, mtop, mheight, scale = meter
        while time.time() - start < METER_APPEAR_TIMEOUT + MAX_NORMAL_HOLD:
            strip = capture(mx - 1, mtop, 2, mheight)
            if strip is None:
                continue
            empty = sum(is_navy(*strip.rgb(strip.width // 2, y)) for y in range(strip.height))
            if empty < 4 * scale:
                held = time.time() - start
                if held > MAX_NORMAL_HOLD:
                    # 이보다 오래 걸렸으면 게이지가 아닌 걸 본 것
                    log(f"누른 시간이 이상함({held:.2f}초) - 캐스팅 실패로 보고 다시 시도")
                    return False
                log(f"황금색 구간 도달 - 뗌 ({held:.2f}초)")
                return True
        log("게이지가 끝까지 안 차서 뗌 - 다시 시도")
        return False
    finally:
        mouse(MOUSE_LEFT_UP, point)


def wait_for_bite(win):
    start = time.time()
    while time.time() - start < BITE_TIMEOUT and running.is_set():
        if stop_button_visible(win):
            return True
        time.sleep(0.1)
    return False


def reel(win, point):
    """물고기 UI 가 사라질 때까지 연타."""
    clicks = 0
    misses = 0
    start = time.time()
    while time.time() - start < 30 and running.is_set():
        for _ in range(4):
            click(point)
            clicks += 1
        if stop_button_visible(win):
            misses = 0
        else:
            misses += 1
            if misses >= 2:
                break
    log(f"연타 {clicks}번 - 물고기 UI 사라짐")


def fish_once(pid):
    win = window_rect(pid)
    if win is None:
        log("로블록스 창을 찾지 못함")
        time.sleep(2)
        return
    point = CGPoint(win.origin.x + win.size.width / 2, win.origin.y + win.size.height / 2)

    if not cast(win, point):
        time.sleep(RETRY_WAIT)  # 아직 캐스팅할 수 없는 상태 - 잠깐 뒤 다시 시도
        return
    if not wait_for_bite(win):
        if running.is_set():
            log(f"{BITE_TIMEOUT}초 동안 물고기 UI 가 안 떠서 다시 캐스팅")
        return
    log("물고기 UI 뜸 - 연타 시작")
    reel(win, point)
    time.sleep(REWARD_WAIT)


def watch_hotkey():
    """Control + Option 을 같이 누를 때마다 일시정지/재개를 바꾼다."""
    was_down = False
    while True:
        flags = cg.CGEventSourceFlagsState(EVENT_SOURCE_HID)
        down = flags & HOTKEY_FLAGS == HOTKEY_FLAGS
        if down and not was_down:
            if running.is_set():
                running.clear()
                log("일시정지 (다시 시작하려면 Control + Option)")
                subprocess.Popen(["afplay", "/System/Library/Sounds/Bottle.aiff"])
            else:
                running.set()
                log("다시 시작")
                subprocess.Popen(["afplay", "/System/Library/Sounds/Glass.aiff"])
        was_down = down
        time.sleep(0.05)


def main():
    # 화면이 꺼지거나 잠기면 입력이 안 들어가므로, 매크로가 도는 동안 화면/시스템 잠자기를 막는다.
    subprocess.Popen(["caffeinate", "-d", "-i", "-w", str(os.getpid())])
    running.set()
    threading.Thread(target=watch_hotkey, daemon=True).start()

    print("낚시 매크로 시작. 로블록스가 맨 앞에 있을 때만 동작.", flush=True)
    print("Control + Option 을 같이 누르면 일시정지/재개. 완전히 끄려면 이 창을 닫거나 Ctrl+C", flush=True)
    waiting = False
    try:
        while True:
            if not running.is_set():
                time.sleep(0.1)
                continue
            pid = roblox_pid()
            if pid is None or front_pid() != pid:
                if not waiting:
                    log("로블록스가 맨 앞에 없음 - 돌아올 때까지 대기")
                    waiting = True
                time.sleep(1)
                continue
            waiting = False
            fish_once(pid)
    except KeyboardInterrupt:
        print("\n매크로 종료")


if __name__ == "__main__":
    main()

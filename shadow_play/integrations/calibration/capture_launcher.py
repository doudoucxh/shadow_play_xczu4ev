#!/usr/bin/env python3
"""Ubuntu desktop entry for camera practice and the synthetic capture demo."""
import argparse
from datetime import datetime
import json
import math
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parents[2]
SETTINGS = ROOT / "runtime" / "capture-launcher.json"


def validate_settings(data):
    if not isinstance(data, dict) or data.get("version") != 1:
        raise ValueError("启动设置格式无效，请重新配置。")
    camera = data.get("camera")
    if type(camera) is not int or camera < 0:
        raise ValueError("摄像头编号必须是非负整数。")
    for name in ("width_mm", "height_mm"):
        value = data.get(name)
        if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
            raise ValueError("有效幕布宽高必须是大于 0 的有限毫米数值。")
    return data


def read_value(prompt, parser, check, default=None):
    while True:
        suffix = " [{}]".format(default) if default is not None else ""
        raw = input(prompt + suffix + "：").strip()
        try:
            value = parser(raw) if raw else default
            if value is not None and check(value):
                return value
        except (ValueError, OverflowError):
            pass
        print("输入无效，请按提示填写数字。")


def configure():
    previous = {}
    if SETTINGS.exists():
        try:
            previous = validate_settings(json.loads(SETTINGS.read_text(encoding="utf-8")))
        except (ValueError, OSError):
            pass
    print("首次摄像头练习设置；幕布尺寸用实测有效区域，不是外框尺寸。")
    data = {
        "version": 1,
        "camera": read_value("摄像头编号（/dev/video0 对应 0）", int,
                             lambda x: x >= 0, previous.get("camera", 0)),
        "width_mm": read_value("有效幕布宽度（mm）", float,
                               lambda x: math.isfinite(x) and x > 0, previous.get("width_mm")),
        "height_mm": read_value("有效幕布高度（mm）", float,
                                lambda x: math.isfinite(x) and x > 0, previous.get("height_mm")),
    }
    validate_settings(data)
    SETTINGS.parent.mkdir(parents=True, exist_ok=True)
    temporary = SETTINGS.with_name(SETTINGS.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temporary.replace(SETTINGS)
    finally:
        if temporary.exists():
            temporary.unlink()
    print("设置已保存：{}".format(SETTINGS))
    return data


def desktop_string(value):
    return str(value).replace("\\", "\\\\").replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t")


def exec_argument(value):
    # Exec quoting is different from shell quoting. Desktop files are never run
    # through a shell; escape the Exec layer before the desktop string layer.
    value = str(value).replace("%", "%%")
    for character in ("\\", '"', "`", "$"):
        value = value.replace(character, "\\" + character)
    return '"' + desktop_string(value) + '"'


def desktop_directory(override):
    if override:
        return Path(override).expanduser().resolve()
    command = shutil.which("xdg-user-dir")
    if command:
        result = subprocess.run([command, "DESKTOP"], capture_output=True, text=True, timeout=5)
        value = result.stdout.strip()
        if result.returncode == 0 and value:
            path = Path(value)
            if path.is_absolute() and path != Path.home():
                return path
            return None
    for name in ("桌面", "Desktop"):
        path = Path.home() / name
        if path.is_dir():
            return path
    return None


def install_shortcuts(override):
    if not sys.platform.startswith("linux"):
        raise ValueError("请在 Ubuntu 中运行安装命令，入口用于 Ubuntu 桌面。")
    binary = ROOT / "build-capture" / "shadow_capture"
    if not binary.is_file() or not os.access(str(binary), os.X_OK):
        raise ValueError("请先在 Ubuntu 编译 build-capture/shadow_capture。")
    data_home = Path(os.environ.get("XDG_DATA_HOME", "")).expanduser()
    if not data_home.is_absolute():
        data_home = Path.home() / ".local" / "share"
    applications = data_home / "applications"
    desktop = desktop_directory(override)
    directories = [applications] + ([desktop] if desktop else [])
    for mode, title, icon in (
        ("camera", "皮影坐标采集（摄像头练习）", "camera-photo"),
        ("demo", "皮影坐标采集（演示）", "applications-science"),
    ):
        command = " ".join(exec_argument(x) for x in (sys.executable, Path(__file__).resolve()))
        command += " --mode " + mode
        content = "\n".join([
            "[Desktop Entry]", "Type=Application", "Name=" + title,
            "Comment=打开坐标采集练习；每次使用独立保存目录，不发送实物电机命令",
            "Exec=" + command, "Path=" + desktop_string(ROOT), "Icon=" + icon,
            "Terminal=true", "Categories=Education;Science;", "StartupNotify=false", "",
        ])
        for directory in directories:
            directory.mkdir(parents=True, exist_ok=True)
            target = directory / ("shadow-capture-" + mode + ".desktop")
            target.write_text(content, encoding="utf-8")
            target.chmod(0o755)
            print("已安装：{}".format(target))
    print("可从应用菜单打开。桌面图标若提示不可信，右键选择“允许启动”。")
    if desktop is None:
        print("未检测到桌面目录；请从应用菜单搜索“皮影坐标采集”。")
    print("工程目录移动后，请在新位置重新运行安装命令。")


def launch(mode, print_only=False):
    binary = ROOT / "build-capture" / "shadow_capture"
    if not binary.is_file() or not os.access(str(binary), os.X_OK):
        raise ValueError("找不到可执行程序，请先在 Ubuntu 编译 build-capture/shadow_capture。")
    settings = None
    if mode == "camera":
        settings = (validate_settings(json.loads(SETTINGS.read_text(encoding="utf-8")))
                    if SETTINGS.exists() else configure())
    name = "{}-{}-{}".format("camera-practice" if mode == "camera" else "demo",
                             datetime.now().strftime("%Y%m%d-%H%M%S-%f"), uuid.uuid4().hex[:8])
    session = ROOT / "capture-sessions" / name
    # Do not create the session directory: the capture application owns it.
    command = [str(binary), "--reference-view", "front", "--config", str(ROOT / "config" / "capture.demo.json"),
               "--session", str(session)]
    if settings is None:
        command += ["--demo"]
    else:
        command += ["--camera", str(settings["camera"]), "--backend", "manual_unconfirmed",
                    "--stage-width-mm", str(settings["width_mm"]),
                    "--stage-height-mm", str(settings["height_mm"])]
    print("本轮保存目录：{}".format(session), flush=True)
    print("练习模式：指令单位为 demo，本入口不控制电机。", flush=True)
    if print_only:
        print(shlex.join(command))
        return 0
    result = subprocess.run(command, cwd=str(ROOT))
    print("界面已关闭。保存目录：{}".format(session), flush=True)
    if result.returncode:
        print("启动或运行失败，退出码 {}。请保留上方报错；相机问题先检查 USB 转交和编号。".format(result.returncode))
    return result.returncode


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("camera", "demo"), default="camera")
    parser.add_argument("--install-shortcuts", action="store_true")
    parser.add_argument("--desktop-dir", help="安装入口时显式指定桌面目录")
    parser.add_argument("--configure", action="store_true", help="重新填写摄像头编号和有效幕布尺寸")
    parser.add_argument("--print-command", action="store_true", help="只显示启动参数，不打开相机或界面")
    parser.add_argument("--no-wait", action="store_true", help="退出前不等待回车")
    args = parser.parse_args()
    if args.install_shortcuts:
        install_shortcuts(args.desktop_dir)
        return 0
    if args.configure:
        configure()
        return 0
    result = 1
    try:
        result = launch(args.mode, args.print_command)
    except (OSError, ValueError) as error:
        print("错误：{}".format(error))
        print("需要修改启动设置时，运行：python3 integrations/calibration/capture_launcher.py --configure")
    if not args.no_wait and not args.print_command and sys.stdin.isatty():
        input("按回车关闭本启动窗口。")
    return result


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (KeyboardInterrupt, EOFError):
        print("\n已取消。")
        sys.exit(1)
    except (OSError, ValueError, subprocess.TimeoutExpired) as error:
        print("错误：{}".format(error))
        sys.exit(1)

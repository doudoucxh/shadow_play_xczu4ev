# VirtualBox Ubuntu：从安装工具到运行演示

适用情况：终端类似 `peter@peter-VirtualBox:~$`，提示找不到 `cmake` / `ctest`。

WSL 和 VirtualBox 虚拟机是两个独立环境。此前 WSL 的依赖安装和编译结果不会自动出现在虚拟机；`/mnt/d/ZYNQ` 也不是这里已确认可用的路径。现在先在虚拟机中完成电脑仿真，这一步不使用 PetaLinux 或 Vivado。

## 1. 在虚拟机 Ubuntu 安装工具

按顺序执行，每步成功后再进行下一步：

```bash
sudo apt update
sudo apt install build-essential cmake ninja-build pkg-config libasound2-dev unzip
```

`sudo` 提示密码时输入 Ubuntu 登录密码；终端不显示输入的密码字符是正常现象。安装出现确认提示时输入 `Y`。

检查：

```bash
cmake --version
ctest --version
g++ --version
```

工程声明最低 CMake 3.16，并使用 C++17；你贴出的 apt 提示版本 3.16.3 满足工程声明的最低要求。无需仅为解决“命令不存在”而安装多个版本的 CMake。VirtualBox 中的实际编译和测试结果仍需你运行下面步骤确认。

## 2. 把源码放入虚拟机

Windows 工程在 `D:\ZYNQ\shadow_play`。另提供 `D:\ZYNQ\shadow_play-source-v0.2.zip`，包含源码、配置、示例资源和文档，不包含其他环境的构建目录。

通过已配置的共享文件夹、文件拖放或 U 盘，把这个 ZIP 复制到虚拟机。文件拖放是否可用取决于 VirtualBox 的增强功能和配置；无法拖放时使用已经可用的文件传输方式。

在 Ubuntu 文件管理器中将 ZIP 放到当前用户的“主目录”，然后在终端执行：

```bash
cd ~
unzip -n shadow_play-source-v0.2.zip
cd ~/shadow_play
pwd
ls
```

`unzip -n` 不覆盖已有文件。如果主目录已经有你改动过的 `shadow_play`，请把新包解压到另一个空文件夹，并进入其中的 `shadow_play` 再构建。

对用户名 peter，上面的 `pwd` 应显示 `/home/peter/shadow_play`。`ls` 应至少显示 `CMakeLists.txt`、`src`、`include`、`assets`、`config`、`tests` 和 `third_party`。

如果已经通过其他方式复制了完整工程，也可以直接进入它所在的目录，确认有上述文件。只复制 `.cpp` 文件不足以构建本工程。

如果 `unzip` 找不到 ZIP，先用文件管理器确认实际存放位置；如果 `cd` 提示目录不存在，说明源码还没有放在该位置。先解决路径问题，再继续。

## 3. 配置和编译

确认当前目录是包含 `CMakeLists.txt` 的工程根目录后执行：

```bash
cmake -S . -B build-vm -G Ninja -DCMAKE_BUILD_TYPE=Debug
cmake --build build-vm --parallel 2
```

这里使用新的 `build-vm`，避免复用 Windows 或 WSL 的构建缓存。第一条成功时会显示配置/生成完成，并写入 `build-vm`；第二条才真正编译程序。`--parallel 2` 适合先在虚拟机中减少同时编译的任务数。

如果 `build-vm` 已经是从其他环境复制来的旧构建目录，改用一个新的目录名，并在后续命令中保持一致。

## 4. 运行测试

```bash
cd build-vm
ctest --output-on-failure
cd ..
```

预期运行 6 项 CTest，并显示 `100% tests passed`。如果有失败，保留输出并先排查。

这里特意进入构建目录再运行 `ctest`。`--test-dir` 从 CMake 3.20 才引入，不适用于你所示的 3.16 版本：[CMake 官方说明](https://cmake.org/cmake/help/latest/manual/ctest.1.html#cmdoption-ctest-test-dir)。

## 5. 运行 90 秒仿真

回到工程根目录后执行：

```bash
./build-vm/shadow_show --seconds 92 --output build-vm/my_rehearsal.csv
./build-vm/trace_preview build-vm/my_rehearsal.csv build-vm/my_rehearsal.svg
```

第一条生成电机角度数据，第二条生成轨迹图；这是加速、静音的软件仿真。前 90 秒为剧本，后 2 秒观察结束后回中。

输出文件已存在时，工具会拒绝覆盖。重复运行可以将两条命令中的文件名一致改为 `my_rehearsal2.csv` / `my_rehearsal2.svg`。

在 Ubuntu 文件管理器中打开“主目录 → shadow_play → build-vm → my_rehearsal.svg”，选择浏览器查看。文件扩展名是 `.svg`，不是 `.sSSg`。

## 报错对应关系

| 现象 | 先检查 |
| --- | --- |
| `cmake: command not found` | 第 1 步是否在当前这台 Ubuntu 中安装成功 |
| `ctest: command not found` | `cmake` 包是否安装成功 |
| 找不到 `CMakeLists.txt` | 当前目录是否为解压后的工程根目录 |
| `build-vm/...` 不存在 | 配置和编译是否成功；当前是否仍在工程根目录 |
| CMake 缓存含 `/mnt/d/...` | 是否误用了 WSL 的旧构建目录 |
| `No tests were found` | 是否进入当前虚拟机生成的 `build-vm` 目录 |

上述步骤成功后，再按根目录 README 继续触控、摄像头和三模式模拟。README 的 `build-linux` 在本虚拟机对应 `build-vm`，工程目录对应你刚才解压的位置。

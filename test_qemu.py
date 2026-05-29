#!/usr/bin/env python3
"""RV1108 U-Boot QEMU 模拟测试脚本
使用 Cortex-A7 + QEMU ARM virt 板模拟 RV1108 环境，自动化交互测试 U-Boot 功能
"""

import pexpect
import sys
import time

U_BOOT_BIN = "u-boot.bin"
ENV_FLASH = "/tmp/uboot-env.bin"
UBOOT_FLASH = "/tmp/uboot-flash.bin"

qemu_cmd = [
    "qemu-system-arm",
    "-M", "virt,highmem=false",
    "-cpu", "cortex-a7",
    "-m", "128",
    "-nographic",
    "-drive", f"if=pflash,format=raw,file={UBOOT_FLASH}",
    "-drive", f"if=pflash,format=raw,file={ENV_FLASH}",
    "-nic", "user,model=e1000",          # e1000 网卡 + user模式网络
    "-device", "usb-ehci",               # USB EHCI 控制器
    "-device", "usb-kbd",                # USB 键盘
    "-device", "nvme,serial=nvme0,drive=nvme0",  # NVMe 存储
    "-drive", "if=none,id=nvme0,file=/tmp/nvme.img,format=raw",
]

def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}")

def main():
    log("=== RV1108 U-Boot QEMU 模拟测试 ===")
    log(f"CPU: Cortex-A7 | 内存: 128MB | 网络: e1000 | USB: EHCI | 存储: NVMe")

    log("启动 QEMU + U-Boot...")
    child = pexpect.spawn(" ".join(qemu_cmd), encoding="utf-8", timeout=30, maxread=65536)
    child.logfile_read = None  # 设为 sys.stdout 可看完整输出

    # 等待 U-Boot 命令行提示符
    try:
        child.expect(r"=>", timeout=15)
    except pexpect.TIMEOUT:
        print("错误: U-Boot 未能启动到命令行")
        print(f"输出: {child.before[-1000:]}")
        return 1

    # 先按任意键打断自动启动
    child.sendline("")
    child.expect(r"=>", timeout=3)
    log("U-Boot 启动成功!")

    def run_test(name, cmd, expect_str, timeout=10):
        child.sendline(cmd)
        try:
            child.expect(expect_str, timeout=timeout)
            print(f"  [PASS] {name}")
            return True
        except pexpect.TIMEOUT:
            print(f"  [FAIL] {name} - 超时")
            print(f"  最后输出: {child.before[-500:]}")
            return False
        except pexpect.EOF:
            print(f"  [FAIL] {name} - QEMU退出")
            return False

    results = []

    # 1. 版本信息
    results.append(run_test("version", "version", "U-Boot 2026", timeout=5))

    # 2. 板级信息
    results.append(run_test("bdinfo", "bdinfo", "boot_params", timeout=5))

    # 3. 内存读写测试
    results.append(run_test("md 内存读取", "md 0x40000000 10", "[0-9a-f]{8}:", timeout=5))

    results.append(run_test("mw 内存写入", "mw 0x40000000 0xdeadbeef", "=>", timeout=5))
    results.append(run_test("md 验证写入", "md 0x40000000 4", "deadbeef", timeout=5))

    results.append(run_test("cp 内存复制", "cp 0x40000000 0x40100000 1024", "=>", timeout=5))

    # 5. 环境变量
    results.append(run_test("printenv", "printenv bootcmd", "bootcmd=", timeout=5))

    # 6. 网络测试
    results.append(run_test("dhcp", "dhcp", "DHCP client bound", timeout=15))

    results.append(run_test("ping", "ping 10.0.2.2", "is alive", timeout=10))

    # 7. 存储检测 (NVMe)
    results.append(run_test("nvme scan", "nvme scan", "=>", timeout=10))
    results.append(run_test("nvme info", "nvme info", "=>", timeout=5))

    # 9. Flash 探测
    results.append(run_test("flinfo", "flinfo", "Sector", timeout=10))

    # 10. help
    results.append(run_test("help", "help", "version", timeout=15))

    # 汇总
    print()
    log(f"=== 测试结果: {sum(results)}/{len(results)} 通过 ===")
    for name, ok in zip([
        "version", "bdinfo", "md 内存读取", "mw 内存写入", "md 验证写入",
        "cp 内存复制", "printenv", "dhcp", "ping", "nvme scan", "nvme info",
        "flinfo", "help"
    ], results):
        print(f"  {'[PASS]' if ok else '[FAIL]'} {name}")

    child.sendline("reset")
    child.close()
    return 0 if all(results) else 1

if __name__ == "__main__":
    sys.exit(main())

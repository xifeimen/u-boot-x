#!/usr/bin/env python3
"""RV1108 不死 U-Boot Web 升级 QEMU 测试脚本
测试 httpd 命令：Web 页面访问、固件上传、重启
"""

import pexpect
import sys
import os
import time
import subprocess

U_BOOT_BIN = "u-boot.bin"
ENV_FLASH = "/tmp/uboot-env.bin"
UBOOT_FLASH = "/tmp/uboot-flash.bin"

def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}")

def main():
    log("=== 不死 U-Boot Web 升级 QEMU 测试 ===")

    # 准备 flash 镜像
    if not os.path.exists(UBOOT_FLASH):
        log("创建 U-Boot flash 镜像...")
        subprocess.run(f"dd if=/dev/zero of={UBOOT_FLASH} bs=1M count=64", shell=True, check=True)
        subprocess.run(f"dd if={U_BOOT_BIN} of={UBOOT_FLASH} conv=notrunc", shell=True, check=True)

    if not os.path.exists(ENV_FLASH):
        subprocess.run(f"dd if=/dev/zero of={ENV_FLASH} bs=1M count=64", shell=True, check=True)

    # QEMU 参数
    qemu_args = [
        "qemu-system-arm",
        "-M", "virt,highmem=false", "-cpu", "cortex-a7", "-m", "128",
        "-nographic",
        "-drive", f"if=pflash,format=raw,file={UBOOT_FLASH}",
        "-drive", f"if=pflash,format=raw,file={ENV_FLASH}",
        "-nic", "user,model=e1000,hostfwd=tcp::8880-:80",
    ]

    log("启动 QEMU...")
    child = pexpect.spawn(" ".join(qemu_args), encoding="utf-8", timeout=30, maxread=65536)
    # child.logfile_read = sys.stdout  # 取消此行注释可看到完整输出

    # 等待 U-Boot 命令行
    try:
        child.expect(r"=>", timeout=15)
    except:
        print("错误: U-Boot 未能启动")
        return 1

    child.sendline("")
    child.expect(r"=>", timeout=3)
    log("U-Boot 启动成功!")

    # 启动 httpd
    log("输入 httpd 命令启动 Web 服务器...")
    child.sendline("httpd")
    try:
        idx = child.expect([r"Web .*已启动", r"DHCP 成功"], timeout=20)
        log(f"httpd 已启动! DHCP 成功")
    except pexpect.TIMEOUT:
        print("httpd 启动超时")
        print(child.before[-1000:])
        return 1

    # 获取 IP
    child.expect(r"http://\d+\.\d+\.\d+\.\d+/", timeout=5)
    output = child.before + child.after
    import re
    ip_match = re.search(r'(\d+\.\d+\.\d+\.\d+)', output)
    u_ip = ip_match.group(1) if ip_match else "10.0.2.15"

    # 测试 Web 访问
    log("测试 Web 首页访问...")
    time.sleep(2)
    try:
        import urllib.request
        resp = urllib.request.urlopen("http://localhost:8880/", timeout=10)
        html = resp.read().decode("utf-8")
        if "不死 U-Boot" in html:
            log("Web 首页测试 [PASS]")
        else:
            log(f"Web 首页测试 [FAIL] - 内容不匹配")
    except Exception as e:
        log(f"Web 首页测试 [FAIL] - {e}")

    # 测试 POST 固件上传
    log("测试固件上传 (POST /upload)...")
    try:
        fw_data = b"\x00\xFF" * 512 + b"FIRMWARE_DATA" * 100
        req = urllib.request.Request("http://localhost:8880/upload",
                                      data=fw_data,
                                      headers={"Content-Type": "application/octet-stream",
                                               "Content-Length": str(len(fw_data))})
        resp = urllib.request.urlopen(req, timeout=15)
        result = resp.read().decode("utf-8")
        if "成功" in result or "升级" in result:
            log("固件上传测试 [PASS]")
        else:
            log(f"固件上传测试 [WARN] - 响应: {result[:300]}")
    except urllib.error.HTTPError as e:
        err_body = e.read().decode('utf-8', errors='replace')[:300]
        log(f"固件上传 HTTP {e.code}: {err_body}")
    except Exception as e:
        log(f"固件上传测试 [FAIL] - {e}")

    # 打印 QEMU 控制台 httpd 相关输出
    import io
    child.sendline("\x03")
    time.sleep(1)
    try:
        child.expect(r"=>", timeout=5)
        remaining = child.before
        for line in remaining.split('\n'):
            if 'httpd' in line.lower() or 'flash' in line.lower() or '写入' in line:
                log(f"  [QEMU] {line.strip()}")
    except:
        pass

    # 停止 httpd
    log("停止 httpd...")
    child.sendline("\x03")  # Ctrl+C
    time.sleep(2)

    log("=== 测试完成 ===")
    child.sendline("reset")
    child.close()
    return 0

if __name__ == "__main__":
    sys.exit(main())

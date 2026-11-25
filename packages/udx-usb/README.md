# UDX USB 管理包（`udx-usb`）

`udx-usb` 在 `29100000.usb`（USB1）上提供 CDC-NCM 网络管理接口与可选的受认证 ACM 串口终端：
- 主系统默认启用 **PAM U3 硬件加速模式（`ncm`）**，支持切换至软件处理模式（`ncm-software`）用于对比诊断；
- 独立 Recovery 默认使用软件模式（`ncm-software`）；
- 包含 Microsoft OS 1.0 `WINNCM` 兼容描述符，支持 Windows 11、macOS 与 Linux 免驱枚举。

## 组件与文件结构

- `/etc/config/udx-usb`：UCI 配置文件（启用状态、工作模式、可选 ACM 控制台及持久身份覆盖）。
- `/etc/init.d/udx-usb`：`procd` 服务入口，负责启动时配置 configfs Gadget 并托管 ACM `agetty` 进程。
- `/usr/sbin/udx-usbctl`：本地维护命令行工具，支持查询状态与切换 USB 模式。
- `/usr/libexec/udx-usb-gadget`：configfs Gadget 事务脚本。
- `/usr/libexec/udx-usb-ready`：调用 `udx-boot-state management-ready` 的当前管理链路检查；启动确认使用同一实现。gadget 绑定不等待 logd/DHCP，状态不读取早期超时缓存。
- `/usr/libexec/udx-usb-console` / `udx-usb-login`：ACM 串口 `agetty` 包装与密码认证登录入口（要求系统已设置非空 `root` 密码）。
- `/etc/uci-defaults/90-udx-usb`：初始化 `usbmgmt`（`br-usb`，默认 `192.168.66.1/24`）网桥、DHCP 与防火墙规则。

## 模式与设备身份派生

| 模式（Profile） | PID（无 ACM） | PID（启用 ACM） | 接口分配 | 网络设备名 |
|---|---|---|---|---|
| `ncm` | `0x0105` | `0x0115` | 接口 0/1：CDC-NCM（PAM U3 硬件卸载） | `uncm0` |
| `ncm-software` | `0x0105` | `0x0115` | 接口 0/1：CDC-NCM（内核软件数据通路） | `uncm0` |
| `rndis` | `0x0106` | `0x0116` | 接口 0/1：RNDIS（`ef/04/01`，MS 描述符 `RNDIS`/`5162001`） | `uncm0` |
| `ecm` | `0x0107` | `0x0117` | 接口 0/1：CDC-ECM（无 MS 描述符） | `uncm0` |
| `eem` | `0x0108` | `0x0118` | 单接口：CDC-EEM（`02/0e`，无功能描述符） | `uncm0` |

所有模式统一使用 `uncm0` 作为网络设备名，切换模式不会改变 `br-usb` 的成员，因此 DHCP、防火墙与路由配置无需随之调整。

### 模式选择建议

| 主机 | 推荐模式 | 说明 |
|---|---|---|
| Android 8+ 手机 / 车机 | `rndis` | Android 的 USB 共享网络本身基于 RNDIS，`rndis_host` 属标配驱动，插上即用 |
| Windows 10/11 | `ncm` | 原生 `UsbNcm.sys`，并支持 PAM U3 硬件卸载 |
| Windows 7/8 | `rndis` | 系统自带 `usb8023`/`rndismpx` |
| Linux / macOS | `ncm` 或 `ecm` | 均为内核原生类驱动，无需安装 |
| 主机拒绝 ECM/NCM 枚举 | `eem` | 无 CDC 功能描述符，Android/Linux 均内置 `cdc_eem`，作为兜底模式 |
| 需要旁路调试通道 | 任意模式 + `acm` | 额外暴露 `/dev/ttyGS0` ↔ 主机 `/dev/ttyACM0` |

若配置的模式在启动时无法实例化（内核缺对应 gadget 功能或描述符写入失败），`udx-usb-gadget start` 会自动回退到 `ncm` 并把该回退写回 UCI，保证设备不会因为一个不可用的模式而失去管理链路。

启用 ACM 时，接口 2/3 追加 CDC-ACM 串口（`/dev/ttyGS0`）。设备描述符使用复合设备 IAD 类型 `ef/02/01`，并在 NCM 接口 0 上提供 `MSFT100`（Vendor Request `0xcd`、`WINNCM`）描述符。

### 自动身份派生（`auto`）
UCI 中的序列号与 MAC 字段默认为 `auto`，启动时根据原生 U-Boot 从原厂 `miscdata` 读取并传入内核命令行的 `androidboot.serialno` 确定性派生：
- 使用带域分离前缀（`udx710-usb-serial-v1\0` 与 `udx710-usb-mac-v1\0`）的 SHA-256 摘要；
- USB 序列号格式为 `udx710-<16位十六进制摘要>`；
- 设备端与主机端 MAC 取摘要前 6 字节并设置为本地管理单播地址（最低两位分别标识 device 与 host）；
- 若未读取到有效出厂序列号，则回退至诊断默认值 `sy108-usb` / `02:71:04:10:00:01` / `02:71:04:10:00:02`。

## 维护命令

```sh
# 查看当前控制器状态、速率与激活配置
udx-usbctl status

# 切换硬件/软件 NCM 模式（保存配置并触发系统正常重启生效）
udx-usbctl switch ncm no-acm
udx-usbctl switch ncm-software no-acm

# 在同一 NCM 模式下动态启停受密码保护的 ACM 串口终端
udx-usbctl switch ncm acm
udx-usbctl switch ncm no-acm
```

- 在 `ncm`（PAM 硬件加速）与 `ncm-software` 之间切换需重启系统生效；
- 同一数据模式内启停 ACM 会直接在当前系统内重绑 configfs Gadget。

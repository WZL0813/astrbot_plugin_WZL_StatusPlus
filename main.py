import asyncio
import platform
import psutil
import datetime
import os
from typing import Tuple, Optional

from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register

def get_disk_root() -> str:
    """智能获取磁盘根路径（兼容Windows/Linux）"""
    return 'C:\\' if platform.system() == 'Windows' else '/'

def format_units(num: float, precision: int = 2) -> str:
    """智能单位转换（自动适配B/KB/MB/GB/TB）"""
    units = ['B', 'KB', 'MB', 'GB', 'TB']
    unit_index = 0
    while num >= 1024 and unit_index < 4:
        num /= 1024
        unit_index += 1
    return f"{num:.{precision}f} {units[unit_index]}"

@register("astrbot_plugin_WZL_StatusPlus",
         "WZL",
         "状态监控插件", 
         "1.0.0", 
         "https://github.com/WZL0813/astrbot_plugin_WZL_StatusPlus")
class ServerStatusMonitor(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self._prev_net = None  # 网络IO历史数据
        self._prev_ts = None   # 上次时间戳

    def _get_uptime(self) -> str:
        """计算系统运行时间"""
        delta = datetime.datetime.now() - datetime.datetime.fromtimestamp(psutil.boot_time())
        days, seconds = delta.days, delta.seconds
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        return f"{days}天{hours}时{minutes}分"

    def _get_load_avg(self) -> Optional[str]:
        """获取系统负载（Windows返回空值）"""
        try:
            load = os.getloadavg()
            return f"{load[0]:.2f}/{load[1]:.2f}/{load[2]:.2f}"
        except AttributeError:
            return None

    def _calc_network_speed(self) -> Tuple[str, str]:
        """计算实时网络速率（需两次调用间隔）"""
        current = psutil.net_io_counters()
        now = datetime.datetime.now().timestamp()
        
        upload = "0.00 KB/s"
        download = "0.00 KB/s"
        
        if self._prev_net and self._prev_ts:
            time_diff = now - self._prev_ts
            upload = current.bytes_sent - self._prev_net.bytes_sent
            download = current.bytes_recv - self._prev_net.bytes_recv
            
            upload = f"{upload / time_diff / 1024:.2f} KB/s" if upload < 1048576 else f"{upload / time_diff / 1048576:.2f} MB/s"
            download = f"{download / time_diff / 1024:.2f} KB/s" if download < 1048576 else f"{download / time_diff / 1048576:.2f} MB/s"

        self._prev_net = current
        self._prev_ts = now
        return (upload, download)

    @filter.command("状态查询", alias=["status", "sysinfo"])
    async def query_status(self, event: AstrMessageEvent):
        '''触发服务器状态检查（支持异步并发采集）'''
        try:
            # 异步并发获取核心数据
            cpu_percent, mem_info, disk_info, processes = await asyncio.gather(
                asyncio.to_thread(psutil.cpu_percent, interval=1),
                asyncio.to_thread(psutil.virtual_memory),
                asyncio.to_thread(psutil.disk_usage, get_disk_root()),
                asyncio.to_thread(psutil.process_iter)
            )

            # 获取附加指标
            load_avg = self._get_load_avg()
            upload_speed, download_speed = self._calc_network_speed()
            cpu_cores = psutil.cpu_count(logical=False)
            net_conns = len(psutil.net_connections())

            # 构建状态报告
            status_report = [
                "🔍 状态监控",
                "======================",
                f"▪ 运行时长 : {self._get_uptime()}",
                f"▪ 系统负载 : {load_avg or 'N/A'} (1/5/15min)" if load_avg else "",
                f"▪ CPU使用  : {cpu_cores}核 {cpu_percent}%",
                f"▪ 内存状态 : {mem_info.percent}% ({format_units(mem_info.used)}/{format_units(mem_info.total)})",
                f"▪ 磁盘使用 : {disk_info.percent}% ({format_units(disk_info.used)}/{format_units(disk_info.total)})",
                f"▪ 网络速率 : ↑{upload_speed}  ↓{download_speed}",
                f"▪ 进程状态 : {len(list(processes))}运行中 | {net_conns}连接数",
                f"▪ 系统版本 : {platform.system()} {platform.release()}",
                f"🕒 报告时间 : {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                "======================"
            ]

            # 过滤空行并发送结果
            yield event.plain_result('\n'.join([line for line in status_report if line]))

        except psutil.AccessDenied:
            yield event.plain_result("⛔ 权限不足，请以重现尝试！")
        except Exception as e:
            yield event.plain_result(f"❗ 监控异常：{str(e)}")
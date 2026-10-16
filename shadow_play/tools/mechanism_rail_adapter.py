"""Rail interface deliberately unconfigured until the real driver is identified.

Simulation uses an explicitly established local position, never board feedback.
"""
import math

class RailUnavailable(RuntimeError):pass

class UnconfiguredRailDriver:
    ready=False
    reason='尚未接入丝杆驱动：请提供驱动器型号、接线/协议和限位方式。'
    def move_relative(self,*args,**kwargs):raise RailUnavailable(self.reason)
    def home(self,*args,**kwargs):raise RailUnavailable('未配置回零接口；不会向端点试撞回零。')
    def stop(self):return dict(confirmed=False,reason='无已连接丝杆驱动，未发送停止指令')

def finite_number(value,name):
    if isinstance(value,bool):raise ValueError(name+'须为有限数字')
    value=float(value)
    if not math.isfinite(value):raise ValueError(name+'须为有限数字')
    return value

def simulated_relative(position,delta,minimum,maximum):
    if position is None:raise ValueError('先录入位置或建立零点；未知位置不能累计移动')
    position=finite_number(position,'位置');delta=finite_number(delta,'位移')
    minimum=finite_number(minimum,'最小位置');maximum=finite_number(maximum,'最大位置')
    if minimum>=maximum:raise ValueError('行程下限必须小于上限')
    target=position+delta
    if not minimum<=position<=maximum or not minimum<=target<=maximum:
        raise ValueError('超出手动设定的丝杆行程')
    return target

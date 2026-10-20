"""角色卡刷新 (把 Character 的数值填进已建好的控件)。

原 700 行的单文件已按区域拆开:
    ui/refresh.py    —— RefreshMixin: 整卡刷新 (英雄区/HP/属性/技能/法术位/装备/专长)
    ui/classtab.py   —— ClassTabMixin: 职业页 (资源池/超魔法/术法源泉/荒野变形/子职/特性)
    ui/featpanel.py  —— FeatPanelMixin: 专长页与状态栏
本模块保留原名与位置, 因为 app.py 从这里取 AppSheet。
"""
from .ui.classtab import ClassTabMixin
from .ui.featpanel import FeatPanelMixin
from .ui.refresh import RefreshMixin


class AppSheet(RefreshMixin, ClassTabMixin, FeatPanelMixin):
    """原来的方法已按模块拆到其它文件, 这里只做组合。"""

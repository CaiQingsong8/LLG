# # 不用 Counter，手写统计列表中每个元素出现次数
#
# lst = [1, 2, 3, 1, 2, 1]
# # 输出：{1: 3, 2: 2, 3: 1}
# print(dict(zip(lst, [1]*len(lst))))
# result={}
# for x in lst:
#     result[x]=result.get(x,0)+1
# print(result)
from mpmath.libmp.libintmath import ifac2

# 把两个列表合并成字典
# keys = ["host", "port", "db"]
# vals = ["localhost", 8123, "default"]
# # 输出：{"host": "localhost", "port": 8123, "db": "default"}
# result = dict(zip(keys, vals))
# print(result)





# rows = [
#     {"client.py": "华为", "profit": 300, "cost": 800},
#     {"client.py": "比亚迪", "profit": 400, "cost": 1000},
#     {"client.py": "腾讯", "profit": 500, "cost": 1200},
# ]
# result= [r for r in rows if r["profit"] /r["cost"]> 0.3]
# print(result[0].values())
# print([r["client.py"] for r in result])
# # ['华为', '比亚迪', '腾讯']
#
# g = (r["profit"] for r in result)
# print(g)        # 地址：<generator object ...>
# print(list(g))  # 值：[300, 400, 500]
# print(list(g))  # 值：[300, 400, 500]


# # 把字典列表按 profit 从高到低排序
# rows = [
#     {"client.py": "华为",   "profit": 300},
#     {"client.py": "腾讯",   "profit": 500},
#     {"client.py": "比亚迪", "profit": 400},
# ]
# # 输出：[腾讯, 比亚迪, 华为]
# print([r["client.py"] for r in rows if r["profit"]>300])

# 统计下面列表中每个dept出现次数
# lst = ["华南区","华北区","华南区","华东区","华北区","华南区"]
# result = {}
# for x in lst:
#     result[x] = result.get(x, 0) + 1
# print(result)
# # {"华南区": 3, "华北区": 2, "华东区": 1}
#
# for y in result:
#     result[y] =result.get(y,0)+2
# print(result)
import numpy as np
import sys
from db import ckread
from tabulate import tabulate
sql_multi = """
SELECT 
    month_dt,
    SUM(f_sale_num) AS total_qty
FROM alphafeed.dwd_so_saleorder
WHERE client_class_flag = '0'
  AND month_dt BETWEEN '2025-01' AND '2026-01'
GROUP BY month_dt
ORDER BY month_dt
"""

rows_multi = ckread.query(sql_multi).result_rows
months = [row[0] for row in rows_multi]
qtys   = np.array([float(row[1]) for row in rows_multi])

# 环比：当月 vs 上月
mom = np.diff(qtys) / qtys[:-1] * 100

# 同比：当月 vs 去年同月（间隔12个月）
yoy = (qtys[12:] - qtys[:-12]) / qtys[:-12] * 100

print(f"{'#'*20}每月销量{'#'*20}\n月份        环比%")
for i in range(1, len(months)):
    print(f"{months[i]}  {mom[i-1]:+.1f}%")

print("\n月份        同比%")
for i in range(12, len(months)):
    print(f"{months[i]}  {yoy[i-12]:+.1f}%")


# 环比表格
mom_table = [[months[i], f"{mom[i-1]:+.1f}%"] for i in range(1, len(months))]
print(tabulate(mom_table, headers=["月份", "环比%"], tablefmt="grid"))

# 同比表格
yoy_table = [[months[i], f"{yoy[i-12]:+.1f}%"] for i in range(12, len(months))]
print(tabulate(yoy_table, headers=["月份", "同比%"], tablefmt="grid"))
# sql = """
# SELECT d_client_name,client_class_flag, SUM(f_sale_num) AS total_qty
# FROM alphafeed.dwd_so_saleorder
# WHERE month_dt = '2026-01'
# GROUP BY d_client_name,client_class_flag
# ORDER BY total_qty DESC
# """
#
# rows = ckread.query(sql).result_rows
# rows = [row for row in rows if row[1] == '0']
# names = [row[0] for row in rows]
# qtys  = np.array([float(row[2]) for row in rows])  # row[2] 才是销量
#
#
#
# print(f"总销量：{qtys.sum():.0f}")
# print(f"均值：{qtys.mean():.0f}")
# print(f"最大：{qtys.max():.0f}")
# print(f"标准差：{qtys.std():.0f}")
#
# # 找出高于均值的客户
# mean = qtys.mean()
# above = [(names[i], qtys[i]) for i in range(len(qtys)) if qtys[i] > mean]
# print(f"\n高于均值的客户（共{len(above)}个）：")
# for name, qty in above[:5]:
#     print(f"  {name} - {qty:.0f}")
#
# total = qtys.sum()
# top_n = max(1, int(len(qtys) * 0.2))
# top_pct = qtys[:top_n].sum() / total * 100
# cumsum = np.cumsum(qtys) / total * 100
# threshold = np.searchsorted(cumsum, 80)
#
# print(f"\n前20%客户（{top_n}个）贡献占比：{top_pct:.1f}%")
# print(f"累计80%销量需要前 {threshold+1} 个客户")
# print(f"总客户数：{len(qtys)}")
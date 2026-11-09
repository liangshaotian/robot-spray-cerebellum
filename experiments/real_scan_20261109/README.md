# 真实扫描异形件：11月9日实验记录

正式汇报见 [11.16组会汇报](../../docs/EXPERIMENT_20261116.md)。

- `results.json`：固定三维轨迹细网格复核的主结果与适用范围。
- `fixed_path_evaluation.npz`：目标、边缘、曲面面积权重与基准/搜索沉积数组；不包含原始XYZ/RGB和重建高度。
- `comparison.csv`：主结果表。
- `search_path_workpiece.csv`：345个规划点及表面法向、TCP、速度和喷涂段标记。坐标为本次曲面局部坐标，单位尚待确认；不是机器人底座坐标，不能直接用于实机。
- `data_quality.json`：同一工件、多角度扫描及未解析文件的统计范围。
- `synthetic_transfer_summary.json`：18类54个合成曲面的补充测试摘要，与真实扫描实验分开统计。

```bash
python tools/verify_real_scan_search.py
```

该命令仅复核保存结果。原始企业点云未上传；完整三维重建与搜索重跑需要原始数据、环境及相应研究代码，当前仓库不宣称已有任意新工件的全自动流水线。

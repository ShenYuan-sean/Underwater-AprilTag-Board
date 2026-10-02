# 水库 AprilTag 定位板（两批共 40 块）

本工程管理两批共 40 块独立的 `300 mm × 300 mm` 水库定位板。参考原六面标定板，每块板使用“一个中央大 Tag + 八个外围小 Tag”的 AprilTag 36h11 九宫格布局。共使用唯一 ID `100–459`，避免与 `Underwater-AprilTag-Board` 中已有的 `0–53` 冲突。

| 批次 | 板号 | Tag ID | 文件位置 |
|---|---|---|---|
| 第一批（已加工） | R01–R20 | 100–279 | `generated/`、`加工厂复核/` |
| 第二批（本次新增） | R21–R40 | 280–459 | `batch_02/generated/`、`batch_02/output/pdf/` |

## 推荐方案

| 项目 | 参数 |
|---|---:|
| 板材外形 | 300 mm × 300 mm |
| 每板 Tag 数量 | 9 |
| Tag 家族 | AprilTag 36h11 |
| ID | 100–459（两批合计） |
| 中央黑色码区 | 128 mm × 128 mm |
| 外围黑色码区 | 44 mm × 44 mm |
| 中央/小 Tag 单元格 | 16 mm / 5.5 mm |
| 中央/小 Tag quiet zone | 10 mm / 8 mm |
| 安装孔 | 4 × 直径 5.2 mm（M5 间隙孔） |
| 孔位 | 两列 `x=96/204 mm`，两行 `y=44/256 mm` |

以板左下角为工程坐标原点，四个孔心为：

- `(96, 44) mm`
- `(204, 44) mm`
- `(96, 256) mm`
- `(204, 256) mm`

中央 Tag 黑色码区位于 `x=86–214 mm, y=86–214 mm`，其 quiet zone 为 `x=76–224 mm, y=76–224 mm`。外围 Tag 位于中心坐标为 `44、150、256 mm` 的九宫格位置，跳过中央位置；每个小 Tag 的 quiet zone 外形为 `60 mm × 60 mm`。孔位落在外围 Tag 之间的空隙中，不侵入任何 quiet zone。

每块板的 ID 按下面方式连续分配：

```text
左上=base+1    上=base+2      右上=base+3
左=base+4      中央=base      右=base+5
左下=base+6    下=base+7      右下=base+8
```

例如 R01 使用 `100–108`，R20 使用 `271–279`，R21 使用 `280–288`，R40 使用 `451–459`。

## 为什么采用一大八小

中央 `128 mm` Tag 是主地标，承担相对较远距离的发现和位姿估计。八个 `44 mm` 小 Tag 用于：

- 相机经常靠得非常近，主 Tag 不能完整进入画面；
- 标定板经常被局部遮挡；
- 只看到板的一角或一条边时仍能识别板号；
- 近距离时提供更多独立角点和检测冗余。

该布局是原 150 mm 六面板方案的两倍尺度版本：中央 `64→128 mm`、外围 `22→44 mm`、外围中心距板边 `22→44 mm`。因此可以沿用原工程的 ID 顺序和检测逻辑。

## 输出文件

第一批的 `generated/` 包含：

- `board_01_ids_100-108.svg` 到 `board_20_ids_271-279.svg`：用于印刷的干净 SVG；
- `board_XX_ids_XXX-XXX_guide.svg`：包含 quiet zone、Tag 边界、ID 和钻孔位置的检查图；
- 对应的 `.dxf`：包含切割、钻孔和黑色单元格加工图层；
- `all_boards_sheet.svg/.dxf`：20 块板的 4 × 5 拼版；
- `board_drill_template.svg/.dxf`：所有板共用的钻孔模板；
- `id_map.csv`：板号与 Tag ID 对照表；
- `deployment_survey_template.csv`：部署位置和姿态测量记录模板；
- `manifest.txt`：生产尺寸摘要。
- `output/pdf/reservoir_apriltag_20_board_reference.pdf`：20 页 DXF 图案和孔位对照册。

第二批的 `batch_02/generated/` 使用相同结构，文件名从 `board_21_ids_280-288` 到 `board_40_ids_451-459`。加工厂交付目录位于 `batch_02/manufacturing/`，可直接发送的压缩包为 `batch_02/reservoir_apriltag_boards_21-40_manufacturing.zip`，参考对照册为 `batch_02/output/pdf/reservoir_apriltag_boards_21-40_reference.pdf`。

干净 SVG 不画钻孔辅助圆，避免钻孔标记混入印刷图案；钻孔位置在 guide SVG 和所有 DXF 文件中给出。
每块板正面左下边缘只印中央大 Tag 的可读编号，例如第一块为 `ID = 100`；不再印 `R01–R20` 板号。该文字位于外围 Tag 的 quiet zone 之外。
生产 DXF 中的 `ID = 100` 已转换成普通 `LINE` 轮廓，不依赖 DXF `TEXT` 实体，因此 Fusion 360 插入草图时也能显示。

## 环境

本机已有 `rss_depth` Conda 环境满足要求：

- Python 3.10.19
- OpenCV 4.13.0
- `cv2.aruco.ArucoDetector`

直接运行：

```powershell
conda run -n rss_depth python generate_reservoir_boards.py
conda run -n rss_depth python verify_reservoir_boards.py --no-debug
conda run -n rss_depth python generate_reference_pdf.py
```

生成并验证第二批 R21–R40：

```powershell
conda run -n rss_depth python generate_reservoir_boards.py `
  --out batch_02/generated `
  --board-count 20 `
  --board-number-start 21 `
  --start-id 280

conda run -n rss_depth python verify_reservoir_boards.py `
  --input-dir batch_02/generated `
  --no-debug

conda run -n rss_depth python generate_reference_pdf.py `
  --out batch_02/output/pdf/reservoir_apriltag_boards_21-40_reference.pdf `
  --board-count 20 `
  --board-number-start 21 `
  --start-id 280
```

如果以后需要独立重建环境：

```powershell
conda env create -f environment.yml
conda run -n reservoir-apriltag-boards python generate_reservoir_boards.py
```

常用参数示例：

```powershell
conda run -n rss_depth python generate_reservoir_boards.py `
  --board-count 20 `
  --board-mm 300 `
  --center-tag-mm 128 `
  --small-tag-mm 44 `
  --center-quiet-mm 10 `
  --small-quiet-mm 8 `
  --small-center-mm 44 `
  --start-id 100 `
  --hole-dia-mm 5.2 `
  --hole-x-mm 96 `
  --hole-y-mm 44
```

## 制作要求

1. 必须按 `100%` 实际尺寸输出，关闭“适合页面”或自动缩放。
2. 成品上实测中央/小黑色码区应为 `128 mm` 和 `44 mm`；建议中央尺寸误差控制在 `±0.5 mm` 内。
3. quiet zone 内不能出现孔、螺栓、接缝、文字、污渍或颜色突变。
4. 黑白表面优先使用哑光工艺，避免水下照明形成强反光。
5. 推荐 3–5 mm 5052 铝板、铝塑板或足够刚性的耐水板材；薄板背面应加支撑，避免弯曲造成位姿误差。
6. 图案可采用耐浸水 UV 印刷、丝印或黑白双组分环氧涂层。正式批量制作前先做一块浸泡和擦洗测试。
7. M5 螺栓建议配大垫片和防松结构；异种金属接触处应做电化学腐蚀隔离。
8. 板角建议倒圆，但最终外形变更不能侵入孔边或 quiet zone。

## 部署要求

Tag ID 只能告诉程序“看到了哪块板”。要让它成为水库世界坐标系中的定位地标，还必须测量并记录：

- Tag 中心的水库坐标 `X/Y/Z`；
- 板面朝向，至少记录 yaw/pitch/roll 或板面法向量；
- 箭头所指方向；
- 安装位置照片和附近固定参照物；
- 安装日期、紧固状态和后续污损情况。

建议所有竖直安装的板保持箭头朝上。位姿估计时必须根据 ID 使用正确尺寸：每板第一个 ID 对应中央 `128 mm` Tag，其余八个 ID 对应 `44 mm` Tag，不能把 300 mm 板外形当成 Tag 尺寸。

粗略识别距离可以用下面的投影关系估算：

```text
中央 Tag 像素宽度 ≈ 相机焦距(px) × 0.128(m) / 距离(m)
小 Tag 像素宽度   ≈ 相机焦距(px) × 0.044(m) / 距离(m)
```

水下正式部署前，应使用实际相机、舱体玻璃、灯光和目标水体，在计划的最远距离验证检测成功率。建议让 Tag 在图像中至少保持约 60–80 像素宽，复杂浑水环境应留更大余量。

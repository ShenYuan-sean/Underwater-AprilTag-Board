# 6-Face AprilTag 36h11 Calibration Board

这个项目用于生成 6 块 150 mm x 150 mm 标定板，每块板使用 AprilTag `36h11` 家族，所有 Tag ID 唯一。默认布局是每面 1 个中央大 Tag + 8 个外围小 Tag，适合做六边形水平全向标定板。

## 默认方案

- 每块板尺寸：150 mm x 150 mm
- 每面 Tag 数：9
- 中央大 Tag：64 mm 黑色码区，单元格约 8 mm
- 外围小 Tag：22 mm 黑色码区，单元格约 2.75 mm
- 每面 ID：
  - Face 1: 0-8
  - Face 2: 9-17
  - Face 3: 18-26
  - Face 4: 27-35
  - Face 5: 36-44
  - Face 6: 45-53

中央大 Tag 用来保证中远距离、斜视角和运动模糊下仍能稳定识别；外围小 Tag 用来在近距离、局部遮挡、多面同时入镜时增加可见角点数量。默认不在板面上放安装孔，建议用背面、边缘压条或插槽夹持，避免破坏 Tag 的白色 quiet zone。

## 文件

- `generate_apriltag_boards.py`: 生成 SVG/DXF 的 Python 脚本
- `environment.yml`: 可复现环境配置
- `generated/face_01.svg` 到 `generated/face_06.svg`: 单面干净 SVG
- `generated/face_01_guide.svg` 到 `generated/face_06_guide.svg`: 带 ID 和 quiet zone 辅助线的 SVG
- `generated/face_01.dxf` 到 `generated/face_06.dxf`: 单面干净 DXF，默认只含加工常用图层和板面文字
- `generated/face_01_guide.dxf` 到 `generated/face_06_guide.dxf`: 带 Tag 边界、quiet zone 和辅助 ID 的 DXF
- `generated/all_faces_sheet.svg`: 六面拼版 SVG
- `generated/all_faces_sheet.dxf`: 六面拼版 DXF
- `generated/all_faces_sheet_guide.dxf`: 六面拼版辅助 DXF
- `generated/hex_fixture_top_view.dxf`: 六边形夹具顶视参考 DXF
- `generated/manifest.txt`: 尺寸、ID 和 DXF 图层说明

## 生成命令

本机 Miniconda 没有加入 PATH，所以可以直接用完整路径调用项目内环境：

```powershell
C:\Users\ASUS\Documents\WS\4.Underwater_Robot\水下标定板\.conda\apriltag-board\python.exe generate_apriltag_boards.py
```

如果要从 `environment.yml` 重建环境：

```powershell
C:\Users\ASUS\miniconda3\Scripts\conda.exe env create -f environment.yml
```

或者创建到项目内：

```powershell
C:\Users\ASUS\miniconda3\Scripts\conda.exe env create --prefix .\.conda\apriltag-board -f environment.yml
```

## 可调参数

```powershell
.\.conda\apriltag-board\python.exe generate_apriltag_boards.py --center-tag-mm 64 --small-tag-mm 22 --start-id 0
```

如果你希望远距离识别更强，可以把外围小 Tag 减少，或把中央 Tag 改到 72-90 mm；如果主要是近距离标定，可以保留 9 Tag 布局。当前默认方案是两者之间的折中。

## ID 校验

用 OpenCV 重新检测每块板的 SVG，确认 AprilTag 36h11 的 ID 没有生成错：

```powershell
.\.conda\apriltag-board\python.exe verify_apriltag_boards.py
```

脚本会检查 `generated/face_01.svg` 到 `generated/face_06.svg`，并在 `generated/verification_debug/` 里输出带检测框的 PNG。

## DXF 图层

- `CUT`: 150 mm 板外框
- `MOUNT_HOLE`: 4 个安装孔，默认孔径 3.4 mm，孔心为 `(48,22)`, `(102,22)`, `(48,128)`, `(102,128)`
- `BLACK_POCKET`: 每个黑色单元格的轮廓线，适合 CNC/激光做填黑或雕刻区域
- `BOARD_TEXT`: 实际可印/可刻的板号、ID 范围和左右相邻面提示；普通 DXF 中这些文字已经转成线段字，不依赖 CAD 的 `TEXT` 实体
- `ORIENTATION`: 顶边方向箭头
- `BLACK_FILL_PREVIEW`: 可选黑块预览填充层，默认不输出
- `TAG_BOUNDARY`: Tag 黑色码区边界，只在 `*_guide.dxf`
- `QUIET_ZONE`: 推荐留白区域，只在 `*_guide.dxf`
- `LABEL`: 面编号和 ID 辅助标注，只在 `*_guide.dxf`

实际加工时，建议使用 `CUT`、`BLACK_POCKET`、`BOARD_TEXT` 和 `ORIENTATION`。默认 DXF 已改成 AutoCAD R12 ASCII，普通加工版只用 `LINE` 实体来画板框、黑块、箭头和板面提示文字，兼容性比上一版更好。

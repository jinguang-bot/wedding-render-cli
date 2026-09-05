# 布局 JSON Schema（单一事实源）

布局文件位于 `<workspace>/layouts/wedding.vN.json`。所有渲染与照片级化都从它派生；
改方案 = 改这个文件。坐标：原点在礼堂中心，Y 轴指向海（晚宴方向）为正，单位米。

```jsonc
{
  "version": "v1",
  "time": "day | dusk | night",          // 时段：影响光照与生图氛围模板
  "source_images": ["参考图路径..."],      // compose_layout 生成时的来源，可追溯
  "venue": {
    "chapel": { "length": 12, "width": 8, "wall_h": 5 }   // 礼堂体量（8-16 / 5-12 / 3-7）
  },
  "ceremony": {
    "arch": {
      "pos": [0, -3, 0],                  // 拱门位置（Z 恒为 0）
      "width": 3.0,                       // 1.5-5
      "height": 2.6,                      // 2.0-3.5（尺度标定：现实拱门高 2.2-3m）
      "palette": "white_cloth"            // white_cloth | greenery | petal
    },
    "aisle": { "rows": 4, "seats_per_row": 6, "aisle_w": 1.8 },  // 0-10 / 0-14 / 1.2-3.0
    "sign_in": { "pos": [-6, 5] }         // 可选：签到台位置
  },
  "dinner": {                             // 图中/需求中无晚宴则整个省略
    "pos_y": 26,                          // 14-40，晚宴区在草坪海侧的距离
    "long_tables": 2,                     // 0-6
    "table_spacing": 3.0,                 // 1.5-6
    "chairs_per_side": 8,                 // 4-15
    "string_lights": { "height": 3.2 },   // 可选：灯串（2.2-4.5）
    "dessert": { "pos": [9, 23] }         // 可选：甜品台
  },
  "cameras": ["ceremony_front", "ceremony_side45", "ceremony_doorview",
               "dinner_wide", "dinner_guest", "dinner_night"]   // 机位子集
}
```

## 机位说明
| 机位 | 视角 |
|---|---|
| ceremony_front | 礼堂内望向拱门的正面仪式视角 |
| ceremony_side45 | 仪式区 45° 侧视角 |
| ceremony_doorview | 从礼堂门洞向外（海景）视角 |
| dinner_wide | 晚宴区大全景 |
| dinner_guest | 宾客入座视角（低机位） |
| dinner_night | 夜景灯串氛围视角 |

## 常见改法速查
- 「座椅太多」→ ceremony.aisle.rows / seats_per_row 减小
- 「拱门再大气点」→ arch.width / height 增大（不超过钳制上限）
- 「换黄昏」→ time: "dusk"
- 「加灯串/甜品台」→ dinner 下补 string_lights / dessert
- 「晚宴离海近点」→ dinner.pos_y 增大

改完务必 `--quick` 重渲并在 preview.html 上确认。数值超出范围的修改会被 compose_layout 的
sanitize 钳回（范围见上），手工编辑时同样遵守。

## venue.chapel 精确建模字段（v3 起）

```jsonc
"venue": { "chapel": {
  "length": 15.0,   // 纵深 8-16
  "width": 8.2,     // 内宽 5-12
  "wall_h": 4.6,    // 侧墙高 3-7
  "roof_rise": 2.0, // 双坡屋顶脊升高
  "beams": 6,       // 露明横梁数
  "windows": { "count": 6, "w": 1.3, "h": 2.9, "sill": 1.0 },  // 每侧拱窗
  "sea_opening": { "w": 4.5, "h": 3.2 },                        // 海侧大开口（玻璃）
  "entrance": { "door_w": 2.4, "door_h": 2.6,
                "side_win": { "w": 1.0, "h": 2.0, "sill": 1.0 } }
} }
```
坐标系：Y+ 海侧大开口，Y- 入口双开门+三角山花；两端山墙、坡顶斜板自动生成。
测量来源：5 张实拍交叉验证 + 渲染-照片几何自检两轮迭代（2026-08-25）。
新增机位：chapel_interior（内部对角全景）；内部机位默认 28mm 对齐实拍广角。

## venue.exterior 外部结构字段 & 布置开关（v4 起）

```jsonc
"venue": { "exterior": {
  "fence":  { "enabled": true, "height": 1.2, "offset": 7.0,   // 木栅栏：高/距海侧墙距离
              "side": 11.0, "gate_w": 2.4 },                    // 围合宽度/中央门洞
  "path":   { "enabled": true, "width": 2.4 },                  // 石板步道（大开口→栅栏门）
  "porch":  { "enabled": true, "depth": 2.0, "height": 3.1 },   // 海侧门廊雨棚
  "shrubs": { "enabled": true }                                 // 步道两侧灌木
} }
```

**布置元素显式开关**：`"ceremony": null` 与 `"dinner": null` 表示纯建筑骨架（v4 默认）。
要加布置时填入对应对象即可（字段同上文仪式区/晚宴区）。
新机位：`chapel_exterior`（外部斜侧看海侧立面+栅栏前院）。

## 复刻级礼堂（replica=true，v6 起 2026-08-25 五图实证）

`"chapel": {"replica": true, "length": 15, "width": 8.2, "wall_h": 4.6, "roof_rise": 2.0, "beams": 6}`
启用后整个礼堂切换为实证复刻结构（字段 length/width/wall_h/roof_rise/beams 仍生效）：

- 侧墙：深木墙裙(0.95m) + 通高玻璃 + 立柱(间距2.5m) + 弹簧梁 + 壁灯（隔柱）
- 坡顶：深木板条吊顶 + 挑檐0.6 + 脊梁 + **沿坡彩色玻璃条带**（两侧全长）
- 海侧尽头：通宽敞开口 7.2×2.5m（折叠玻璃门收两侧）+ 上方玻璃格 + **通宽深棂格玻璃三角**
- 入口端：中央双开深木门 + 门上横窗 + 两侧通高玻璃 + 对称棂格三角
- 山墙四拐角白色圆柱；脊下黑铁双环烛台吊灯
- 外部：木平台(11×4.5m，一步高差) + **尖顶木桩栅栏**（双横轨+密排尖桩，中段留门洞）+ 两翼灌木

复现三层：L1=layouts/wedding.v6.json（参数） L2=overlay.json（增量） L3=sessions/*.blend（100%保真）。
材质契约新增：wood_dark/wood_deck/column_white/iron_black/candle/stained_{green,red,blue,amber}。

## 海之恋婚礼堂（style="haizhilian"，v8 起 2026-09-05 尺寸图驱动）

`"chapel": {"style": "haizhilian", "length": 11, "width": 9, "wall_h": 3.9, "roof_rise": 2.2, "glass_top": 4.4, "beams": 5}`

用户提供的官方尺寸图规格（权威）：内部 9×11m（场地 14.5×16.3 含入口外区 5.3m）、
脊高 6.1（wall_h 3.9 + roof_rise 2.2）、玻璃顶 4.4、海侧开口 7×2.7（落地玻璃到地）、
吊灯 3.8（HZL["lamp_z"]）、海端室内台阶平台。
外观（航拍实证）：红棕双坡屋面 + 海侧坡中下段玻璃格阵（5×4）、入口端奶油山墙 + 深木
A 型饰边 + 石材门柱与耳房、白色圆柱。
外部（build_site_haizhilian）：木平台/尖桩栅栏+栅栏门/沙滩/海面、六角红顶凉亭、
风格化椰树（伞冠）、绿篱、入口步道。
新机位：hzl_aerial（航拍）、hzl_lawn（草坪海侧回望）。
材质新增：roof_red/stone_cream/trunk/frond。

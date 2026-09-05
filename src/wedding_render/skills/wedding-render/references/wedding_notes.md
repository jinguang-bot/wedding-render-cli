# 婚礼领域笔记（父级特化知识）

子技能 scene-skeleton 持有通用契约（scene_schema.md / semantic_palette.md）；
本文件只放**婚礼话术 → JSON 字段**的翻译对照与流程特化，改字段前先读子技能的 schema。

## 用户话术 → 布局字段速查

| 用户说 | 改哪里 |
|---|---|
| "座椅太多/宾客就20来人" | ceremony.aisle.rows ↓ / seats_per_row ↓（20位≈4排×6座） |
| "拱门再大气点/存在感强" | arch.width / arch.height ↑（钳制上限 5 / 3.5） |
| "换个时段/想要黄昏氛围" | time: "dusk"；要夜景灯串氛围则 "night" |
| "晚宴加一桌" | dinner.long_tables +1 |
| "灯串挂高点/矮点" | dinner.string_lights.height（2.2-4.5） |
| "晚宴离海近一点" | dinner.pos_y ↑ |
| "加签到台/甜品台" | ceremony.sign_in / dinner.dessert 补 pos |
| "礼堂图 / 晚宴图" | cameras 选 ceremony_* / dinner_* |

## 机位语义（婚礼交付常用组合）
- 给婚策看仪式：ceremony_front + ceremony_side45
- 展示晚宴氛围：dinner_wide + dinner_night（灯串在 night/dusk 才点亮出效果）
- 海景门户感：ceremony_doorview

## 流程特化约束
1. **布局确认是婚礼效果图满意的前提**：新人认可是硬闸门，骨架未认可不出正式图
2. 案例组合任务的 style_ref 登记进 layout JSON（ceremony/dinner 各自指向源案例），可追溯
3. 真花比例敏感（对比婚策时的核心差异项）：描述花艺时避免"仿真感"词汇，
   prompt 用"自然舒展、层次分明、实拍质感"
4. 用户偏好沉淀在 `<workspace>/assets/preferences.md`：风格/色系/必备/拒绝元素，
   review 评分时对照它判定 element_match

## 案例 index.csv 检索口径
打标列：区域/风格/主色系/花材特征/材质元素/时段/氛围标签/适合风格参考。
常见检索：白绿色系拱门、带灯串的晚宴图、黄昏氛围参考——用 csv 过滤
"适合风格参考=是" 再按列匹配。

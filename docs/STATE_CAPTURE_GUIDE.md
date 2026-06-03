# 状态截图采集指南

这份文档用于采集新流程的完整界面截图。第一阶段只采集完整截图，不裁模板、不调识别。

## 准备

在 PowerShell 里进入项目根目录：

```powershell
cd /d C:\path\to\czn_auto
$env:PYTHONPATH="src"
```

如果已经在项目根目录，只需要：

```powershell
$env:PYTHONPATH="src"
```

先确认状态目录映射：

```powershell
python -m commands.state_check --list-states
```

## 采集规则

每采集一个状态：

1. 手动把游戏切到目标界面。
2. 确保游戏窗口没有被遮挡。
3. 等界面动画基本稳定。
4. 执行对应采集命令。
5. 查看输出里的 `saved capture:` 路径。

第一次采集全部使用 `--no-detect`，因为模板规则还没有建立好。

## 按流程采集

### 1. 主界面

目标画面：能看到“模拟”入口。

```powershell
python -m commands.state_check --save-state main --no-detect
```

保存目录：

```text
templates/common/main/captures/
```

### 2. 模拟界面

目标画面：能看到“战斗训练”入口。

```powershell
python -m commands.state_check --save-state simulate --no-detect
```

保存目录：

```text
templates/simulate/captures/
```

### 3. 战斗训练界面

目标画面：能看到“成长 / 主战员 / 辅战员 / 潜能 / 记忆碎片 / 挑战”等页签。

```powershell
python -m commands.state_check --save-state battle_training --no-detect
```

保存目录：

```text
templates/simulate/battle_training/captures/
```

### 4. 记忆碎片界面

目标画面：刚进入“记忆碎片”页。

```powershell
python -m commands.state_check --save-state memory_fragment --no-detect
```

保存目录：

```text
templates/simulate/battle_training/memory/captures/
```

### 5. 记忆碎片列表底部

目标画面：右侧列表下拉到底，能看到“贪婪与执着”。

```powershell
python -m commands.state_check --save-state greed --no-detect
```

保存目录：

```text
templates/simulate/battle_training/memory/greed/captures/
```

### 6. 贪婪与执着详情界面

目标画面：进入“贪婪与执着”详情页，能看到“出击”按钮。

```powershell
python -m commands.state_check --save-state greed --no-detect
```

保存目录：

```text
templates/simulate/battle_training/memory/greed/captures/
```

这个状态和“记忆碎片列表底部”使用同一个流程目录。后续裁模板时用不同文件名区分，例如 `greed_title.jpg`、`greed_sortie_button.jpg`。

### 7. 贪婪与执着战斗中

目标画面：进入战斗后，能看到右上角自动战斗、齿轮或暂停区域。

```powershell
python -m commands.state_check --save-state greed_game --no-detect
```

保存目录：

```text
templates/simulate/battle_training/memory/greed/in_game/captures/
```

### 8. 战斗结算界面

目标画面：能看到结算确认按钮。

```powershell
python -m commands.state_check --save-state settlement --no-detect
```

保存目录：

```text
templates/common/battle/settlement/captures/
```

## 每个状态采多张

同一个状态建议采 2-3 张，尤其是有动画、粒子、按钮发光的界面：

```powershell
python -m commands.state_check --save-state greed --no-detect
python -m commands.state_check --save-state greed --no-detect
python -m commands.state_check --save-state greed --no-detect
```

后续从这些截图里挑最清晰、最稳定的一张裁模板。

## 采集完成后的下一步

从保存的 `*_raw.jpg` 里裁小模板，优先裁稳定元素：

```text
main_simulation_button.jpg
simulate_battle_training_button.jpg
battle_training_memory_tab.jpg
memory_fragment_title.jpg
greed_title.jpg
greed_sortie_button.jpg
auto_battle_button.jpg
settlement_confirm_button.jpg
```

模板建议放到对应目录：

```text
templates/common/main/main_simulation_button.jpg
templates/simulate/simulate_battle_training_button.jpg
templates/simulate/battle_training/battle_training_memory_tab.jpg
templates/simulate/battle_training/memory/memory_fragment_title.jpg
templates/simulate/battle_training/memory/greed/greed_title.jpg
templates/simulate/battle_training/memory/greed/greed_sortie_button.jpg
templates/simulate/battle_training/memory/greed/in_game/auto_battle_button.jpg
templates/common/battle/settlement/settlement_confirm_button.jpg
```

然后把这些模板路径写入：

```text
templates/state_manifest.json
```

识别规则参考：

```text
templates/state_manifest.example.json
```

## 测试一个状态能否识别

裁好模板并写入 `templates/state_manifest.json` 后，可以测试这个状态是否能被识别。

### 1. 测试当前游戏画面

先手动把游戏切到要测试的状态，例如“贪婪与执着详情界面”，然后运行：

```powershell
python -m commands.state_check --save-state greed
```

如果识别成功，输出会类似：

```text
fresh_state | greed | greed_title=0.914@(520,180) | greed_sortie_button=0.887@(3300,1960)
```

重点看第二段状态名是否是预期状态：

```text
fresh_state | greed | ...
```

如果输出是：

```text
fresh_state | unknown
```

说明当前 `state_manifest.json` 里的规则没有命中。

常见原因：

- `path` 指向的模板文件不存在或文件名写错。
- `roi` 没覆盖模板在当前截图里的位置。
- `threshold` 太高。
- 裁图包含动画、发光、背景变化，导致匹配不稳定。
- 模板太小或太普通，缺少可区分特征。

### 2. 测试已保存截图

也可以不用切游戏，直接拿之前保存的完整截图测试。

示例：

```powershell
python .\src\main.py --image .\templates\simulate\battle_training\memory\greed\captures\20260603_120000_raw.jpg
```

如果需要保存标注图：

```powershell
python .\src\main.py --image .\templates\simulate\battle_training\memory\greed\captures\20260603_120000_raw.jpg --out-dir .\debug_live
```

标注图会保存到：

```text
debug_live/
```

### 3. 调整 ROI 和阈值

如果识别不到，先不要马上重裁模板，优先调整 `state_manifest.json`：

```json
{
  "name": "greed_sortie_button",
  "path": "simulate/battle_training/memory/greed/greed_sortie_button.jpg",
  "roi": [0.65, 0.72, 0.98, 0.98],
  "threshold": 0.78
}
```

调试顺序建议：

1. 先把 `roi` 放大，确认搜索区域覆盖模板。
2. 把 `threshold` 从 `0.82` 临时降到 `0.78`。
3. 如果能识别，再逐步缩小 `roi`、提高 `threshold`。
4. 如果仍然识别不到，再重新裁更稳定的模板。

### 4. 一个状态多个模板

如果一个状态容易和别的界面混淆，用多个模板并设置 `mode: "all"`：

```json
{
  "label": "greed",
  "priority": 110,
  "mode": "all",
  "templates": [
    {
      "name": "greed_title",
      "path": "simulate/battle_training/memory/greed/greed_title.jpg",
      "roi": [0.00, 0.00, 0.45, 0.30],
      "threshold": 0.82
    },
    {
      "name": "greed_sortie_button",
      "path": "simulate/battle_training/memory/greed/greed_sortie_button.jpg",
      "roi": [0.70, 0.78, 0.98, 0.98],
      "threshold": 0.82
    }
  ]
}
```

这表示必须同时匹配到 `greed_title` 和 `greed_sortie_button`，才认为当前状态是 `greed`。

### 5. 多张截图和多模板的规则

`captures/` 目录只是原始采集素材，不会自动参与识别。

也就是说，即使这里有很多截图：

```text
templates/simulate/battle_training/memory/greed/captures/
```

程序也不会自动从里面挑一张来识别。真正参与识别的只有 `templates/state_manifest.json` 里明确写到 `path` 的模板文件。

例如下面这个规则只会使用一个模板：

```json
{
  "label": "greed",
  "priority": 110,
  "mode": "all",
  "templates": [
    {
      "name": "greed_title",
      "path": "simulate/battle_training/memory/greed/greed_title.jpg",
      "roi": [0.00, 0.00, 0.45, 0.30],
      "threshold": 0.82
    }
  ]
}
```

程序只会读取：

```text
templates/simulate/battle_training/memory/greed/greed_title.jpg
```

不会自动读取：

```text
templates/simulate/battle_training/memory/greed/captures/*.jpg
```

如果同一个状态有多个可选模板，希望任意一个命中就算识别成功，使用 `mode: "any"`：

```json
{
  "label": "greed",
  "priority": 110,
  "mode": "any",
  "templates": [
    {
      "name": "greed_title_v1",
      "path": "simulate/battle_training/memory/greed/greed_title_v1.jpg",
      "roi": [0.00, 0.00, 0.45, 0.30],
      "threshold": 0.82
    },
    {
      "name": "greed_title_v2",
      "path": "simulate/battle_training/memory/greed/greed_title_v2.jpg",
      "roi": [0.00, 0.00, 0.45, 0.30],
      "threshold": 0.82
    }
  ]
}
```

这个规则表示：

- `greed_title_v1` 命中，识别为 `greed`。
- `greed_title_v1` 失败，但 `greed_title_v2` 命中，也识别为 `greed`。
- 两个都失败，`greed` 状态识别失败。

如果希望一个状态必须同时满足多个条件，使用 `mode: "all"`：

```json
{
  "label": "greed",
  "priority": 110,
  "mode": "all",
  "templates": [
    {
      "name": "greed_title",
      "path": "simulate/battle_training/memory/greed/greed_title.jpg",
      "roi": [0.00, 0.00, 0.45, 0.30],
      "threshold": 0.82
    },
    {
      "name": "greed_sortie_button",
      "path": "simulate/battle_training/memory/greed/greed_sortie_button.jpg",
      "roi": [0.70, 0.78, 0.98, 0.98],
      "threshold": 0.82
    }
  ]
}
```

这个规则表示必须同时匹配到标题和“出击”按钮，才识别为 `greed`。

总结：

- `captures/`：原始截图素材，不自动识别。
- `state_manifest.json`：唯一识别入口。
- `mode: "any"`：多个模板里任意一个成功即可。
- `mode: "all"`：多个模板必须全部成功。

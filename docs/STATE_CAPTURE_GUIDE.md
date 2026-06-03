# 状态与动作模板采集指南

这份文档按完整流程说明：采集完整截图、裁小模板、配置 `state_manifest.json`、测试状态识别、测试动作定位。

## 1. 准备

在 PowerShell 里进入项目根目录：

```powershell
cd /d C:\path\to\czn_auto
$env:PYTHONPATH="src"
```

如果已经在项目根目录，只需要：

```powershell
$env:PYTHONPATH="src"
```

确认状态保存目录：

```powershell
python -m commands.state_check --list-states
```

采集时先使用 `--no-detect`，因为模板和 manifest 规则可能还没有准备好。

## 2. 采集完整截图

每次采集前，手动切到目标界面，确认游戏窗口无遮挡，等动画稳定后执行命令。

| 流程位置 | 状态名 | 采集命令 | 保存目录 |
|---|---|---|---|
| 主界面，能看到“模拟” | `main` | `python -m commands.state_check --save-state main --no-detect` | `templates/common/main/captures/` |
| 模拟界面，能看到“战斗训练” | `simulate` | `python -m commands.state_check --save-state simulate --no-detect` | `templates/simulate/captures/` |
| 战斗训练页，能看到各页签 | `battle_training` | `python -m commands.state_check --save-state battle_training --no-detect` | `templates/simulate/battle_training/captures/` |
| 记忆碎片页 | `memory_fragment` | `python -m commands.state_check --save-state memory_fragment --no-detect` | `templates/simulate/battle_training/memory/captures/` |
| 记忆碎片列表底部，能看到“贪婪与执着” | `memory_fragment` 或 `greed` | `python -m commands.state_check --save-state memory_fragment --no-detect` | `templates/simulate/battle_training/memory/captures/` |
| 贪婪与执着详情页，能看到“出击” | `greed` | `python -m commands.state_check --save-state greed --no-detect` | `templates/simulate/battle_training/memory/greed/captures/` |
| 战斗中，能看到右上角自动战斗/暂停区域 | `greed_game` | `python -m commands.state_check --save-state greed_game --no-detect` | `templates/simulate/battle_training/memory/greed/in_game/captures/` |
| 战斗结算页，能看到确认按钮 | `settlement` | `python -m commands.state_check --save-state settlement --no-detect` | `templates/common/battle/settlement/captures/` |

建议每个状态采 2-3 张，从中挑稳定清晰的一张裁模板。

## 3. 裁小模板

完整截图只是原材料，真正参与识别的是小模板。不要用整张界面当模板。

优先裁稳定元素：

- 按钮文字和少量按钮边框。
- 页面标题。
- 页签高亮。
- 固定图标加文字。

避免裁这些区域：

- 动态背景。
- 发光、粒子、动画。
- 角色、奖励内容、随机元素。

当前流程建议准备这些模板：

| 用途 | 文件路径 |
|---|---|
| 状态 `main` + 动作 `click_simulation` | `templates/common/main/main_simulation_button.jpg` |
| 状态 `simulate` + 动作 `click_battle_training` | `templates/simulate/simulate_battle_training_button.jpg` |
| 状态 `battle_training` + 动作 `click_memory_fragment` | `templates/simulate/battle_training/battle_training_memory_tab.jpg` |
| 状态 `memory_fragment` | `templates/simulate/battle_training/memory/memory_fragment_title.jpg` |
| 动作 `click_greed` | `templates/simulate/battle_training/memory/greed/greed_list_item.jpg` |
| 状态 `greed` | `templates/simulate/battle_training/memory/greed/greed_title.jpg` |
| 状态 `greed` + 动作 `click_sortie` | `templates/simulate/battle_training/memory/greed/greed_sortie_button.jpg` |
| 状态 `greed_game` + 动作 `click_auto_battle` | `templates/simulate/battle_training/memory/greed/in_game/auto_battle_button.jpg` |
| 状态 `settlement` + 动作 `click_confirm` | `templates/common/battle/settlement/settlement_confirm_button.jpg` |

## 4. 配置 Manifest

识别和动作都由 `templates/state_manifest.json` 定义。参考文件是：

```text
templates/state_manifest.example.json
```

核心规则：

- `label` 是识别成功后返回的状态名。
- `path` 决定实际用哪张模板图片匹配；程序不会按 `label` 自动找同名图片。
- `name` 是模板日志名。
- `roi` 是在完整截图里搜索模板的区域，坐标是 `[x1, y1, x2, y2]`，范围 0 到 1。
- `threshold` 是匹配阈值，通常从 `0.82` 开始。
- `mode: "all"` 表示所有状态模板都必须命中。
- `mode: "any"` 表示任意一个状态模板命中即可。
- `actions` 定义当前状态下可以执行的动作。

状态和动作示例：

```json
{
  "label": "main",
  "priority": 100,
  "mode": "all",
  "templates": [
    {
      "name": "main_simulation_button",
      "path": "common/main/main_simulation_button.jpg",
      "roi": [0.70, 0.20, 0.98, 0.55],
      "threshold": 0.82
    }
  ],
  "actions": {
    "click_simulation": {
      "type": "click_template",
      "target": "simulate",
      "template": {
        "name": "main_simulation_button",
        "path": "common/main/main_simulation_button.jpg",
        "roi": [0.70, 0.20, 0.98, 0.55],
        "threshold": 0.82
      },
      "click_at": [0.5, 0.5],
      "wait_after": 1.0
    }
  }
}
```

动作类型：

- `click_template`：用动作模板定位按钮，点击匹配框内的 `click_at`。
- `wheel`：在指定归一化坐标滚轮，例如列表下拉。
- `wait`：纯等待，例如等战斗结算。

## 5. 测试状态识别

状态模板写入 `state_manifest.json` 后，可以测试当前游戏画面，也可以测试已保存截图。

使用 `python -m commands.state_check --save-state <状态名>` 测试当前画面时，工具只会测试这个状态，不会被其它状态尚未裁好的模板干扰。完整自动流程运行时才会按 manifest 优先级扫描所有状态。

| 状态名 | 当前画面测试 | 已保存截图测试 |
|---|---|---|
| `main` | `python -m commands.state_check --save-state main` | `python .\src\main.py --image .\templates\common\main\captures\<raw>.jpg --out-dir .\debug_live` |
| `simulate` | `python -m commands.state_check --save-state simulate` | `python .\src\main.py --image .\templates\simulate\captures\<raw>.jpg --out-dir .\debug_live` |
| `battle_training` | `python -m commands.state_check --save-state battle_training` | `python .\src\main.py --image .\templates\simulate\battle_training\captures\<raw>.jpg --out-dir .\debug_live` |
| `memory_fragment` | `python -m commands.state_check --save-state memory_fragment` | `python .\src\main.py --image .\templates\simulate\battle_training\memory\captures\<raw>.jpg --out-dir .\debug_live` |
| `greed` | `python -m commands.state_check --save-state greed` | `python .\src\main.py --image .\templates\simulate\battle_training\memory\greed\captures\<raw>.jpg --out-dir .\debug_live` |
| `greed_game` | `python -m commands.state_check --save-state greed_game` | `python .\src\main.py --image .\templates\simulate\battle_training\memory\greed\in_game\captures\<raw>.jpg --out-dir .\debug_live` |
| `settlement` | `python -m commands.state_check --save-state settlement` | `python .\src\main.py --image .\templates\common\battle\settlement\captures\<raw>.jpg --out-dir .\debug_live` |

成功输出示例：

```text
fresh_state | greed | greed_title=0.914@(520,180)
```

失败输出通常是：

```text
fresh_state | unknown
```

`--out-dir .\debug_live` 会保存标注图，方便查看实际匹配位置。

## 6. 测试动作定位

状态能识别后，再测试动作模板。`--test-action` 只测试定位并保存标注图，不会点击。

| 状态 | 动作 | 命令 |
|---|---|---|
| `main` | `click_simulation` | `python -m commands.state_check --save-state main --test-action click_simulation` |
| `simulate` | `click_battle_training` | `python -m commands.state_check --save-state simulate --test-action click_battle_training` |
| `battle_training` | `click_memory_fragment` | `python -m commands.state_check --save-state battle_training --test-action click_memory_fragment` |
| `memory_fragment` | `click_greed` | `python -m commands.state_check --save-state memory_fragment --test-action click_greed` |
| `greed` | `click_sortie` | `python -m commands.state_check --save-state greed --test-action click_sortie` |
| `greed_game` | `click_auto_battle` | `python -m commands.state_check --save-state greed_game --test-action click_auto_battle` |
| `settlement` | `click_confirm` | `python -m commands.state_check --save-state settlement --test-action click_confirm` |

成功输出示例：

```text
action found: state=greed action=click_sortie type=click_template target=greed_game
action template matched: greed_sortie_button score=0.901 box=(3100,1840,3480,1990) click_point=(3290,1915)
saved action annotated capture: ...
```

常见失败：

- `action missing`：当前状态没有在 manifest 里定义这个动作。
- `action template not matched`：动作模板没有匹配到，检查 `template.path`、`template.roi`、`template.threshold`。

## 7. 调参规则

识别不到时按这个顺序调：

1. 确认 `path` 文件存在，文件名和扩展名正确。
2. 放大 `roi`，确保搜索区域覆盖模板实际位置。
3. 把 `threshold` 从 `0.82` 临时降到 `0.78`。
4. 如果能识别，再逐步缩小 `roi`、提高 `threshold`。
5. 如果仍然识别不到，重新裁更稳定的模板。

多模板规则：

- `captures/` 目录只是原始截图素材，不会自动参与识别。
- 只有 `state_manifest.json` 里明确写到 `path` 的模板会参与识别。
- `mode: "any"`：多个状态模板里任意一个成功即可。
- `mode: "all"`：多个状态模板必须全部成功。

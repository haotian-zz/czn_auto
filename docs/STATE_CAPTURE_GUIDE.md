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

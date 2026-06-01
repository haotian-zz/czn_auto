# CZN Auto 测试方法

本文档用于测试国服/新模板/新配置改动。建议按顺序执行：先不点击，只确认配置和识别；再单击；最后小范围实跑。

## 0. 测试前准备

1. 打开游戏，优先使用 16:9 全屏、无边框全屏或固定大小窗口。
2. 确认 `config.json` 里的窗口标题正确：

```json
"input": {
  "target_window_title": "Chaos Zero Nightmare"
}
```

3. 常用停止键：

```text
F8 / Esc / Pause / End
```

4. 运行命令前进入仓库目录：

```bat
cd /d path\to\czn_auto
```

## 一键测试命令

可以直接运行：

```bat
scripts\test_workflow.bat
```

它会自动执行非点击测试：语法检查、JSON 检查、入口 help、当前画面识别、窗口 dry-run 诊断、live 只识别不点击。

到了会实际点击游戏的测试时，会询问：

```text
y=yes, n=no
```

输入 `y` 才会继续执行单击测试或小流程点击测试；输入 `n` 会跳过对应点击测试。

脚本退出前会清理本次测试在仓库内生成的临时文件：

```text
__pycache__\
debug_live\fresh_state.jpg
debug_live\fresh_state_annotated.jpg
STOP
```

运行日志保留在 `%LOCALAPPDATA%\CZN Auto\logs`，用于失败排查。

## 1. 语法和配置检查

用于确认 Python 文件和 JSON 配置没有写坏。

```bat
python -m py_compile src\main.py src\state_check.py src\diagnose_input.py src\commands\cli.py src\commands\state_check.py src\commands\diagnose_input.py src\core\settings.py src\core\models.py src\vision\detector.py src\system\io_system.py src\system\controls.py src\actions\common.py src\ui\logging.py src\state_machines\live\session.py
python -m json.tool config.json
python -m json.tool config.example.json
```

通过标准：命令没有报错。

如果 `config.json` 报错，优先检查逗号、括号、引号是否漏写。

## 2. 查看窗口标题

用于确认 `target_window_title` 应该填什么。

把游戏窗口打开后运行：

```bat
python src\diagnose_input.py --dry-run
```

看输出里的：

```text
foreground=... title='...'
target_at=... title='...'
```

如果鼠标默认坐标不在游戏窗口上，把鼠标放到游戏窗口里，或者指定一个游戏内坐标：

```bat
python src\diagnose_input.py --x 1000 --y 800 --dry-run
```

拿到标题后，把其中稳定的一部分写进 `config.json`：

```json
"target_window_title": "窗口标题的一部分"
```

## 3. 测窗口匹配和后台点击目标

用于确认程序能按标题找到游戏窗口。

```bat
python src\diagnose_input.py --target-window-title "你的国服窗口标题" --dry-run
```

通过标准：输出里出现 `configured_title`，并且 title 是游戏窗口。

如果找不到：

- 检查游戏是否已经打开。
- 检查 `target_window_title` 是否和窗口标题一致。
- 只填标题中稳定的一小段，不要填会变化的 FPS、账号名、区服后缀。

## 4. 当前画面识别测试

用于测试当前画面会被识别成什么状态，不会点击。

把游戏停在某个明确界面，例如主页、配队页、三选一页，然后运行：

```bat
python src\state_check.py
```

它会生成：

```text
debug_live\fresh_state.jpg
debug_live\fresh_state_annotated.jpg
```

常见状态：

```text
start_screen      主页/入口页
team_screen       配队页
choice_screen     三选一页，但没有识别到目标词
legend_choice     三选一页，识别到“传说”
card_reward       卡牌奖励页
dream_found       识别到目标卡
flee_screen       脱逃页
return_confirm    返回确认弹窗
unknown           未识别
```

如果画面明确但识别成 `unknown`，优先替换对应模板图片。

## 5. 只识别不点击的 live 测试

用于观察连续画面识别结果，不会点击鼠标。

```bat
python src\main.py --live --max-seconds 30
```

通过标准：切换不同游戏界面时，日志里的状态跟画面一致。

常用加长版本：

```bat
python src\main.py --live --max-seconds 120 --wide-match-scales
```

`--wide-match-scales` 会用更多缩放比例匹配模板，速度慢一点，但适合刚适配模板时排查问题。

## 6. 单击测试

用于确认识别正确后，程序点击的位置是否正确。

建议先停在主页或配队页，再运行：

```bat
python src\main.py --live --act --max-seconds 8 --max-clicks 1 --input-backend postmessage_activate
```

通过标准：只点击一次，并且点到正确按钮。

如果后台点击没反应，测试真实鼠标模式：

```bat
python src\main.py --live --act --max-seconds 8 --max-clicks 1 --input-backend sendinput
```

如果真实鼠标模式能点，后台模式不能点，通常是窗口权限或游戏不接受后台消息。

## 7. 小范围流程测试

用于测试主页到配队、对白推进、三选一识别等短流程。

```bat
python src\main.py --live --act --max-seconds 60 --max-clicks 10 --input-backend postmessage_activate --advance-on-unknown --fast-start-to-team --wide-match-scales
```

通过标准：能按预期走到三选一、奖励页或返回流程，没有明显乱点。

如果有误点，先停下来，查看日志和 `config.json` 的坐标。

## 8. 完整流程测试

用于稳定性测试，会持续运行直到停止键、找到目标卡或出错。

```bat
python src\main.py --live --act --input-backend postmessage_activate --advance-on-unknown --fast-start-to-team --wide-match-scales
```

如果后台点击不稳定，改用：

```bat
python src\main.py --live --act --input-backend sendinput --advance-on-unknown --fast-start-to-team --wide-match-scales
```

## 9. 指定显示器测试

默认配置是自动找窗口：

```json
"runtime": {
  "monitor": "auto"
}
```

如果多屏时找错屏，可以手动指定显示器：

```bat
python src\main.py --live --monitor 1 --max-seconds 30
python src\main.py --live --monitor 2 --max-seconds 30
```

找到正确屏幕后，可以把 `config.json` 改成：

```json
"monitor": 2
```

## 10. 截图后离线识别测试

如果已经有截图文件，可以直接检测单张图：

```bat
python src\main.py --image path\to\screenshot.jpg
```

如果需要输出标注图：

```bat
python src\main.py --image path\to\screenshot.jpg --out-dir debug_live
```

适合用来验证新裁剪的模板是否能识别国服截图。

## 11. 视频离线识别测试

如果录了一段完整流程视频，可以按固定间隔抽帧识别：

```bat
python src\main.py --video path\to\recording.mp4 --every-sec 0.25 --out-dir debug_video
```

适合检查状态流转是否稳定。

## 12. 常见问题定位

### 一直是 unknown

优先检查：

- `templates` 里的对应模板是否来自国服画面。
- 模板是否裁得太大，包含了易变化背景。
- 游戏分辨率是否接近 16:9。
- `target_window_title` 是否导致截错窗口。

### 识别正确但点歪

修改 `config.json` 的 `click_points`。

坐标换算：

```text
配置 x = 实际按钮中心 x / 截图宽度
配置 y = 实际按钮中心 y / 截图高度
```

例子：按钮中心在 1920x1080 的 `(1613, 977)`：

```text
x = 1613 / 1920 = 0.840
y = 977 / 1080 = 0.905
```

### 点了但游戏没反应

按顺序排查：

1. 用管理员权限运行。
2. 改用 `--input-backend sendinput`。
3. 确认游戏窗口没有被遮挡或最小化。
4. 确认 `target_window_title` 找到的是游戏窗口。

### 加载慢导致提前点对白

加大：

```json
"wait_after_team_enter": 8.0,
"post_click_wait": 5.0
```

### 奖励页刚出现就误退出

加大：

```json
"reward_settle_before_action": 2.0
```

### 三选一刚出现就当作没传说

加大：

```json
"choice_settle_before_action": 0.6
```

## 13. 打包前检查

打包前先跑：

```bat
python -m py_compile src\main.py src\state_check.py src\diagnose_input.py src\commands\cli.py src\commands\state_check.py src\commands\diagnose_input.py src\core\settings.py src\core\models.py src\vision\detector.py src\system\io_system.py src\system\controls.py src\actions\common.py src\ui\logging.py src\state_machines\live\session.py
python -m json.tool config.example.json
```

确认 `config.example.json` 已经同步国服默认配置。

只有需要发布安装包或便携包时才运行：

```bat
packaging\build_release.bat
```

打包后检查：

- `dist\CZNAuto\config.json` 是否是新的默认配置。
- `dist\CZNAuto\templates` 是否包含国服模板。
- `dist\CZNAuto\start_czn_auto.bat` 是否能启动。
- 安装版快捷方式是否能启动。

## 14. 推荐测试顺序

```text
语法/JSON 检查
-> 窗口标题检查
-> state_check 当前画面识别
-> live 只识别不点击
-> 单击测试
-> 60 秒小流程测试
-> 完整流程测试
-> 打包前检查
```

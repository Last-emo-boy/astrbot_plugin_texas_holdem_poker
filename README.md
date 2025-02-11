# Texas Hold'em Poker Bot 插件

**插件名称**: Texas Hold'em Poker Bot  
**作者**: w33d  
**版本**: 1.2.0  
**仓库**: [GitHub 地址](https://github.com/Last-emo-boy/astrbot_plugin_texas_holdem_poker)

## 插件简介

这个插件基于 AstrBot 平台，旨在实现一个完整的德州扑克（Texas Hold'em Poker）游戏。插件支持以下功能：

- **游戏流程**  
  - **/poker start**：开启一局新的德州扑克游戏，并设置买入金额、盲注、每轮下注金额以及最大玩家数。
  - **/poker join**：玩家加入当前游戏，自动扣除买入筹码。
  - **/poker deal**：发牌，插件会随机为每个玩家发两张手牌，并通过私信发送给玩家（采用底层 SimpleGewechatClient 的 post_text 方法）。
  - **/poker call**：跟注，玩家补足当前下注金额。
  - **/poker raise <increment>**：加注，玩家在跟注的基础上额外加注指定代币数。
  - **/poker allin**：全压，将玩家剩余的所有筹码全部投入当前下注。
  - **/poker check**：看牌，当前玩家若已跟满当前注则可以选择看牌而不追加筹码。
  - **/poker next**：推进游戏到下一阶段。根据当前阶段自动发翻牌、转牌、河牌，并最终进入摊牌阶段。
  - **/poker showdown**：摊牌，计算每位玩家的最佳牌型，比较牌力决定赢家或平局，奖金分配后保存游戏记录与排行榜数据。
  - **/poker status**：以美化后的图文形式显示当前游戏状态、公共牌、玩家信息及筹码余额。
  - **/poker tokens**：查询个人当前余额。
  - **/poker reset**：重置当前群聊游戏状态（适用于游戏中断等情况）。
  - **/poker add_balance <amount>**：增加当前用户的余额（便于测试和奖励）。

- **图文渲染**  
  使用 HTML + Jinja2 模板将牌局状态、公共牌以及玩家手牌渲染成图片，提升游戏界面效果。你可以通过 `/poker status` 和 `/poker next` 命令看到美化后的状态图片。

- **游戏记录和排行榜**  
  - 每局游戏结束后，详细记录各玩家的筹码变化、下注历史、牌型比较结果等，并保存到 `game_records.json` 文件中，方便日后查询和回放。
  - 同时，插件还建立了简单的排行榜（或胜率统计系统），将每位玩家的游戏次数和胜利次数保存到 `ranking.json` 文件中。

## 安装与配置

1. **安装插件**  
   将插件代码放置于 AstrBot 插件目录下，并确保文件名为 `main.py`。

2. **依赖安装**  
   - 确保 AstrBot 框架已正确安装。
   - 本插件依赖于 AstrBot 自带的 HTML 渲染功能（`html_render` 方法）和 SimpleGewechatClient 模块，需确保相应依赖均已安装和配置。

3. **配置文件 (_conf_schema.json)**  
   在插件目录下建立 `_conf_schema.json`，示例内容如下：

   ```json
   {
       "buyin": {
           "description": "每局的买入金额",
           "type": "int",
           "default": 100
       },
       "small_blind": {
           "description": "小盲注金额",
           "type": "int",
           "default": 10
       },
       "big_blind": {
           "description": "大盲注金额",
           "type": "int",
           "default": 20
       },
       "bet_amount": {
           "description": "每轮固定跟注金额",
           "type": "int",
           "default": 20
       },
       "max_players": {
           "description": "允许参加游戏的最大玩家数",
           "type": "int",
           "default": 9
       },
       "initial_token": {
           "description": "每个玩家的初始代币数量",
           "type": "int",
           "default": 1000
       }
   }
   ```

4. **记录文件**  
   插件运行时会自动生成或更新以下文件：
   - `tokens.json`：存储每个群聊中玩家的当前余额。
   - `game_records.json`：保存每局游戏的详细记录。
   - `ranking.json`：保存排行榜数据和玩家胜率统计。

## 使用方法

在群聊（或私聊）中使用以下命令触发相应操作：

- `/poker start`：启动一局新的游戏。
- `/poker join`：加入当前游戏。
- `/poker deal`：发牌，每个玩家将通过私信接收到自己的手牌。
- `/poker call`：跟注。
- `/poker raise <increment>`：加注指定筹码。
- `/poker allin`：全压，将剩余筹码全部投注。
- `/poker check`：看牌，当你已跟满当前注时可以选择看牌。
- `/poker next`：进入下一阶段（翻牌、转牌、河牌或摊牌）。
- `/poker showdown`：摊牌，计算牌型，决定赢家并更新记录（通常由 `/poker next` 在河牌阶段自动调用）。
- `/poker status`：查看当前游戏状态（以美化后的图片形式展示）。
- `/poker tokens`：查询你的余额。
- `/poker add_balance <amount>`：增加你的余额（测试或奖励用）。
- `/poker reset`：重置当前群游戏（例如出现异常时）。

## 注意事项

- 请确保你的 AstrBot 框架版本与本插件兼容。
- HTML 渲染依赖内置的 `html_render` 方法，如需定制化效果可进一步修改模板。
- 牌型评价函数仅为基础示例，如需更准确的德州扑克牌型比较，请根据需求调整算法。
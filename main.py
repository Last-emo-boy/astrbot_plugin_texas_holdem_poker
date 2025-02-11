import itertools
from astrbot.api.all import *
from astrbot.core.platform.sources.gewechat.client import SimpleGewechatClient
import random
import json
import os

class PokerGame:
    def __init__(self, buyin: int, small_blind: int, big_blind: int, bet_amount: int, max_players: int):
        self.buyin = buyin                  # 加入游戏时支付的买入金额
        self.small_blind = small_blind      # 小盲注金额
        self.big_blind = big_blind          # 大盲注金额
        self.bet_amount = bet_amount        # 后续每轮固定跟注金额
        self.max_players = max_players      # 最大玩家数
        self.players = []                   # 玩家记录：{"id": str, "name": str, "cards": list, ...}
        self.deck = self.create_deck()      # 洗好的牌堆
        self.community_cards = []           # 公共牌
        self.phase = "waiting"              # 游戏阶段：waiting, preflop, flop, turn, river, showdown
        self.pot = 0                        # 当前彩池
        self.current_bet = 0                # 当前轮要求的投注额度

    def create_deck(self):
        suits = ['♠', '♥', '♦', '♣']
        ranks = ['2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K', 'A']
        deck = [f"{rank}{suit}" for suit in suits for rank in ranks]
        random.shuffle(deck)
        return deck

    def deal_card(self):
        if not self.deck:
            self.deck = self.create_deck()
        return self.deck.pop()


# -------------------------
# 牌型评价函数
# -------------------------
def evaluate_5cards(cards: list) -> tuple:
    """
    对 5 张牌进行评价，返回一个元组表示手牌强度。
    数值越大表示手牌越好，元组中第一个元素为类别，其它元素为高牌信息。
    类别定义：
        8: 同花顺
        7: 四条
        6: 葫芦（满堂红）
        5: 同花
        4: 顺子
        3: 三条
        2: 两对
        1: 一对
        0: 高牌
    """
    rank_map = {"2":2, "3":3, "4":4, "5":5, "6":6, "7":7, "8":8, "9":9, "10":10, "J":11, "Q":12, "K":13, "A":14}
    values = []
    suits = []
    for card in cards:
        rank = card[:-1]
        suit = card[-1]
        values.append(rank_map[rank])
        suits.append(suit)
    values.sort(reverse=True)
    freq = {}
    for v in values:
        freq[v] = freq.get(v, 0) + 1
    counts = sorted(freq.values(), reverse=True)
    flush = len(set(suits)) == 1
    straight = False
    high_straight = None
    unique_vals = sorted(set(values))
    if len(unique_vals) >= 5:
        for i in range(len(unique_vals)-4):
            seq = unique_vals[i:i+5]
            if seq == list(range(seq[0], seq[0]+5)):
                straight = True
                high_straight = seq[-1]
        if set([14,2,3,4,5]).issubset(set(values)):
            straight = True
            high_straight = 5
    if flush and straight:
        return (8, high_straight, values)
    elif counts[0] == 4:
        four_val = max(v for v, c in freq.items() if c == 4)
        kicker = max(v for v in values if v != four_val)
        return (7, four_val, kicker)
    elif counts[0] == 3 and any(c >= 2 for v, c in freq.items() if c >= 2 and v not in [max(v for v, c in freq.items() if c == 3)]):
        three_val = max(v for v, c in freq.items() if c == 3)
        pair_val = max(v for v, c in freq.items() if c >= 2 and v != three_val)
        return (6, three_val, pair_val)
    elif flush:
        return (5, values)
    elif straight:
        return (4, high_straight, values)
    elif counts[0] == 3:
        three_val = max(v for v, c in freq.items() if c == 3)
        kickers = sorted([v for v in values if v != three_val], reverse=True)
        return (3, three_val, kickers)
    elif counts[0] == 2 and len([v for v, c in freq.items() if c == 2]) >= 2:
        pairs = sorted([v for v, c in freq.items() if c == 2], reverse=True)
        kicker = max(v for v in values if v not in pairs)
        return (2, pairs, kicker)
    elif counts[0] == 2:
        pair_val = max(v for v, c in freq.items() if c == 2)
        kickers = sorted([v for v in values if v != pair_val], reverse=True)
        return (1, pair_val, kickers)
    else:
        return (0, values)

def evaluate_hand(cards: list) -> tuple:
    """
    给定 7 张牌（2张手牌+5张公共牌），返回最佳 5 张牌的评价元组。
    """
    best = None
    for combo in itertools.combinations(cards, 5):
        rank = evaluate_5cards(list(combo))
        if best is None or rank > best:
            best = rank
    return best

# -------------------------
# 德州扑克插件
# -------------------------
@register("texas_holdem_poker", "w33d", "Texas Hold'em Poker Bot插件", "1.1.0", "https://github.com/Last-emo-boy/astrbot_plugin_texas_holdem_poker")
class TexasHoldemPoker(Star):
    def __init__(self, context: Context, config: dict):
        super().__init__(context)
        self.config = config
        self.games = {}  # 存储各群游戏状态
        self.tokens_file = os.path.join(os.path.dirname(__file__), "tokens.json")
        self.tokens = self.load_tokens()

    def load_tokens(self):
        try:
            if os.path.exists(self.tokens_file):
                with open(self.tokens_file, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception as e:
            print("加载tokens失败:", e)
        return {}

    def save_tokens(self):
        try:
            with open(self.tokens_file, "w", encoding="utf-8") as f:
                json.dump(self.tokens, f, ensure_ascii=False, indent=4)
        except Exception as e:
            print("保存tokens失败:", e)

    def get_group_id(self, event: AstrMessageEvent) -> str:
        group_id = event.message_obj.group_id
        if not group_id:
            group_id = f"private_{event.get_sender_id()}"
        return group_id

    @command_group("poker")
    def poker():
        '''德州扑克指令组'''
        pass

    @poker.command("start")
    async def start_game(self, event: AstrMessageEvent):
        group_id = self.get_group_id(event)
        if group_id in self.games:
            yield event.plain_result("本群已存在正在进行的游戏，请结束当前游戏后再开始新游戏。")
            return
        buyin = self.config.get("buyin", 100)
        small_blind = self.config.get("small_blind", 10)
        big_blind = self.config.get("big_blind", 20)
        bet_amount = self.config.get("bet_amount", 20)
        max_players = self.config.get("max_players", 9)
        self.games[group_id] = PokerGame(buyin, small_blind, big_blind, bet_amount, max_players)
        yield event.plain_result(
            f"新德州扑克游戏开始！买入: {buyin}, 小盲注: {small_blind}, 大盲注: {big_blind}, 每轮跟注金额: {bet_amount}, 最大玩家: {max_players}。\n请发送 `/poker join` 加入游戏。"
        )

    @poker.command("add_balance")
    async def add_balance(self, event: AstrMessageEvent, amount: int):
        '''增加余额：给当前用户增加指定数量的代币'''
        group_id = self.get_group_id(event)
        sender_id = event.get_sender_id()
        if group_id not in self.tokens:
            self.tokens[group_id] = {}
        self.tokens[group_id][sender_id] = self.tokens[group_id].get(sender_id, self.config.get("initial_token", 1000)) + amount
        self.save_tokens()
        yield event.plain_result(f"成功增加 {amount} 代币。你当前余额: {self.tokens[group_id][sender_id]}")

    @poker.command("join")
    async def join_game(self, event: AstrMessageEvent):
        group_id = self.get_group_id(event)
        if group_id not in self.games:
            yield event.plain_result("当前群聊没有正在进行的游戏，请先使用 `/poker start` 开始游戏。")
            return
        game = self.games[group_id]
        sender_id = event.get_sender_id()
        sender_name = event.get_sender_name()
        for player in game.players:
            if player["id"] == sender_id:
                yield event.plain_result("你已经加入了本局游戏。")
                return
        # 记录私信 session 字符串供记录使用（格式："gewechat:FriendMessage:{wxid}"）
        private_unified = f"gewechat:FriendMessage:{sender_id}"
        if group_id not in self.tokens:
            self.tokens[group_id] = {}
        if sender_id not in self.tokens[group_id]:
            initial_token = self.config.get("initial_token", 1000)
            self.tokens[group_id][sender_id] = initial_token
        buyin = game.buyin
        if self.tokens[group_id][sender_id] < buyin:
            yield event.plain_result(f"余额不足，买入需要 {buyin} 代币。你当前余额: {self.tokens[group_id][sender_id]}")
            return
        self.tokens[group_id][sender_id] -= buyin
        self.save_tokens()
        game.pot += buyin
        game.players.append({
            "id": sender_id,
            "name": sender_name,
            "cards": [],
            "private_unified": private_unified,
            "round_bet": 0,
            "active": True
        })
        yield event.plain_result(
            f"{sender_name} 加入游戏，扣除买入 {buyin} 代币。当前彩池: {game.pot} 代币。你当前余额: {self.tokens[group_id][sender_id]}"
        )

    @poker.command("deal")
    async def deal_hole_cards(self, event: AstrMessageEvent):
        group_id = self.get_group_id(event)
        if group_id not in self.games:
            yield event.plain_result("当前群聊没有正在进行的游戏。")
            return
        game = self.games[group_id]
        if len(game.players) < 2:
            yield event.plain_result("至少需要2名玩家才能开始游戏。")
            return
        if game.phase != "waiting":
            yield event.plain_result("游戏已经开始发牌了。")
            return

        # 动态获取当前事件所属平台适配器
        platform_name = event.platform_meta.name
        adapter = next((adapter for adapter in self.context.platform_manager.get_insts()
                        if adapter.meta().name.lower() == platform_name.lower()), None)
        if adapter is None:
            yield event.plain_result(f"未找到 {platform_name} 平台适配器。")
            return

        for player in game.players:
            card1 = game.deal_card()
            card2 = game.deal_card()
            player["cards"] = [card1, card2]
            content = f"你的手牌: {card1} {card2}"
            # 直接使用目标用户的 wxid 发送私信
            await adapter.client.post_text(player["id"], content)
        # 分配盲注
        small_blind_player = game.players[0]
        sb_amount = game.small_blind
        group_tokens = self.tokens[group_id]
        available = group_tokens.get(small_blind_player["id"], 0)
        sb = min(available, sb_amount)
        group_tokens[small_blind_player["id"]] = available - sb
        small_blind_player["round_bet"] += sb
        game.pot += sb

        big_blind_player = game.players[1]
        available = group_tokens.get(big_blind_player["id"], 0)
        bb_amount = game.big_blind
        bb = min(available, bb_amount)
        group_tokens[big_blind_player["id"]] = available - bb
        big_blind_player["round_bet"] += bb
        game.pot += bb

        self.save_tokens()
        game.current_bet = game.big_blind
        game.phase = "preflop"
        yield event.plain_result(
            f"手牌已发出，各玩家请查看私信。\n盲注分配：{small_blind_player['name']} 小盲 {sb}，{big_blind_player['name']} 大盲 {bb}。\n当前预注金额为 {game.current_bet} 代币。请使用 `/poker call` 跟注，或 `/poker next` 进入下一阶段。"
        )

    @poker.command("call")
    async def call_bet(self, event: AstrMessageEvent):
        group_id = self.get_group_id(event)
        if group_id not in self.games:
            yield event.plain_result("当前群聊没有正在进行的游戏。")
            return
        game = self.games[group_id]
        sender_id = event.get_sender_id()
        player = None
        for p in game.players:
            if p["id"] == sender_id and p["active"]:
                player = p
                break
        if not player:
            yield event.plain_result("你不在当前游戏中或已弃牌。")
            return
        if player["round_bet"] >= game.current_bet:
            yield event.plain_result("你已经跟注了。")
            return
        required = game.current_bet - player["round_bet"]
        group_tokens = self.tokens[group_id]
        if group_tokens.get(sender_id, 0) < required:
            yield event.plain_result(f"余额不足，需跟注 {required} 代币。你当前余额: {group_tokens.get(sender_id, 0)}")
            return
        group_tokens[sender_id] -= required
        player["round_bet"] += required
        game.pot += required
        self.save_tokens()
        yield event.plain_result(f"你已跟注，支付 {required} 代币。当前彩池: {game.pot} 代币。")

    @poker.command("raise")
    async def raise_bet(self, event: AstrMessageEvent, increment: int):
        '''加注：支付跟注差额再额外加注指定代币'''
        group_id = self.get_group_id(event)
        if group_id not in self.games:
            yield event.plain_result("当前群聊没有正在进行的游戏。")
            return
        game = self.games[group_id]
        sender_id = event.get_sender_id()
        player = None
        for p in game.players:
            if p["id"] == sender_id and p["active"]:
                player = p
                break
        if not player:
            yield event.plain_result("你不在当前游戏中或已弃牌。")
            return
        required_call = game.current_bet - player["round_bet"]
        total_raise = required_call + increment
        group_tokens = self.tokens[group_id]
        if group_tokens.get(sender_id, 0) < total_raise:
            yield event.plain_result(f"余额不足，需支付 {total_raise} 代币（含跟注差额和加注）。你当前余额: {group_tokens.get(sender_id, 0)}")
            return
        group_tokens[sender_id] -= total_raise
        player["round_bet"] += total_raise
        game.pot += total_raise
        game.current_bet = player["round_bet"]
        self.save_tokens()
        yield event.plain_result(f"你加注了 {increment} 代币，总支付 {total_raise} 代币。当前彩池: {game.pot} 代币，新预注金额: {game.current_bet} 代币。")

    @poker.command("fold")
    async def fold(self, event: AstrMessageEvent):
        group_id = self.get_group_id(event)
        if group_id not in self.games:
            yield event.plain_result("当前群聊没有正在进行的游戏。")
            return
        game = self.games[group_id]
        sender_id = event.get_sender_id()
        found = False
        for p in game.players:
            if p["id"] == sender_id and p["active"]:
                p["active"] = False
                found = True
                yield event.plain_result(f"{p['name']} 已弃牌。")
                break
        if not found:
            yield event.plain_result("你不在当前游戏中或已弃牌。")
            return
        active_players = [p for p in game.players if p["active"]]
        if len(active_players) == 1:
            winner = active_players[0]
            group_tokens = self.tokens[group_id]
            group_tokens[winner["id"]] += game.pot
            self.save_tokens()
            yield event.plain_result(f"只有 {winner['name']} 一人未弃牌，赢得彩池 {game.pot} 代币！")
            del self.games[group_id]

    @poker.command("next")
    async def next_round(self, event: AstrMessageEvent):
        group_id = self.get_group_id(event)
        if group_id not in self.games:
            yield event.plain_result("当前群聊没有正在进行的游戏。")
            return
        game = self.games[group_id]
        not_called = [p["name"] for p in game.players if p["active"] and p["round_bet"] < game.current_bet]
        if not_called:
            yield event.plain_result("以下玩家还未跟注: " + ", ".join(not_called))
            return

        if game.phase == "preflop":
            game.deal_card()  # 烧牌
            flop_cards = [game.deal_card() for _ in range(3)]
            game.community_cards.extend(flop_cards)
            game.phase = "flop"
            for p in game.players:
                if p["active"]:
                    p["round_bet"] = 0
            game.current_bet = game.bet_amount
            TMPL = '''
            <div style="font-size:32px; font-family:Arial, sans-serif; text-align:center; padding:30px; background:#e0f7fa; border-radius:10px;">
                <h2 style="color:#2c3e50; margin-bottom:20px;">翻牌阶段</h2>
                <p style="margin:20px 0;">翻牌: <span style="font-weight:bold;">{{ cards }}</span></p>
                <p style="margin:20px 0;">当前轮下注金额: <span style="font-weight:bold;">{{ current_bet }}</span> 代币</p>
                <p style="margin:20px 0;">请使用 /poker call 跟注，或 /poker next 进入下一阶段</p>
            </div>
            '''
            data = {"cards": " ".join(flop_cards), "current_bet": game.current_bet}
            url = await self.html_render(TMPL, data)
            yield event.image_result(url)

        elif game.phase == "flop":
            game.deal_card()  # 烧牌
            turn_card = game.deal_card()
            game.community_cards.append(turn_card)
            game.phase = "turn"
            for p in game.players:
                if p["active"]:
                    p["round_bet"] = 0
            game.current_bet = game.bet_amount
            TMPL = '''
            <div style="font-size:32px; font-family:Arial, sans-serif; text-align:center; padding:30px; background:#e8f5e9; border-radius:10px;">
                <h2 style="color:#2c3e50; margin-bottom:20px;">转牌阶段</h2>
                <p style="margin:20px 0;">转牌: <span style="font-weight:bold;">{{ card }}</span></p>
                <p style="margin:20px 0;">当前轮下注金额: <span style="font-weight:bold;">{{ current_bet }}</span> 代币</p>
                <p style="margin:20px 0;">请使用 /poker call 跟注，或 /poker next 进入下一阶段</p>
            </div>
            '''
            data = {"card": turn_card, "current_bet": game.current_bet}
            url = await self.html_render(TMPL, data)
            yield event.image_result(url)

        elif game.phase == "turn":
            game.deal_card()  # 烧牌
            river_card = game.deal_card()
            game.community_cards.append(river_card)
            game.phase = "river"
            for p in game.players:
                if p["active"]:
                    p["round_bet"] = 0
            game.current_bet = game.bet_amount
            TMPL = '''
            <div style="font-size:32px; font-family:Arial, sans-serif; text-align:center; padding:30px; background:#fff3e0; border-radius:10px;">
                <h2 style="color:#2c3e50; margin-bottom:20px;">河牌阶段</h2>
                <p style="margin:20px 0;">河牌: <span style="font-weight:bold;">{{ card }}</span></p>
                <p style="margin:20px 0;">当前轮下注金额: <span style="font-weight:bold;">{{ current_bet }}</span> 代币</p>
                <p style="margin:20px 0;">请使用 /poker call 跟注，或 /poker next 进入摊牌阶段</p>
            </div>
            '''
            data = {"card": river_card, "current_bet": game.current_bet}
            url = await self.html_render(TMPL, data)
            yield event.image_result(url)

        elif game.phase == "river":
            async for result in self.showdown(event):
                yield result
        else:
            yield event.plain_result("游戏阶段错误。")




    @poker.command("showdown")
    async def showdown(self, event: AstrMessageEvent):
        '''摊牌：计算每个玩家的最佳手牌并决定赢家'''
        group_id = self.get_group_id(event)
        if group_id not in self.games:
            yield event.plain_result("当前群聊没有正在进行的游戏。")
            return
        game = self.games[group_id]
        if game.phase != "river":
            yield event.plain_result("还未到摊牌阶段。")
            return
        results = {}
        for player in game.players:
            if not player["active"]:
                continue
            if len(game.community_cards) != 5 or len(player["cards"]) != 2:
                yield event.plain_result("牌数不足，无法摊牌。")
                return
            total_cards = player["cards"] + game.community_cards
            hand_rank = evaluate_hand(total_cards)
            results[player["id"]] = (player["name"], hand_rank)
        best = None
        winners = []
        for pid, (name, rank) in results.items():
            if best is None or rank > best:
                best = rank
                winners = [(pid, name)]
            elif rank == best:
                winners.append((pid, name))
        msg = "摊牌结果：\n"
        for pid, (name, rank) in results.items():
            msg += f"{name}: {rank}\n"
        if len(winners) == 1:
            winner_name = winners[0][1]
            msg += f"\n赢家是 {winner_name}，赢得彩池 {game.pot} 代币！"
            self.tokens[group_id][winners[0][0]] += game.pot
        else:
            names = ", ".join(name for pid, name in winners)
            msg += f"\n平局：{names}，各得彩池的一半。"
            share = game.pot // len(winners)
            for pid, name in winners:
                self.tokens[group_id][pid] += share
                
        # 在决定赢家之后，输出所有参与玩家的最终余额
        final_balances = "参与玩家最终余额：\n"
        for player in game.players:
            uid = player["id"]
            balance = self.tokens[group_id].get(uid, self.config.get("initial_token", 1000))
            final_balances += f"{player['name']}: {balance} 代币\n"
        yield event.plain_result(final_balances)

        self.save_tokens()
        yield event.plain_result(msg)
        del self.games[group_id]

    @poker.command("status")
    async def game_status(self, event: AstrMessageEvent):
        '''显示当前游戏状态（美化版）'''
        group_id = self.get_group_id(event)
        if group_id not in self.games:
            yield event.plain_result("当前群聊没有正在进行的游戏。")
            return
        game = self.games[group_id]
        players_data = []
        for p in game.players:
            players_data.append({
                "name": p["name"],
                "status": "活跃" if p["active"] else "弃牌",
                "round_bet": p["round_bet"],
                "cards": " ".join(p["cards"]) if p["cards"] else "未发牌"
            })
        data = {
            "phase": game.phase,
            "pot": game.pot,
            "community_cards": " ".join(game.community_cards) if game.community_cards else "无",
            "players": players_data
        }
        TMPL = '''
        <html>
        <head>
            <style>
                body {
                    font-family: Arial, sans-serif;
                    background-color: #f0f0f0;
                    margin: 0;
                    padding: 20px;
                }
                .container {
                    background-color: #ffffff;
                    border-radius: 10px;
                    padding: 30px;
                    box-shadow: 0 2px 8px rgba(0,0,0,0.15);
                    text-align: center;
                }
                h2 {
                    font-size: 36px;
                    color: #333;
                    margin-bottom: 20px;
                }
                p {
                    font-size: 32px;
                    margin: 10px 0;
                }
                .players {
                    margin-top: 30px;
                    text-align: left;
                }
                .player {
                    font-size: 32px;
                    padding: 10px;
                    border-bottom: 1px solid #e0e0e0;
                }
                .player:last-child {
                    border-bottom: none;
                }
            </style>
        </head>
        <body>
            <div class="container">
                <h2>德州扑克游戏状态</h2>
                <p>游戏阶段: <strong>{{ phase }}</strong></p>
                <p>彩池: <strong>{{ pot }}</strong> 代币</p>
                <p>公共牌: <strong>{{ community_cards }}</strong></p>
                <div class="players">
                    <h3>玩家信息</h3>
                    {% for player in players %}
                    <div class="player">
                        <p>姓名: <strong>{{ player.name }}</strong></p>
                        <p>状态: <strong>{{ player.status }}</strong></p>
                        <p>本轮投注: <strong>{{ player.round_bet }}</strong> 代币</p>
                        <p>手牌: <strong>{{ player.cards }}</strong></p>
                    </div>
                    {% endfor %}
                </div>
            </div>
        </body>
        </html>
        '''
        url = await self.html_render(TMPL, data)
        yield event.image_result(url)



    @poker.command("tokens")
    async def my_tokens(self, event: AstrMessageEvent):
        group_id = self.get_group_id(event)
        if group_id not in self.tokens:
            balance = self.config.get("initial_token", 1000)
        else:
            balance = self.tokens[group_id].get(event.get_sender_id(), self.config.get("initial_token", 1000))
        yield event.plain_result(f"你的代币余额: {balance} 代币")

    @poker.command("reset")
    async def reset_game(self, event: AstrMessageEvent):
        group_id = self.get_group_id(event)
        if group_id in self.games:
            del self.games[group_id]
            yield event.plain_result("当前游戏已重置。")
        else:
            yield event.plain_result("当前群聊没有进行中的游戏。")
    
    @poker.command("allin")
    async def allin(self, event: AstrMessageEvent):
        '''全压：将你的剩余代币全部投入当前投注'''
        group_id = self.get_group_id(event)
        if group_id not in self.games:
            yield event.plain_result("当前群聊没有正在进行的游戏。")
            return
        game = self.games[group_id]
        sender_id = event.get_sender_id()
        player = None
        for p in game.players:
            if p["id"] == sender_id and p["active"]:
                player = p
                break
        if not player:
            yield event.plain_result("你不在当前游戏中或已弃牌。")
            return
        group_tokens = self.tokens[group_id]
        balance = group_tokens.get(sender_id, 0)
        if balance == 0:
            yield event.plain_result("你已经没有剩余代币，全压失败。")
            return
        # 全压：直接将剩余余额投入
        allin_amount = balance
        group_tokens[sender_id] = 0
        player["round_bet"] += allin_amount
        game.pot += allin_amount
        # 如有必要，更新当前注（例如全压后玩家投注更高）
        if player["round_bet"] > game.current_bet:
            game.current_bet = player["round_bet"]
        self.save_tokens()
        yield event.plain_result(f"你全压了 {allin_amount} 代币。当前彩池: {game.pot} 代币。")

    @poker.command("check")
    async def check(self, event: AstrMessageEvent):
        '''看牌：当你已经跟满当前注额时，可选择看牌'''
        group_id = self.get_group_id(event)
        if group_id not in self.games:
            yield event.plain_result("当前群聊没有正在进行的游戏。")
            return
        game = self.games[group_id]
        sender_id = event.get_sender_id()
        player = None
        for p in game.players:
            if p["id"] == sender_id and p["active"]:
                player = p
                break
        if not player:
            yield event.plain_result("你不在当前游戏中或已弃牌。")
            return
        if player["round_bet"] < game.current_bet:
            yield event.plain_result("你当前还未跟满注，无法看牌。")
            return
        yield event.plain_result("你选择看牌，等待下一轮行动。")